package space.harbour.cloud.importer;

import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Reads a day's worth of coffee-shop payments from a CSV file ("the notebook")
 * and reliably propagates each one to the StarHarbour Payments API
 * ("the Central System").
 *
 * <p>Reliability is built from three independent layers:
 * <ol>
 *   <li><b>Idempotency</b> — every row carries a stable {@code Idempotency-Key},
 *       so a retried POST never creates a duplicate payment. The server dedupes
 *       on (Store-Id x Idempotency-Key) and replays the original with 200.</li>
 *   <li><b>Retries with capped exponential backoff + full jitter</b> — transient
 *       failures (connection drops, timeouts, 408/429/5xx) are retried; permanent
 *       failures (400/422 validation) are not.</li>
 *   <li><b>A local journal</b> — confirmed keys are appended to a file so a crashed
 *       or re-run import skips work it already finished. (Idempotency alone makes
 *       re-sending safe; the journal just makes it fast and auditable.)</li>
 * </ol>
 *
 * <p>Point {@code baseUrl} at the Toxiproxy port (9091) to exercise all of this
 * under injected latency / timeouts.
 */
public final class PaymentCsvImporter {

    // ---- configuration -----------------------------------------------------

    public record Config(
            URI baseUrl,
            int maxAttempts,
            Duration baseBackoff,
            Duration maxBackoff,
            Duration requestTimeout,
            Path journal) {

        public static Config defaults() {
            return new Config(
                    URI.create("http://localhost:9091"), // route through Toxiproxy
                    6,
                    Duration.ofMillis(500),
                    Duration.ofSeconds(10),
                    Duration.ofSeconds(10),
                    Path.of("import-journal.txt"));
        }
    }

    public record Stats(int created, int alreadyExisted, int skipped, int failed) {
        Stats plusCreated()       { return new Stats(created + 1, alreadyExisted, skipped, failed); }
        Stats plusAlready()       { return new Stats(created, alreadyExisted + 1, skipped, failed); }
        Stats plusSkipped()       { return new Stats(created, alreadyExisted, skipped + 1, failed); }
        Stats plusFailed()        { return new Stats(created, alreadyExisted, skipped, failed + 1); }
    }

    private final Config cfg;
    private final HttpClient http;

    public PaymentCsvImporter(Config cfg, HttpClient http) {
        this.cfg = cfg;
        this.http = http;
    }

