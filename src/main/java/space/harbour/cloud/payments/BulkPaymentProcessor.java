package space.harbour.cloud.payments;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Runs the actual bulk job work off the request thread.
 *
 * Kept separate from BulkPaymentService so that @Async's AOP proxy kicks in
 * correctly — self-invocation within the same bean bypasses the proxy.
 */
@Component
class BulkPaymentProcessor {

    private final PaymentService paymentService;
    private final ShardedPaymentRepository shardedRepo;
    private final BulkJobRepository jobRepo;

    BulkPaymentProcessor(PaymentService paymentService,
                          ShardedPaymentRepository shardedRepo,
                          BulkJobRepository jobRepo) {
        this.paymentService = paymentService;
        this.shardedRepo = shardedRepo;
        this.jobRepo = jobRepo;
    }

    @Async
    void process(String jobId, List<BulkPaymentItem> items) {
        for (BulkPaymentItem item : items) {
            PaymentService.RegistrationResult result = paymentService.register(
                    item.storeId(),
                    item.idempotencyKey(),
                    new PaymentRequest(item.coffeeType(), item.price(), item.currency(), item.loyaltyCardId()));
            shardedRepo.save(result.payment());
        }
        jobRepo.markDone(jobId);
    }
}
