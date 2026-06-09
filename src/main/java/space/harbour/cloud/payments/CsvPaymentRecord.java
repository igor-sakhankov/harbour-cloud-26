package space.harbour.cloud.payments;

import java.math.BigDecimal;

/**
 * Represents a single row from the CSV payment import file.
 */
public record CsvPaymentRecord(
		String storeId,
		String coffeeType,
		BigDecimal price,
		String currency,
		String loyaltyCardId,
		String idempotencyKey
) {
}
