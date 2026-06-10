package space.harbour.cloud.importer;

import space.harbour.cloud.payments.CoffeeType;
import space.harbour.cloud.payments.PaymentRequest;

import java.math.BigDecimal;

record ParsedPaymentRow(
		int lineNumber,
		String storeId,
		String idempotencyKey,
		CoffeeType coffeeType,
		BigDecimal price,
		String currency,
		String loyaltyCardId
) {

	PaymentRequest toPaymentRequest() {
		return new PaymentRequest(coffeeType, price, currency, loyaltyCardId);
	}
}
