package space.harbour.cloud.payments;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Service to parse payment details from CSV and reliably propagate them to the central system.
 */
@Service
public class PaymentPropagationService {

	private static final Logger log = LoggerFactory.getLogger(PaymentPropagationService.class);

	private final RestClient.Builder restClientBuilder;
	private final String externalUrl;

	public PaymentPropagationService(RestClient.Builder restClientBuilder,
									 @Value("${payments.external-system.url}") String externalUrl) {
		this.restClientBuilder = restClientBuilder;
		this.externalUrl = externalUrl;
	}

	/**
	 * Propagates payments from the provided CSV input stream.
	 */
	public PropagationResponse propagate(InputStream csvInputStream) throws IOException {
		RestClient restClient = this.restClientBuilder.baseUrl(externalUrl).build();
		List<CsvPaymentParser.CsvRecord> records = CsvPaymentParser.parse(csvInputStream);

		int total = records.size();
		int successCount = 0;
		int failureCount = 0;
		List<PropagationResponse.FailedRecordDetail> failures = new ArrayList<>();

		for (CsvPaymentParser.CsvRecord record : records) {
			String idempotencyKey = record.get("idempotencyKey");
			try {
				validateRecord(record);

				// Prepare request payload
				PaymentRequest requestPayload = new PaymentRequest(
						CoffeeType.valueOf(record.get("coffeeType").toUpperCase()),
						new BigDecimal(record.get("price")),
						record.get("currency"),
						record.get("loyaltyCardId")
				);

				String storeId = record.get("storeId");

				// Send with reliability (retries and backoff)
				sendWithRetry(restClient, storeId, idempotencyKey, requestPayload);
				successCount++;

			} catch (ValidationException e) {
				log.warn("Validation failed for CSV record at line {}: {}", record.lineNumber(), e.getMessage());
				failureCount++;
				failures.add(new PropagationResponse.FailedRecordDetail(
						record.lineNumber(),
						idempotencyKey,
						"Validation Error: " + e.getMessage()
				));
			} catch (Exception e) {
				log.error("Failed to propagate record at line {} (key: {}): {}", record.lineNumber(), idempotencyKey, e.getMessage());
				failureCount++;
				failures.add(new PropagationResponse.FailedRecordDetail(
						record.lineNumber(),
						idempotencyKey,
						"Propagation Error: " + e.getMessage()
				));
			}
		}

		return new PropagationResponse(total, successCount, failureCount, failures);
	}

	private void sendWithRetry(RestClient restClient, String storeId, String idempotencyKey, PaymentRequest request) throws Exception {
		int maxAttempts = 4;
		int attempt = 0;
		long backoffMs = 100;
		boolean success = false;
		Exception lastException = null;

		while (attempt < maxAttempts && !success) {
			attempt++;
			try {
				ResponseEntity<PaymentResponse> response = restClient.post()
						.header(PaymentController.STORE_ID_HEADER, storeId)
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, idempotencyKey)
						.contentType(MediaType.APPLICATION_JSON)
						.body(request)
						.retrieve()
						.toEntity(PaymentResponse.class);

				if (response.getStatusCode().is2xxSuccessful()) {
					success = true;
					log.info("Successfully propagated payment with key {} (attempt {})", idempotencyKey, attempt);
				} else {
					throw new RuntimeException("Server returned status: " + response.getStatusCode());
				}
			} catch (HttpClientErrorException e) {
				// 4xx errors - client-side validation or error. Do not retry!
				log.warn("Non-retryable client error propagating key {} (attempt {}): {}", idempotencyKey, attempt, e.getMessage());
				throw new Exception("External system rejected request with 4xx: " + e.getResponseBodyAsString(), e);
			} catch (HttpServerErrorException e) {
				// 5xx errors - server error. Retry!
				log.warn("Retryable server error propagating key {} (attempt {}): {}", idempotencyKey, attempt, e.getMessage());
				lastException = e;
			} catch (Exception e) {
				// Network error (timeout, connection refused, etc.) - Retry!
				log.warn("Retryable network/unknown error propagating key {} (attempt {}): {}", idempotencyKey, attempt, e.getMessage());
				lastException = e;
			}

			if (!success && attempt < maxAttempts) {
				log.info("Backing off for {} ms before retry attempt {}", backoffMs, attempt + 1);
				Thread.sleep(backoffMs);
				backoffMs *= 2;
			}
		}

		if (!success) {
			throw new Exception("Failed to propagate payment after " + maxAttempts + " attempts. Last error: " +
					(lastException != null ? lastException.getMessage() : "Unknown"), lastException);
		}
	}

	private void validateRecord(CsvPaymentParser.CsvRecord record) throws ValidationException {
		String idempotencyKey = record.get("idempotencyKey");
		if (idempotencyKey == null || idempotencyKey.isBlank()) {
			throw new ValidationException("idempotencyKey is required");
		}

		String storeId = record.get("storeId");
		if (storeId == null || storeId.isBlank()) {
			throw new ValidationException("storeId is required");
		}

		String coffeeTypeStr = record.get("coffeeType");
		if (coffeeTypeStr == null || coffeeTypeStr.isBlank()) {
			throw new ValidationException("coffeeType is required");
		}
		try {
			CoffeeType.valueOf(coffeeTypeStr.toUpperCase());
		} catch (IllegalArgumentException e) {
			throw new ValidationException("Invalid coffee type: " + coffeeTypeStr);
		}

		String priceStr = record.get("price");
		if (priceStr == null || priceStr.isBlank()) {
			throw new ValidationException("price is required");
		}
		BigDecimal price;
		try {
			price = new BigDecimal(priceStr);
		} catch (NumberFormatException e) {
			throw new ValidationException("price must be a valid number: " + priceStr);
		}
		if (price.compareTo(BigDecimal.ZERO) <= 0) {
			throw new ValidationException("price must be greater than zero");
		}
		if (price.scale() > 2) {
			throw new ValidationException("price may have at most 2 decimal places");
		}

		String currency = record.get("currency");
		if (currency == null || currency.isBlank()) {
			throw new ValidationException("currency is required");
		}
		if (!currency.matches("^[A-Z]{3}$")) {
			throw new ValidationException("currency must be a 3-letter ISO-4217 code, e.g. EUR");
		}

		String loyaltyCardId = record.get("loyaltyCardId");
		if (loyaltyCardId == null || loyaltyCardId.isBlank()) {
			throw new ValidationException("loyaltyCardId is required");
		}
	}

	private static class ValidationException extends Exception {
		public ValidationException(String message) {
			super(message);
		}
	}
}