    // ---- public entry points -----------------------------------------------

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: PaymentCsvImporter <payments.csv> [baseUrl]");
            System.exit(2);
        }
        Config base = Config.defaults();
        Config cfg = (args.length >= 2)
                ? new Config(URI.create(args[1]), base.maxAttempts(), base.baseBackoff(),
                             base.maxBackoff(), base.requestTimeout(), base.journal())
                : base;

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        Stats s = new PaymentCsvImporter(cfg, client).run(Path.of(args[0]));
        System.out.printf("done: created=%d alreadyExisted=%d skipped=%d failed=%d%n",
                s.created(), s.alreadyExisted(), s.skipped(), s.failed());
        System.exit(s.failed() == 0 ? 0 : 1);
    }

    public Stats run(Path csv) throws IOException {
        List<Row> rows = parse(Files.readAllLines(csv, StandardCharsets.UTF_8));
        Set<String> done = loadJournal();

        Stats stats = new Stats(0, 0, 0, 0);
        try (BufferedWriter journal = Files.newBufferedWriter(
                cfg.journal(), StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {

            for (Row row : rows) {
                String key = journalKey(row);
                if (done.contains(key)) {
                    stats = stats.plusSkipped();
                    log(row, "SKIP (already in journal)");
                    continue;
                }
                Outcome o = send(row);
                switch (o) {
                    case CREATED -> {
                        journal.write(key); journal.newLine(); journal.flush();
                        stats = stats.plusCreated();
                    }
                    case ALREADY_EXISTS -> {
                        journal.write(key); journal.newLine(); journal.flush();
                        stats = stats.plusAlready();
                    }
                    case PERMANENT_FAILURE -> stats = stats.plusFailed();
                }
            }
        }
        return stats;
    }

    // ---- one row -> the API, with retries -----------------------------------

    private enum Outcome { CREATED, ALREADY_EXISTS, PERMANENT_FAILURE }

    private Outcome send(Row row) {
        HttpRequest request = HttpRequest.newBuilder(
                        cfg.baseUrl().resolve("/api/v1/payments"))
                .timeout(cfg.requestTimeout())
                .header("Content-Type", "application/json")
                .header("Store-Id", row.storeId())
                .header("Idempotency-Key", row.idempotencyKey())
                .POST(HttpRequest.BodyPublishers.ofString(row.toJson()))
                .build();

        for (int attempt = 1; attempt <= cfg.maxAttempts(); attempt++) {
            try {
                HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
                int code = resp.statusCode();

                if (code == 201) { log(row, "CREATED (201)"); return Outcome.CREATED; }
                if (code == 200) { log(row, "ALREADY EXISTS (200, idempotent replay)"); return Outcome.ALREADY_EXISTS; }

                if (isRetryable(code)) {
                    log(row, "transient " + code + " (attempt " + attempt + ")");
                    if (attempt < cfg.maxAttempts()) { sleep(backoff(attempt, resp)); continue; }
                    log(row, "GAVE UP after " + attempt + " attempts (last " + code + ")");
                    return Outcome.PERMANENT_FAILURE;
                }

                // 400 / 422 validation, 401/403/404, etc. -> never retry, bad data or misconfig.
                log(row, "PERMANENT " + code + " -> " + oneLine(resp.body()));
                return Outcome.PERMANENT_FAILURE;

            } catch (IOException | InterruptedException e) {
                // connection refused, reset, read/connect timeout -> transient
                if (e instanceof InterruptedException) Thread.currentThread().interrupt();
                log(row, "I/O failure: " + e.getClass().getSimpleName()
                        + " (attempt " + attempt + ")");
                if (attempt < cfg.maxAttempts()) { sleep(backoff(attempt, null)); continue; }
                log(row, "GAVE UP after " + attempt + " attempts (" + e.getClass().getSimpleName() + ")");
                return Outcome.PERMANENT_FAILURE;
            }
        }
        return Outcome.PERMANENT_FAILURE;
    }

    private static boolean isRetryable(int code) {
        return code == 408 || code == 429 || (code >= 500 && code <= 599);
    }

    /** Capped exponential backoff with full jitter; honours Retry-After on 429 when present. */
    private Duration backoff(int attempt, HttpResponse<String> resp) {
        if (resp != null && resp.statusCode() == 429) {
            Optional<String> ra = resp.headers().firstValue("Retry-After");
            if (ra.isPresent()) {
                try { return Duration.ofSeconds(Long.parseLong(ra.get().trim())); }
                catch (NumberFormatException ignore) { /* fall through */ }
            }
        }
        long expMs = cfg.baseBackoff().toMillis() * (1L << (attempt - 1));
        long cappedMs = Math.min(expMs, cfg.maxBackoff().toMillis());
        long jittered = ThreadLocalRandom.current().nextLong(0, cappedMs + 1); // full jitter
        return Duration.ofMillis(jittered);
    }

    private static void sleep(Duration d) {
        try { Thread.sleep(d.toMillis()); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    // ---- journal ------------------------------------------------------------

    private Set<String> loadJournal() throws IOException {
        if (!Files.exists(cfg.journal())) return new HashSet<>();
        return new HashSet<>(Files.readAllLines(cfg.journal(), StandardCharsets.UTF_8));
    }

    private static String journalKey(Row r) {
        return r.storeId() + "|" + r.idempotencyKey();
    }

    // ---- CSV parsing --------------------------------------------------------

    /**
     * Expected header (order-independent):
     * storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
     * idempotencyKey and loyaltyCardId may be blank.
     */
    private static List<Row> parse(List<String> lines) {
        if (lines.isEmpty()) return List.of();
        List<String> header = splitCsv(lines.get(0));
        int iStore   = header.indexOf("storeId");
        int iKey     = header.indexOf("idempotencyKey");
        int iCoffee  = header.indexOf("coffeeType");
        int iPrice   = header.indexOf("price");
        int iCur     = header.indexOf("currency");
        int iLoyalty = header.indexOf("loyaltyCardId");
        if (iStore < 0 || iCoffee < 0 || iPrice < 0 || iCur < 0) {
            throw new IllegalArgumentException(
                    "CSV header must include at least storeId, coffeeType, price, currency");
        }

        List<Row> rows = new ArrayList<>();
        for (int line = 1; line < lines.size(); line++) {
            String raw = lines.get(line);
            if (raw.isBlank()) continue;
            List<String> c = splitCsv(raw);

            String storeId = at(c, iStore);
            String coffee  = at(c, iCoffee);
            String price   = at(c, iPrice);
            String cur     = at(c, iCur);
            String loyalty = iLoyalty >= 0 ? at(c, iLoyalty) : "";
            String key     = iKey >= 0 ? at(c, iKey) : "";

            new BigDecimal(price); // fail fast on non-numeric price

            if (key.isBlank()) {
                // Deterministic per (file content + position): a re-run of the SAME
                // file produces the SAME key, so retries stay idempotent. Distinct
                // rows never collapse, even if their amounts/coffees match.
                key = UUID.nameUUIDFromBytes(
                        (storeId + "|" + line + "|" + raw).getBytes(StandardCharsets.UTF_8))
                        .toString();
            }
            rows.add(new Row(storeId, key, coffee, price, cur, loyalty));
        }
        return rows;
    }

    private static String at(List<String> cols, int i) {
        return (i >= 0 && i < cols.size()) ? cols.get(i).trim() : "";
    }

    /** Minimal RFC-4180-ish splitter: handles quoted fields and "" escapes. */
    private static List<String> splitCsv(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (inQuotes) {
                if (ch == '"') {
                    if (i + 1 < line.length() && line.charAt(i + 1) == '"') { cur.append('"'); i++; }
                    else inQuotes = false;
                } else cur.append(ch);
            } else {
                if (ch == '"') inQuotes = true;
                else if (ch == ',') { out.add(cur.toString()); cur.setLength(0); }
                else cur.append(ch);
            }
        }
        out.add(cur.toString());
        return out;
    }

    // ---- row model + JSON ---------------------------------------------------

    private record Row(String storeId, String idempotencyKey, String coffeeType,
                       String price, String currency, String loyaltyCardId) {

        String toJson() {
            StringBuilder b = new StringBuilder("{");
            b.append("\"coffeeType\":\"").append(esc(coffeeType)).append("\",");
            b.append("\"price\":").append(price).append(","); // numeric, kept verbatim
            b.append("\"currency\":\"").append(esc(currency)).append("\"");
            if (loyaltyCardId != null && !loyaltyCardId.isBlank()) {
                b.append(",\"loyaltyCardId\":\"").append(esc(loyaltyCardId)).append("\"");
            }
            return b.append("}").toString();
        }

        private static String esc(String s) {
            return s.replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }

    // ---- logging ------------------------------------------------------------

    private static void log(Row r, String msg) {
        System.out.printf("[%s/%s] %s%n", r.storeId(), r.idempotencyKey(), msg);
    }

    private static String oneLine(String body) {
        if (body == null) return "";
        String s = body.replace("\n", " ").trim();
        return s.length() > 200 ? s.substring(0, 200) + "..." : s;
    }
}
