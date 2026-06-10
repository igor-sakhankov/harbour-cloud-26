package space.harbour.cloud.importer;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Queue;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class PaymentImportControllerTest {

	private MockMvc mockMvc(PaymentImportService service) {
		return MockMvcBuilders.standaloneSetup(new PaymentImportController(service)).build();
	}

	@Test
	void importsCsvFileWith200() throws Exception {
		PaymentImportService service = new PaymentImportService(
				new CsvPaymentParser(),
				new StubCentralPaymentClient(ImportedPaymentStatus.CREATED, ImportedPaymentStatus.REPLAYED));

		MockMultipartFile file = new MockMultipartFile(
				"file",
				"payments.csv",
				"text/csv",
				"""
						storeId,coffeeType,price,currency,loyaltyCardId
						store-1,LATTE,3.50,EUR,card-1
						store-1,AMERICANO,2.90,EUR,card-2
						""".getBytes(StandardCharsets.UTF_8));

		mockMvc(service).perform(multipart("/api/v1/payment-imports").file(file))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$.totalRows").value(2))
				.andExpect(jsonPath("$.created").value(1))
				.andExpect(jsonPath("$.replayed").value(1))
				.andExpect(jsonPath("$.failed").value(0));
	}

	@Test
	void invalidCsvFileIsRejected() throws Exception {
		PaymentImportService service = new PaymentImportService(
				new CsvPaymentParser(),
				new StubCentralPaymentClient());

		MockMultipartFile file = new MockMultipartFile(
				"file",
				"payments.csv",
				"text/csv",
				"coffeeType,price,currency,loyaltyCardId\nLATTE,3.50,EUR,card-1\n"
						.getBytes(StandardCharsets.UTF_8));

		mockMvc(service).perform(multipart("/api/v1/payment-imports")
						.file(file)
						.contentType(MediaType.MULTIPART_FORM_DATA))
				.andExpect(status().isBadRequest())
				.andExpect(jsonPath("$.title").value("Payment import failed"))
				.andExpect(jsonPath("$.detail", containsString("storeId")));
	}

	private static final class StubCentralPaymentClient extends CentralPaymentClient {

		private final Queue<ImportedPaymentStatus> statuses;

		StubCentralPaymentClient(ImportedPaymentStatus... statuses) {
			super(RestClient.builder(), new ImporterProperties());
			this.statuses = new ArrayDeque<>(Arrays.asList(statuses));
		}

		@Override
		ImportedPaymentStatus register(ParsedPaymentRow row) {
			return statuses.remove();
		}
	}
}
