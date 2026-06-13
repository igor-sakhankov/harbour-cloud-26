package space.harbour.cloud.payments;

import java.util.ArrayList;
import java.util.List;

/**
 * Result of a CSV payment import operation.
 */
public record CsvImportResult(
		int totalRecords,
		int successCount,
		List<CsvImportFailure> failures
) {
	public CsvImportResult {
		failures = new ArrayList<>(failures);
	}

	/**
	 * Represents a single failed row from the CSV import.
	 */
	public record CsvImportFailure(
			int rowNumber,
			CsvPaymentRecord record,
			String reason
	) {
	}
}
