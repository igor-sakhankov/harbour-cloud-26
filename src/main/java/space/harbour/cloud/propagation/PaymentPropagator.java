package space.harbour.cloud.propagation;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Reads a CSV notebook export and propagates each payment to the Central System.
 */
public class PaymentPropagator {

	private final CsvPaymentReader reader;
	private final PaymentApiClient client;

	public PaymentPropagator(CsvPaymentReader reader, PaymentApiClient client) {
		this.reader = reader;
		this.client = client;
	}

	public PropagationResult propagate(Path csvPath) throws IOException {
		List<CsvPaymentRecord> records = reader.read(csvPath);
		List<RowResult> results = new ArrayList<>();

		for (int i = 0; i < records.size(); i++) {
			CsvPaymentRecord record = records.get(i);
			int rowNumber = i + 2;
			try {
				int status = client.registerPayment(record);
				results.add(RowResult.success(rowNumber, record.idempotencyKey(), status));
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
				results.add(RowResult.failure(rowNumber, record.idempotencyKey(), e.getMessage()));
				break;
			} catch (Exception e) {
				results.add(RowResult.failure(rowNumber, record.idempotencyKey(), e.getMessage()));
			}
		}

		return new PropagationResult(results);
	}

	public record RowResult(int rowNumber, String idempotencyKey, boolean success, int statusCode, String error) {
		static RowResult success(int rowNumber, String idempotencyKey, int statusCode) {
			return new RowResult(rowNumber, idempotencyKey, true, statusCode, null);
		}

		static RowResult failure(int rowNumber, String idempotencyKey, String error) {
			return new RowResult(rowNumber, idempotencyKey, false, 0, error);
		}
	}

	public record PropagationResult(List<RowResult> rows) {
		public boolean allSucceeded() {
			return rows.stream().allMatch(RowResult::success);
		}

		public long successCount() {
			return rows.stream().filter(RowResult::success).count();
		}

		public long failureCount() {
			return rows.stream().filter(row -> !row.success()).count();
		}
	}
}
