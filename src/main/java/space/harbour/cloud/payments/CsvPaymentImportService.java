package space.harbour.cloud.payments;

import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Service for importing and processing CSV payment files.
 * Parses CSV, validates records, and sends them to the payment API.
 */
@Service
public class CsvPaymentImportService {

	private static final String EXPECTED_HEADER = "storeId,coffeeType,price,currency,loyaltyCardId,idempotencyKey";
	private static final String PAYMENT_API_URL = "http://localhost:8080/api/v1/payments";
	private static final int MAX_RETRIES = 3;

	private final RestTemplate restTemplate;

	public CsvPaymentImportService(RestTemplate restTemplate) {
		this.restTemplate = restTemplate;
	}

	/**
	 * Imports CSV payments from an input stream.
	 */
	public CsvImportResult importPayments(InputStream fileInputStream) throws IOException {
		List<CsvPaymentRecord> records = new ArrayList<>();
		List<CsvImportResult.CsvImportFailure> failures = new ArrayList<>();

		try (BufferedReader reader = new BufferedReader(new InputStreamReader(fileInputStream))) {
			String headerLine = reader.readLine();

			// Validate header
			if (headerLine == null || headerLine.isEmpty()) {
				failures.add(new CsvImportResult.CsvImportFailure(
						1,
						null,
						"Invalid CSV header. Expected: " + EXPECTED_HEADER
				));
				return new CsvImportResult(0, 0, failures);
			}

			if (!headerLine.equalsIgnoreCase(EXPECTED_HEADER)) {
				failures.add(new CsvImportResult.CsvImportFailure(
						1,
						null,
						"Invalid CSV header. Expected: " + EXPECTED_HEADER
				));
				return new CsvImportResult(0, 0, failures);
			}

			// Parse data rows
			int rowNumber = 2;
			String line;
			while ((line = reader.readLine()) != null) {
				if (line.trim().isEmpty()) {
					rowNumber++;
					continue;
				}

				String[] fields = line.split(",", -1);

				// Validate field count
				if (fields.length != 6) {
					failures.add(new CsvImportResult.CsvImportFailure(
							rowNumber,
							null,
							"Expected 6 fields but got " + fields.length
					));
					rowNumber++;
					continue;
				}

				// Parse and validate record
				CsvPaymentRecord record = parseRecord(fields, rowNumber, failures);
				if (record != null) {
					records.add(record);
				}

				rowNumber++;
			}
		}

		// Send validated records to API
		int successCount = 0;
		for (CsvPaymentRecord record : records) {
			if (sendPaymentWithRetry(record, failures)) {
				successCount++;
			}
		}

		int totalRecords = records.size() + failures.size();
		return new CsvImportResult(totalRecords, successCount, failures);
	}

	private CsvPaymentRecord parseRecord(String[] fields, int rowNumber, List<CsvImportResult.CsvImportFailure> failures) {
		String storeId = fields[0].trim();
		String coffeeType = fields[1].trim();
		String priceStr = fields[2].trim();
		String currency = fields[3].trim();
		String loyaltyCardId = fields[4].trim();
		String idempotencyKey = fields[5].trim();

		// Validate storeId
		if (storeId.isEmpty()) {
			failures.add(new CsvImportResult.CsvImportFailure(
					rowNumber,
					null,
					"Empty storeId"
			));
			return null;
		}

		// Validate coffeeType
		try {
			CoffeeType.valueOf(coffeeType);
		} catch (IllegalArgumentException e) {
			failures.add(new CsvImportResult.CsvImportFailure(
					rowNumber,
					null,
					"Invalid coffeeType: " + coffeeType + ". Valid types: [ESPRESSO, DOUBLE_ESPRESSO, AMERICANO, LATTE, CAPPUCCINO, FLAT_WHITE, MOCHA, CORTADO, MACCHIATO, COLD_BREW]"
			));
			return null;
		}

		// Validate price
		BigDecimal price;
		try {
			price = new BigDecimal(priceStr);
			if (price.compareTo(BigDecimal.ZERO) <= 0) {
				failures.add(new CsvImportResult.CsvImportFailure(
						rowNumber,
						null,
						"price must be greater than zero"
				));
				return null;
			}
		} catch (NumberFormatException e) {
			failures.add(new CsvImportResult.CsvImportFailure(
					rowNumber,
					null,
					"Invalid price format"
			));
			return null;
		}

		// Validate currency
		if (!currency.matches("^[A-Z]{3}$")) {
			failures.add(new CsvImportResult.CsvImportFailure(
					rowNumber,
					null,
					"currency must be a 3-letter ISO-4217 code, e.g. EUR"
			));
			return null;
		}

		// Create record
		CsvPaymentRecord record = new CsvPaymentRecord(storeId, coffeeType, price, currency, loyaltyCardId, idempotencyKey);
		return record;
	}

	private boolean sendPaymentWithRetry(CsvPaymentRecord record, List<CsvImportResult.CsvImportFailure> failures) {
		int attempts = 0;
		long backoffMs = 500;

		while (attempts < MAX_RETRIES) {
			try {
				sendPayment(record);
				return true;
			} catch (Exception e) {
				attempts++;
				if (attempts >= MAX_RETRIES) {
					failures.add(new CsvImportResult.CsvImportFailure(
							-1,
							record,
							"Failed to send payment after " + MAX_RETRIES + " attempts: " + e.getMessage()
					));
					return false;
				}

				try {
					Thread.sleep(backoffMs);
				} catch (InterruptedException ie) {
					Thread.currentThread().interrupt();
				}

				backoffMs *= 2;
			}
		}

		return false;
	}

	private void sendPayment(CsvPaymentRecord record) {
		HttpHeaders headers = new HttpHeaders();
		headers.setContentType(MediaType.APPLICATION_JSON);
		headers.set("Store-Id", record.storeId());
		headers.set("Idempotency-Key", record.idempotencyKey());

		PaymentRequest paymentRequest = new PaymentRequest(
				CoffeeType.valueOf(record.coffeeType()),
				record.price(),
				record.currency(),
				record.loyaltyCardId()
		);

		HttpEntity<PaymentRequest> request = new HttpEntity<>(paymentRequest, headers);
		restTemplate.postForEntity(PAYMENT_API_URL, request, PaymentResponse.class);
	}
}
