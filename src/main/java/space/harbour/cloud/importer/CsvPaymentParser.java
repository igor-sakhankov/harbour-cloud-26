package space.harbour.cloud.importer;

import space.harbour.cloud.payments.CoffeeType;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Parses notebook-exported CSV files into payments ready to send downstream.
 */
final class CsvPaymentParser {

	private static final List<String> REQUIRED_COLUMNS = List.of(
			"storeId", "coffeeType", "price", "currency", "loyaltyCardId");

	List<ParsedPaymentRow> parse(InputStream inputStream) {
		List<RawCsvRow> csvRows = readRows(inputStream);
		if (csvRows.isEmpty()) {
			throw new PaymentImportException("CSV file is empty");
		}

		List<String> headers = csvRows.getFirst().values();
		Map<String, Integer> headerIndex = headerIndex(headers);
		for (String requiredColumn : REQUIRED_COLUMNS) {
			if (!headerIndex.containsKey(requiredColumn)) {
				throw new PaymentImportException("Missing required CSV column: " + requiredColumn);
			}
		}

		List<ParsedPaymentRow> rows = new ArrayList<>();
		for (int i = 1; i < csvRows.size(); i++) {
			RawCsvRow rawRow = csvRows.get(i);
			if (rawRow.values().stream().allMatch(String::isBlank)) {
				continue;
			}
			rows.add(parsePaymentRow(rawRow, headerIndex));
		}
		return rows;
	}

	private ParsedPaymentRow parsePaymentRow(RawCsvRow row, Map<String, Integer> headerIndex) {
		String storeId = required(row, headerIndex, "storeId");
		String coffeeType = required(row, headerIndex, "coffeeType");
		String price = required(row, headerIndex, "price");
		String currency = required(row, headerIndex, "currency").toUpperCase(Locale.ROOT);
		String loyaltyCardId = required(row, headerIndex, "loyaltyCardId");
		String idempotencyKey = optional(row, headerIndex, "idempotencyKey");
		if (idempotencyKey.isBlank()) {
			idempotencyKey = deterministicIdempotencyKey(
					row.lineNumber(), storeId, coffeeType, price, currency, loyaltyCardId);
		}

		try {
			return new ParsedPaymentRow(
					row.lineNumber(),
					storeId,
					idempotencyKey,
					CoffeeType.valueOf(coffeeType.toUpperCase(Locale.ROOT)),
					new BigDecimal(price),
					currency,
					loyaltyCardId
			);
		}
		catch (IllegalArgumentException ex) {
			throw new PaymentImportException("Invalid payment data on CSV line " + row.lineNumber(), ex);
		}
	}

	private String required(RawCsvRow row, Map<String, Integer> headerIndex, String column) {
		String value = optional(row, headerIndex, column);
		if (value.isBlank()) {
			throw new PaymentImportException("Missing value for " + column + " on CSV line " + row.lineNumber());
		}
		return value;
	}

	private String optional(RawCsvRow row, Map<String, Integer> headerIndex, String column) {
		Integer index = headerIndex.get(column);
		if (index == null || index >= row.values().size()) {
			return "";
		}
		return row.values().get(index).trim();
	}

	private Map<String, Integer> headerIndex(List<String> headers) {
		Map<String, Integer> indexes = new HashMap<>();
		for (int i = 0; i < headers.size(); i++) {
			indexes.put(headers.get(i).trim(), i);
		}
		return indexes;
	}

	private List<RawCsvRow> readRows(InputStream inputStream) {
		try (BufferedReader reader = new BufferedReader(
				new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
			List<RawCsvRow> rows = new ArrayList<>();
			String line;
			int lineNumber = 0;
			while ((line = reader.readLine()) != null) {
				lineNumber++;
				if (lineNumber == 1 && line.startsWith("\uFEFF")) {
					line = line.substring(1);
				}
				rows.add(new RawCsvRow(lineNumber, parseLine(line, lineNumber)));
			}
			return rows;
		}
		catch (IOException ex) {
			throw new PaymentImportException("Failed to read CSV file", ex);
		}
	}

	private List<String> parseLine(String line, int lineNumber) {
		List<String> values = new ArrayList<>();
		StringBuilder value = new StringBuilder();
		boolean quoted = false;
		for (int i = 0; i < line.length(); i++) {
			char current = line.charAt(i);
			if (current == '"') {
				if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') {
					value.append('"');
					i++;
				}
				else {
					quoted = !quoted;
				}
			}
			else if (current == ',' && !quoted) {
				values.add(value.toString());
				value.setLength(0);
			}
			else {
				value.append(current);
			}
		}
		if (quoted) {
			throw new PaymentImportException("Unclosed quoted value on CSV line " + lineNumber);
		}
		values.add(value.toString());
		return values;
	}

	private String deterministicIdempotencyKey(
			int lineNumber, String storeId, String coffeeType, String price, String currency, String loyaltyCardId) {
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			byte[] hash = digest.digest(String.join("|",
					Integer.toString(lineNumber), storeId, coffeeType.toUpperCase(Locale.ROOT), price, currency, loyaltyCardId)
					.getBytes(StandardCharsets.UTF_8));
			return "csv-" + HexFormat.of().formatHex(hash, 0, 16);
		}
		catch (NoSuchAlgorithmException ex) {
			throw new IllegalStateException("SHA-256 is not available", ex);
		}
	}

	private record RawCsvRow(int lineNumber, List<String> values) {
	}
}
