package space.harbour.cloud.propagation;

import space.harbour.cloud.payments.CoffeeType;

import java.math.BigDecimal;

/**
 * One payment row parsed from the end-of-day CSV notebook export.
 */
public record CsvPaymentRecord(
		String storeId,
		String idempotencyKey,
		CoffeeType coffeeType,
		BigDecimal price,
		String currency,
		String loyaltyCardId
) {
}
