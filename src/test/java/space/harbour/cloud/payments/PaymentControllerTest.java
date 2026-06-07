package space.harbour.cloud.payments;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class PaymentControllerTest {

	@Autowired
	private WebApplicationContext context;

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
}
