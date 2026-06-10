package space.harbour.cloud.payments;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Utility for parsing CSV files containing coffee payments.
 */
public class CsvPaymentParser {

	public static List<CsvRecord> parse(InputStream is) throws IOException {
		List<CsvRecord> records = new ArrayList<>();
		try (BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {
			String headerLine = reader.readLine();
			if (headerLine == null) {
				return records;
			}

			// Map headers to column indices
			String[] headers = splitCsv(headerLine);
			Map<String, Integer> headerIndexMap = new HashMap<>();
			for (int i = 0; i < headers.length; i++) {
				headerIndexMap.put(headers[i].trim().toLowerCase(), i);
			}

			String line;
			int lineNumber = 1;
			while ((line = reader.readLine()) != null) {
				lineNumber++;
				if (line.trim().isEmpty()) {
					continue;
				}
				String[] values = splitCsv(line);
				records.add(new CsvRecord(lineNumber, values, headerIndexMap));
			}
		}
		return records;
	}

	private static String[] splitCsv(String line) {
		// Regex to split by commas outside of quotes
		return line.split(",(?=([^\"]*\"[^\"]*\")*[^\"]*$)", -1);
	}

	public record CsvRecord(int lineNumber, String[] values, Map<String, Integer> headerIndexMap) {
		public String get(String columnName) {
			Integer index = headerIndexMap.get(columnName.toLowerCase());
			if (index == null || index >= values.length) {
				return null;
			}
			String val = values[index];
			if (val == null) {
				return null;
			}
			val = val.trim();
			if (val.startsWith("\"") && val.endsWith("\"") && val.length() >= 2) {
				val = val.substring(1, val.length() - 1);
			}
			return val.trim();
		}
	}
}
