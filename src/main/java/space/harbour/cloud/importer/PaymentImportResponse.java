package space.harbour.cloud.importer;

import java.util.List;

public record PaymentImportResponse(
		int totalRows,
		int created,
		int replayed,
		int failed,
		List<PaymentImportFailure> failures
) {

	static PaymentImportResponse empty() {
		return new PaymentImportResponse(0, 0, 0, 0, List.of());
	}
}
