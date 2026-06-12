package space.harbour.cloud.importer;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Reliability tests for {@link PaymentCsvImporter} against a self-contained fake
 * "Central System". No Spring context, no Docker, no Toxiproxy — the fake server
 * fails on demand so we can assert retry + idempotency behaviour deterministically.
 */
class PaymentCsvImporterTest {

    private HttpServer server;
    private int port;

    // request counters & idempotency store, keyed by Idempotency-Key
    private final AtomicInteger totalCalls = new AtomicInteger();
    private final Map<String, Integer> calls = new ConcurrentHashMap<>();
    private final Map<String, String> stored = new ConcurrentHashMap<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/api/v1/payments", exchange -> {
            totalCalls.incrementAndGet();
            String key = exchange.getRequestHeaders().getFirst("Idempotency-Key");
            int n = calls.merge(key, 1, Integer::sum);

            // Fail the first two attempts of every key, then succeed -> forces retries.
            byte[] body;
            int status;
            if (stored.containsKey(key)) {
                status = 200;                       // idempotent replay
                body = stored.get(key).getBytes(StandardCharsets.UTF_8);
            } else if (n < 3) {
                status = 503;                       // transient -> importer must retry
                body = "{\"error\":\"unavailable\"}".getBytes(StandardCharsets.UTF_8);
            } else {
                String payment = "{\"paymentId\":\"" + key + "\"}";
                stored.put(key, payment);
                status = 201;
                body = payment.getBytes(StandardCharsets.UTF_8);
            }
            exchange.sendResponseHeaders(status, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        port = server.getAddress().getPort();
    }

    @AfterEach
    void stop() { server.stop(0); }

    private PaymentCsvImporter.Config cfg(Path journal) {
        return new PaymentCsvImporter.Config(
                URI.create("http://localhost:" + port),
                6,
                Duration.ofMillis(1),   // tiny backoff so the test is fast
                Duration.ofMillis(5),
                Duration.ofSeconds(2),
                journal);
    }

    @Test
    void retriesTransientFailuresThenCreates(@TempDir Path tmp) throws IOException {
        Path csv = writeCsv(tmp, List.of(
                "storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId",
                "store-1,k-001,LATTE,3.50,EUR,card-1",
                "store-1,k-002,ESPRESSO,2.00,EUR,"));
        Path journal = tmp.resolve("journal.txt");

        var stats = new PaymentCsvImporter(cfg(journal), HttpClient.newHttpClient()).run(csv);

        assertEquals(2, stats.created(), "both rows created after retries");
        assertEquals(0, stats.failed());
        // each key was tried 3 times (2x503 + 1x201)
        assertEquals(3, calls.get("k-001"));
        assertEquals(3, calls.get("k-002"));
    }

    @Test
    void reRunIsIdempotentAndCreatesNoDuplicates(@TempDir Path tmp) throws IOException {
        Path csv = writeCsv(tmp, List.of(
                "storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId",
                "store-1,k-100,MOCHA,3.80,EUR,"));
        Path journal = tmp.resolve("journal.txt");

        var first = new PaymentCsvImporter(cfg(journal), HttpClient.newHttpClient()).run(csv);
        assertEquals(1, first.created());

        // Second run over the same file: journal short-circuits it, server is never asked again.
        int callsAfterFirst = totalCalls.get();
        var second = new PaymentCsvImporter(cfg(journal), HttpClient.newHttpClient()).run(csv);

        assertEquals(1, second.skipped(), "row already in journal -> skipped");
        assertEquals(0, second.created());
        assertEquals(callsAfterFirst, totalCalls.get(), "no extra server calls on re-run");
    }

    @Test
    void reRunWithoutJournalStillNoDuplicateViaServerIdempotency(@TempDir Path tmp) throws IOException {
        Path csv = writeCsv(tmp, List.of(
                "storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId",
                "store-1,k-200,CORTADO,2.90,EUR,"));

        // Two separate runs, each with a FRESH journal -> the journal can't help.
        // Safety must come from the server deduping on the Idempotency-Key.
        new PaymentCsvImporter(cfg(tmp.resolve("j1.txt")), HttpClient.newHttpClient()).run(csv);
        var second = new PaymentCsvImporter(cfg(tmp.resolve("j2.txt")), HttpClient.newHttpClient()).run(csv);

        assertEquals(1, second.alreadyExisted(), "server replays the original with 200");
        assertEquals(0, second.created());
        assertEquals(1, stored.size(), "exactly one payment ever stored");
        assertTrue(stored.containsKey("k-200"));
    }

    private static Path writeCsv(Path tmp, List<String> lines) throws IOException {
        Path csv = tmp.resolve("payments.csv");
        Files.write(csv, lines, StandardCharsets.UTF_8);
        return csv;
    }
}
