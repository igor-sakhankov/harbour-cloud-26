package space.harbour.cloud.importer;

import org.junit.jupiter.api.Test;
import space.harbour.cloud.payments.CoffeeType;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CsvPaymentParserTest {

	private final CsvPaymentParser parser = new CsvPaymentParser();

	@Test
	void parsesValidCsvWithExplicitIdempotencyKey() {
		String csv = """
				storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
				store-1,key-1,LATTE,3.50,EUR,card-1
				""";

		List<ParsedPaymentRow> rows = parser.parse(input(csv));

		assertEquals(1, rows.size());
		ParsedPaymentRow row = rows.getFirst();
		assertEquals(2, row.lineNumber());
		assertEquals("store-1", row.storeId());
		assertEquals("key-1", row.idempotencyKey());
		assertEquals(CoffeeType.LATTE, row.coffeeType());
		assertEquals("3.50", row.price().toPlainString());
		assertEquals("EUR", row.currency());
		assertEquals("card-1", row.loyaltyCardId());
	}

	@Test
	void missingIdempotencyKeyUsesStableRowContentHash() {
		String csv = """
				storeId,coffeeType,price,currency,loyaltyCardId
				store-1,LATTE,3.50,EUR,card-1
				""";

		ParsedPaymentRow first = parser.parse(input(csv)).getFirst();
		ParsedPaymentRow second = parser.parse(input(csv)).getFirst();

		assertFalse(first.idempotencyKey().isBlank());
		assertEquals(first.idempotencyKey(), second.idempotencyKey());
	}

	@Test
	void generatedIdempotencyKeysKeepIdenticalRowsDistinct() {
		String csv = """
				storeId,coffeeType,price,currency,loyaltyCardId
				store-1,LATTE,3.50,EUR,card-1
				store-1,LATTE,3.50,EUR,card-1
				""";

		List<ParsedPaymentRow> rows = parser.parse(input(csv));

		assertNotEquals(rows.get(0).idempotencyKey(), rows.get(1).idempotencyKey());
	}

	@Test
	void missingRequiredColumnIsRejected() {
		String csv = """
				storeId,coffeeType,price,currency
				store-1,LATTE,3.50,EUR
				""";

		PaymentImportException ex = assertThrows(PaymentImportException.class, () -> parser.parse(input(csv)));

		assertEquals("Missing required CSV column: loyaltyCardId", ex.getMessage());
	}

	private ByteArrayInputStream input(String csv) {
		return new ByteArrayInputStream(csv.getBytes(StandardCharsets.UTF_8));
	}
}
