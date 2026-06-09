package space.harbour.cloud.propagation;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.nio.file.Path;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PaymentPropagationIntegrationTest {

	@LocalServerPort
	private int port;

	@Autowired
	private WebApplicationContext context;

	private MockMvc mockMvc;

	@BeforeEach
	void setUp() {
		mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
	}

	@Test
	void propagatesCsvPaymentsToCentralSystem() throws Exception {
		Path csvPath = Path.of("src/test/resources/payments.csv");
		String baseUrl = "http://localhost:" + port;

		PaymentPropagator propagator = new PaymentPropagator(
				new CsvPaymentReader(),
				new PaymentApiClient(baseUrl));

		PaymentPropagator.PropagationResult firstRun = propagator.propagate(csvPath);
		org.junit.jupiter.api.Assertions.assertTrue(firstRun.allSucceeded());
		org.junit.jupiter.api.Assertions.assertEquals(2, firstRun.successCount());

		mockMvc.perform(get("/api/v1/payments")
						.param("storeId", "store-test-01")
						.accept(MediaType.APPLICATION_JSON))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$", hasSize(2)))
				.andExpect(jsonPath("$[0].coffeeType").exists())
				.andExpect(jsonPath("$[1].coffeeType").exists());

		PaymentPropagator.PropagationResult secondRun = propagator.propagate(csvPath);
		org.junit.jupiter.api.Assertions.assertTrue(secondRun.allSucceeded());
		org.junit.jupiter.api.Assertions.assertEquals(2, secondRun.successCount());
		org.junit.jupiter.api.Assertions.assertTrue(
				secondRun.rows().stream().allMatch(row -> row.statusCode() == 200));

		mockMvc.perform(get("/api/v1/payments")
						.param("storeId", "store-test-01")
						.accept(MediaType.APPLICATION_JSON))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$", hasSize(2)));
	}
}
