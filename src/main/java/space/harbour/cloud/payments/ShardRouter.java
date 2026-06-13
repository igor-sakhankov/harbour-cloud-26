package space.harbour.cloud.payments;

import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Routes writes to the correct Postgres shard by hashing the routing key.
 *
 * Shard 0 also doubles as the metadata node — it holds the bulk_jobs table.
 * All shards hold the payments table.
 */
@Component
public class ShardRouter {

    private final List<JdbcTemplate> shards;

    public ShardRouter(DbConfig config) {
        this.shards = config.shards().stream()
                .map(s -> {
                    HikariDataSource ds = new HikariDataSource();
                    ds.setJdbcUrl(s.url());
                    ds.setUsername(s.username());
                    ds.setPassword(s.password());
                    ds.setInitializationFailTimeout(-1); // skip pool init; retry loop handles connectivity
                    ds.setConnectionTimeout(2000);       // fail fast per attempt so retries are quick
                    return new JdbcTemplate(ds);
                })
                .toList();
    }

    @PostConstruct
    void initSchema() {
        String paymentsDdl = """
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id      TEXT        PRIMARY KEY,
                    store_id        TEXT        NOT NULL,
                    coffee_type     TEXT        NOT NULL,
                    price           NUMERIC(12,2) NOT NULL,
                    currency        TEXT        NOT NULL,
                    loyalty_card_id TEXT        NOT NULL,
                    idempotency_key TEXT        NOT NULL,
                    registered_at   TIMESTAMPTZ NOT NULL,
                    UNIQUE (store_id, idempotency_key)
                )
                """;
        String jobsDdl = """
                CREATE TABLE IF NOT EXISTS bulk_jobs (
                    id          TEXT        PRIMARY KEY,
                    status      TEXT        NOT NULL,
                    total_count INTEGER     NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL
                )
                """;

        for (JdbcTemplate t : shards) {
            executeWithRetry(t, paymentsDdl);
        }
        executeWithRetry(shards.get(0), jobsDdl);
    }

    /** Routes by string key — any shard-worthy field works (storeId, paymentId, etc.). */
    public JdbcTemplate forKey(String key) {
        return shards.get(Math.abs(key.hashCode()) % shards.size());
    }

    /** Shard 0 — hosts bulk_jobs and serves as the coordination point. */
    public JdbcTemplate meta() {
        return shards.get(0);
    }

    private void executeWithRetry(JdbcTemplate t, String ddl) {
        Exception last = null;
        for (int i = 0; i < 15; i++) {
            try {
                t.execute(ddl);
                return;
            } catch (Exception e) {
                last = e;
                try { Thread.sleep(1000); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); return; }
            }
        }
        throw new IllegalStateException("Postgres not reachable after retries", last);
    }
}
