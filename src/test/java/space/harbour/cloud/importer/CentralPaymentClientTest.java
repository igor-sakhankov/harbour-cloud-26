package space.harbour.cloud.importer;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import space.harbour.cloud.payments.CoffeeType;

import java.math.BigDecimal;
import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

class CentralPaymentClientTest {

	@Test
	void registerRetriesTransientFailuresAndReturnsCreated() {
		RestClient.Builder builder = RestClient.builder();
		MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
		CentralPaymentClient client = new CentralPaymentClient(builder, properties(3));

		server.expect(once(), requestTo("http://central.test/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andRespond(withStatus(HttpStatus.INTERNAL_SERVER_ERROR));
		server.expect(once(), requestTo("http://central.test/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(header("Store-Id", "store-1"))
				.andExpect(header("Idempotency-Key", "key-1"))
				.andRespond(withStatus(HttpStatus.CREATED).contentType(MediaType.APPLICATION_JSON));

		ImportedPaymentStatus status = client.register(row());

		assertEquals(ImportedPaymentStatus.CREATED, status);
		server.verify();
	}

	@Test
	void registerDoesNotRetryBadRequests() {
		RestClient.Builder builder = RestClient.builder();
		MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
		CentralPaymentClient client = new CentralPaymentClient(builder, properties(3));

		server.expect(once(), requestTo("http://central.test/api/v1/payments"))
				.andRespond(withStatus(HttpStatus.BAD_REQUEST));

		assertThrows(CentralPaymentException.class, () -> client.register(row()));
		server.verify();
	}

	private ImporterProperties properties(int maxAttempts) {
		ImporterProperties properties = new ImporterProperties();
		properties.setCentralSystemBaseUrl(URI.create("http://central.test"));
		properties.setMaxAttempts(maxAttempts);
		return properties;
	}

	private ParsedPaymentRow row() {
		return new ParsedPaymentRow(
				2,
				"store-1",
				"key-1",
				CoffeeType.LATTE,
				new BigDecimal("3.50"),
				"EUR",
				"card-1");
	}
}
