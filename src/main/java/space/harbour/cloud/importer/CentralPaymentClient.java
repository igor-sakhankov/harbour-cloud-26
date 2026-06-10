package space.harbour.cloud.importer;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
class CentralPaymentClient {

	private static final String STORE_ID_HEADER = "Store-Id";
	private static final String IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";

	private final RestClient restClient;
	private final int maxAttempts;

	CentralPaymentClient(RestClient.Builder builder, ImporterProperties properties) {
		this.restClient = builder
				.baseUrl(properties.getCentralSystemBaseUrl().toString())
				.build();
		this.maxAttempts = properties.getMaxAttempts();
	}

	ImportedPaymentStatus register(ParsedPaymentRow row) {
		for (int attempt = 1; attempt <= maxAttempts; attempt++) {
			try {
				ResponseEntity<Void> response = restClient.post()
						.uri("/api/v1/payments")
						.header(STORE_ID_HEADER, row.storeId())
						.header(IDEMPOTENCY_KEY_HEADER, row.idempotencyKey())
						.body(row.toPaymentRequest())
						.retrieve()
						.toBodilessEntity();

				if (response.getStatusCode() == HttpStatus.CREATED) {
					return ImportedPaymentStatus.CREATED;
				}
				if (response.getStatusCode() == HttpStatus.OK) {
					return ImportedPaymentStatus.REPLAYED;
				}
				throw new CentralPaymentException("Unexpected Central System status: " + response.getStatusCode());
			}
			catch (ResourceAccessException ex) {
				if (attempt == maxAttempts) {
					throw new CentralPaymentException("Central System is not reachable", ex);
				}
			}
			catch (RestClientResponseException ex) {
				if (!isRetryable(ex) || attempt == maxAttempts) {
					throw new CentralPaymentException("Central System rejected payment: HTTP " + ex.getStatusCode(), ex);
				}
			}
			catch (RestClientException ex) {
				throw new CentralPaymentException("Failed to call Central System", ex);
			}
		}
		throw new CentralPaymentException("Failed to call Central System");
	}

	private boolean isRetryable(RestClientResponseException ex) {
		return ex.getStatusCode().is5xxServerError()
				|| ex.getStatusCode() == HttpStatus.TOO_MANY_REQUESTS;
	}
}
