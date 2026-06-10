package space.harbour.cloud.payments;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.match.MockRestRequestMatchers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;
import org.springframework.web.context.WebApplicationContext;

import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withBadRequest;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class PaymentControllerTest {

	@Autowired
	private WebApplicationContext context;

	@Autowired
	private RestClient.Builder restClientBuilder;

	private MockRestServiceServer mockRestServer;

	@BeforeEach
	void setUp() {
		mockRestServer = MockRestServiceServer.bindTo(restClientBuilder).build();
	}

	private MockMvc mockMvc() {
		return MockMvcBuilders.webAppContextSetup(context).build();
	}

	private static final String VALID_BODY = """
			{
			  "coffeeType": "LATTE",
			  "price": 3.50,
			  "currency": "EUR",
			  "loyaltyCardId": "card-123"
			}
			""";

	@Test
	void registersNewPaymentWith201() throws Exception {
		mockMvc().perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, "store-london-01")
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, "key-new-1")
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isCreated())
				.andExpect(jsonPath("$.paymentId", notNullValue()))
				.andExpect(jsonPath("$.storeId").value("store-london-01"))
				.andExpect(jsonPath("$.coffeeType").value("LATTE"))
				.andExpect(jsonPath("$.currency").value("EUR"));
	}

	@Test
	void replayingSameIdempotencyKeyReturnsSamePaymentWith200() throws Exception {
		MockMvc mvc = mockMvc();
		String store = "store-paris-02";
		String key = "key-retry-9";

		String first = mvc.perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, store)
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, key)
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isCreated())
				.andReturn().getResponse().getContentAsString();

		String firstId = com.jayway.jsonpath.JsonPath.read(first, "$.paymentId");

		mvc.perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, store)
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, key)
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.paymentId").value(firstId));
	}

	@Test
	void missingStoreIdHeaderIsRejected() throws Exception {
		mockMvc().perform(post("/api/v1/payments")
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, "key-x")
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isBadRequest());
	}

	@Test
	void missingIdempotencyKeyCreatesNewPaymentEachTime() throws Exception {
		MockMvc mvc = mockMvc();

		String first = mvc.perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, "store-no-key")
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isCreated())
				.andReturn().getResponse().getContentAsString();

		String second = mvc.perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, "store-no-key")
						.contentType(MediaType.APPLICATION_JSON)
						.content(VALID_BODY))
				.andExpect(status().isCreated())
				.andReturn().getResponse().getContentAsString();

		String firstId = com.jayway.jsonpath.JsonPath.read(first, "$.paymentId");
		String secondId = com.jayway.jsonpath.JsonPath.read(second, "$.paymentId");
		org.junit.jupiter.api.Assertions.assertNotEquals(firstId, secondId);
	}

	@Test
	void invalidCurrencyIsRejected() throws Exception {
		String badBody = VALID_BODY.replace("\"EUR\"", "\"euro\"");
		mockMvc().perform(post("/api/v1/payments")
						.header(PaymentController.STORE_ID_HEADER, "store-1")
						.header(PaymentController.IDEMPOTENCY_KEY_HEADER, "key-bad-currency")
						.contentType(MediaType.APPLICATION_JSON)
						.content(badBody))
				.andExpect(status().isBadRequest());
	}

	@Test
	void propagatesValidCsvPaymentsSuccessfully() throws Exception {
		String csvContent = """
				idempotencyKey,storeId,coffeeType,price,currency,loyaltyCardId
				key-csv-1,store-london-01,LATTE,3.50,EUR,card-123
				key-csv-2,store-london-01,CAPPUCCINO,4.20,EUR,card-456
				""";

		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-csv-1"))
				.andRespond(withStatus(HttpStatus.CREATED)
						.contentType(MediaType.APPLICATION_JSON)
						.body("{\"paymentId\":\"id-1\"}"));

		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-csv-2"))
				.andRespond(withStatus(HttpStatus.CREATED)
						.contentType(MediaType.APPLICATION_JSON)
						.body("{\"paymentId\":\"id-2\"}"));

		MockMultipartFile csvFile = new MockMultipartFile("file", "payments.csv",
				MediaType.TEXT_PLAIN_VALUE, csvContent.getBytes(StandardCharsets.UTF_8));

		mockMvc().perform(multipart("/api/v1/payments/propagate").file(csvFile))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.totalRecords").value(2))
				.andExpect(jsonPath("$.successfulRecords").value(2))
				.andExpect(jsonPath("$.failedRecords").value(0));

		mockRestServer.verify();
	}

	@Test
	void propagatesCsvWithValidationErrorsSkipsInvalidAndReportsFailures() throws Exception {
		String csvContent = """
				idempotencyKey,storeId,coffeeType,price,currency,loyaltyCardId
				key-csv-ok,store-london-01,LATTE,3.50,EUR,card-123
				key-csv-bad,store-london-01,UNKNOWN_COFFEE,3.50,EUR,card-123
				""";

		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-csv-ok"))
				.andRespond(withStatus(HttpStatus.CREATED)
						.contentType(MediaType.APPLICATION_JSON)
						.body("{\"paymentId\":\"id-ok\"}"));

		MockMultipartFile csvFile = new MockMultipartFile("file", "payments.csv",
				MediaType.TEXT_PLAIN_VALUE, csvContent.getBytes(StandardCharsets.UTF_8));

		mockMvc().perform(multipart("/api/v1/payments/propagate").file(csvFile))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.totalRecords").value(2))
				.andExpect(jsonPath("$.successfulRecords").value(1))
				.andExpect(jsonPath("$.failedRecords").value(1))
				.andExpect(jsonPath("$.failures[0].lineNumber").value(3))
				.andExpect(jsonPath("$.failures[0].idempotencyKey").value("key-csv-bad"))
				.andExpect(jsonPath("$.failures[0].error", containsString("Validation Error")));

		mockRestServer.verify();
	}

	@Test
	void propagatesCsvAndRetriesOnTransientErrorsWithExponentialBackoff() throws Exception {
		String csvContent = """
				idempotencyKey,storeId,coffeeType,price,currency,loyaltyCardId
				key-retry,store-london-01,LATTE,3.50,EUR,card-123
				""";

		// Attempt 1: 500 server error
		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-retry"))
				.andRespond(withServerError());

		// Attempt 2: 201 Created
		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-retry"))
				.andRespond(withStatus(HttpStatus.CREATED)
						.contentType(MediaType.APPLICATION_JSON)
						.body("{\"paymentId\":\"id-retry-ok\"}"));

		MockMultipartFile csvFile = new MockMultipartFile("file", "payments.csv",
				MediaType.TEXT_PLAIN_VALUE, csvContent.getBytes(StandardCharsets.UTF_8));

		mockMvc().perform(multipart("/api/v1/payments/propagate").file(csvFile))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.totalRecords").value(1))
				.andExpect(jsonPath("$.successfulRecords").value(1))
				.andExpect(jsonPath("$.failedRecords").value(0));

		mockRestServer.verify();
	}

	@Test
	void propagatesCsvDoesNotRetryOnClientErrorsAndAbortsRecord() throws Exception {
		String csvContent = """
				idempotencyKey,storeId,coffeeType,price,currency,loyaltyCardId
				key-400,store-london-01,LATTE,3.50,EUR,card-123
				""";

		// External system returns 400 Bad Request
		mockRestServer.expect(ExpectedCount.once(), requestTo("http://localhost:9091/api/v1/payments"))
				.andExpect(method(HttpMethod.POST))
				.andExpect(MockRestRequestMatchers.header("Store-Id", "store-london-01"))
				.andExpect(MockRestRequestMatchers.header("Idempotency-Key", "key-400"))
				.andRespond(withBadRequest().body("{\"detail\":\"Card inactive\"}"));

		MockMultipartFile csvFile = new MockMultipartFile("file", "payments.csv",
				MediaType.TEXT_PLAIN_VALUE, csvContent.getBytes(StandardCharsets.UTF_8));

		mockMvc().perform(multipart("/api/v1/payments/propagate").file(csvFile))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.totalRecords").value(1))
				.andExpect(jsonPath("$.successfulRecords").value(0))
				.andExpect(jsonPath("$.failedRecords").value(1))
				.andExpect(jsonPath("$.failures[0].error", containsString("4xx")));

		mockRestServer.verify();
	}
}
