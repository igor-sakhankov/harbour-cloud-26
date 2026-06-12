package space.harbour.cloud.propagation;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * HTTP client that registers payments with the Central System.
 *
 * <p>Retries transient failures while reusing the same idempotency key so
 * duplicate payments are not created.
 */
public class PaymentApiClient {

	private static final int MAX_ATTEMPTS = 3;
	private static final Duration RETRY_BACKOFF = Duration.ofMillis(200);

	private final HttpClient httpClient;
	private final String paymentsUrl;

	public PaymentApiClient(String baseUrl) {
		this(baseUrl, HttpClient.newBuilder()
				.connectTimeout(Duration.ofSeconds(5))
				.build());
	}

	public PaymentApiClient(String baseUrl, HttpClient httpClient) {
		String normalized = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
		this.paymentsUrl = normalized + "/api/v1/payments";
		this.httpClient = httpClient;
	}

	/**
	 * @return HTTP status code (201 for created, 200 for replayed)
	 */
	public int registerPayment(CsvPaymentRecord record) throws IOException, InterruptedException {
		String jsonBody = """
				{
				  "coffeeType": "%s",
				  "price": %s,
				  "currency": "%s",
				  "loyaltyCardId": "%s"
				}
				""".formatted(
				record.coffeeType(),
				record.price().toPlainString(),
				record.currency(),
				escapeJson(record.loyaltyCardId()));

		HttpRequest request = HttpRequest.newBuilder()
				.uri(URI.create(paymentsUrl))
				.timeout(Duration.ofSeconds(10))
				.header("Content-Type", "application/json")
				.header("Store-Id", record.storeId())
				.header("Idempotency-Key", record.idempotencyKey())
				.POST(HttpRequest.BodyPublishers.ofString(jsonBody))
				.build();

		IOException lastIo = null;
		for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
			try {
				HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
				int status = response.statusCode();
				if (status == 201 || status == 200) {
					return status;
				}
				if (!isRetryable(status) || attempt == MAX_ATTEMPTS) {
					throw new PaymentApiException(status, response.body());
				}
			} catch (IOException e) {
				lastIo = e;
				if (attempt == MAX_ATTEMPTS) {
					throw e;
				}
			}
			Thread.sleep(RETRY_BACKOFF.multipliedBy(attempt).toMillis());
		}
		if (lastIo != null) {
			throw lastIo;
		}
		throw new IllegalStateException("registerPayment exhausted retries without result");
	}

	private boolean isRetryable(int status) {
		return status == 408 || status == 429 || status >= 500;
	}

	private String escapeJson(String value) {
		return value.replace("\\", "\\\\").replace("\"", "\\\"");
	}

	public static class PaymentApiException extends IOException {
		private final int statusCode;

		public PaymentApiException(int statusCode, String body) {
			super("Payment API returned HTTP " + statusCode + ": " + body);
			this.statusCode = statusCode;
		}

		public int statusCode() {
			return statusCode;
		}
	}
}
