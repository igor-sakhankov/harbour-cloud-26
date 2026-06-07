package space.harbour.cloud.payments;

import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Registers coffee payments.
 *
 * <p>Registration is idempotent: the caller supplies an idempotency token and,
 * if the same token is seen twice for the same store, the original payment is
 * returned rather than a new one being created. This protects against the
 * client retrying after a network timeout - a classic at-least-once delivery
 * problem in distributed systems.
 */
@Service
public class PaymentService {

	private final PaymentRepository repository;
	private final Clock clock;

	public PaymentService(PaymentRepository repository, Clock clock) {
		this.repository = repository;
		this.clock = clock;
	}

	/**
	 * Registers a payment for the given store.
	 *
	 * @return the result, flagging whether the payment was newly created or
	 *         replayed from a previous identical request.
	 */
	public RegistrationResult register(String storeId, String idempotencyKey, PaymentRequest request) {
		String effectiveKey = (idempotencyKey != null && !idempotencyKey.isBlank())
				? idempotencyKey
				: UUID.randomUUID().toString();
		Payment candidate = new Payment(
				UUID.randomUUID().toString(),
				storeId,
				request.coffeeType(),
				request.price(),
				request.currency(),
				request.loyaltyCardId(),
				effectiveKey,
				clock.instant()
		);

		Payment stored = repository.saveIfAbsent(candidate);
		boolean created = stored.paymentId().equals(candidate.paymentId());
		return new RegistrationResult(stored, created);
	}

	/**
	 * Looks up a previously registered payment by its id.
	 */
	public Optional<Payment> findById(String paymentId) {
		return repository.findById(paymentId);
	}

	public List<Payment> findByStoreId(String storeId) {
		return repository.findByStoreId(storeId);
	}

	/**
	 * @param payment the persisted payment
	 * @param created true if this call created the payment, false if it was a
	 *                replay of an earlier request with the same idempotency token
	 */
	public record RegistrationResult(Payment payment, boolean created) {
	}
}
