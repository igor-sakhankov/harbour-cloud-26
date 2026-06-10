package space.harbour.cloud.payments;

import java.util.List;

/**
 * The API response shape for the CSV propagation endpoint.
 */
public record PropagationResponse(
		int totalRecords,
		int successfulRecords,
		int failedRecords,
		List<FailedRecordDetail> failures
) {
	public record FailedRecordDetail(
			int lineNumber,
			String idempotencyKey,
			String error
	) {}
}
