package space.harbour.cloud.payments;

import org.springframework.stereotype.Repository;

import java.sql.Timestamp;

/**
 * Persists payments to the Postgres shard determined by storeId.
 * Uses ON CONFLICT DO NOTHING for idempotency — same guarantee as the in-memory store.
 */
@Repository
public class ShardedPaymentRepository {

    private final ShardRouter router;

    public ShardedPaymentRepository(ShardRouter router) {
        this.router = router;
    }

    public void save(Payment payment) {
        router.forKey(payment.storeId()).update("""
                INSERT INTO payments(payment_id, store_id, coffee_type, price, currency, loyalty_card_id, idempotency_key, registered_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT (store_id, idempotency_key) DO NOTHING
                """,
                payment.paymentId(),
                payment.storeId(),
                payment.coffeeType().name(),
                payment.price(),
                payment.currency(),
                payment.loyaltyCardId(),
                payment.idempotencyKey(),
                Timestamp.from(payment.registeredAt()));
    }
}
