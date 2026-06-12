package space.harbour.cloud.propagation;

import space.harbour.cloud.payments.CoffeeType;

import java.io.BufferedReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Reads payment rows from a CSV notebook export.
 *
 * <p>Expected header: {@code storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId}
 */
public class CsvPaymentReader {

	private static final String EXPECTED_HEADER =
			"storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId";

	public List<CsvPaymentRecord> read(Path csvPath) throws IOException {
		try (BufferedReader reader = Files.newBufferedReader(csvPath)) {
			String header = reader.readLine();
			if (header == null) {
				throw new IllegalArgumentException("CSV file is empty: " + csvPath);
			}
			if (!header.trim().equals(EXPECTED_HEADER)) {
				throw new IllegalArgumentException(
						"Unexpected CSV header. Expected: " + EXPECTED_HEADER + ", got: " + header);
			}

			List<CsvPaymentRecord> records = new ArrayList<>();
			String line;
			int lineNumber = 1;
			while ((line = reader.readLine()) != null) {
				lineNumber++;
				if (line.isBlank()) {
					continue;
				}
				records.add(parseLine(line, lineNumber));
			}
			return records;
		}
	}

	private CsvPaymentRecord parseLine(String line, int lineNumber) {
		String[] fields = line.split(",", -1);
		if (fields.length != 6) {
			throw new IllegalArgumentException(
					"Line " + lineNumber + ": expected 6 fields, got " + fields.length);
		}

		String storeId = requireNonBlank(fields[0], "storeId", lineNumber);
		String idempotencyKey = requireNonBlank(fields[1], "idempotencyKey", lineNumber);
		CoffeeType coffeeType = parseCoffeeType(fields[2], lineNumber);
		BigDecimal price = parsePrice(fields[3], lineNumber);
		String currency = requireNonBlank(fields[4], "currency", lineNumber);
		String loyaltyCardId = requireNonBlank(fields[5], "loyaltyCardId", lineNumber);

		return new CsvPaymentRecord(storeId, idempotencyKey, coffeeType, price, currency, loyaltyCardId);
	}

	private String requireNonBlank(String value, String fieldName, int lineNumber) {
		if (value == null || value.isBlank()) {
			throw new IllegalArgumentException(
					"Line " + lineNumber + ": " + fieldName + " must not be blank");
		}
		return value.trim();
	}

	private CoffeeType parseCoffeeType(String raw, int lineNumber) {
		String value = requireNonBlank(raw, "coffeeType", lineNumber);
		try {
			return CoffeeType.valueOf(value.trim().toUpperCase(Locale.ROOT));
		} catch (IllegalArgumentException e) {
			throw new IllegalArgumentException(
					"Line " + lineNumber + ": unknown coffeeType '" + value + "'", e);
		}
	}

	private BigDecimal parsePrice(String raw, int lineNumber) {
		String value = requireNonBlank(raw, "price", lineNumber);
		try {
			return new BigDecimal(value.trim());
		} catch (NumberFormatException e) {
			throw new IllegalArgumentException(
					"Line " + lineNumber + ": invalid price '" + value + "'", e);
		}
	}
}
