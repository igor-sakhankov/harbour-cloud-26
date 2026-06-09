package space.harbour.cloud.propagation;

import java.nio.file.Path;

/**
 * CLI entry point for propagating end-of-day CSV payments to the Central System.
 *
 * <p>Usage: {@code PaymentPropagationApp <csvFile> [baseUrl]}
 */
public class PaymentPropagationApp {

	private static final String DEFAULT_BASE_URL = "http://localhost:8080";

	public static void main(String[] args) {
		if (args.length < 1 || args.length > 2) {
			System.err.println("Usage: PaymentPropagationApp <csvFile> [baseUrl]");
			System.exit(1);
		}

		Path csvPath = Path.of(args[0]);
		String baseUrl = args.length == 2 ? args[1] : DEFAULT_BASE_URL;

		CsvPaymentReader reader = new CsvPaymentReader();
		PaymentApiClient client = new PaymentApiClient(baseUrl);
		PaymentPropagator propagator = new PaymentPropagator(reader, client);

		try {
			PaymentPropagator.PropagationResult result = propagator.propagate(csvPath);
			for (PaymentPropagator.RowResult row : result.rows()) {
				if (row.success()) {
					System.out.printf(
							"Row %d (%s): propagated (HTTP %d)%n",
							row.rowNumber(), row.idempotencyKey(), row.statusCode());
				} else {
					System.err.printf(
							"Row %d (%s): failed - %s%n",
							row.rowNumber(), row.idempotencyKey(), row.error());
				}
			}
			System.out.printf(
					"Done: %d succeeded, %d failed%n",
					result.successCount(), result.failureCount());

			if (!result.allSucceeded()) {
				System.exit(1);
			}
		} catch (Exception e) {
			System.err.println("Propagation failed: " + e.getMessage());
			System.exit(1);
		}
	}
}
