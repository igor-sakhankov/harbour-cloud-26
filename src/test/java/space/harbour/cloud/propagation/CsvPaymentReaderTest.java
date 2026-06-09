package space.harbour.cloud.propagation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import space.harbour.cloud.payments.CoffeeType;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CsvPaymentReaderTest {

	private final CsvPaymentReader reader = new CsvPaymentReader();

	@Test
	void readsValidCsv(@TempDir Path tempDir) throws IOException {
		Path csv = tempDir.resolve("payments.csv");
		Files.writeString(csv, """
				storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
				store-london-01,order-001,LATTE,3.50,EUR,card-123
				""");

		var records = reader.read(csv);

		assertEquals(1, records.size());
		CsvPaymentRecord record = records.getFirst();
		assertEquals("store-london-01", record.storeId());
		assertEquals("order-001", record.idempotencyKey());
		assertEquals(CoffeeType.LATTE, record.coffeeType());
		assertEquals(new BigDecimal("3.50"), record.price());
		assertEquals("EUR", record.currency());
		assertEquals("card-123", record.loyaltyCardId());
	}

	@Test
	void rejectsUnexpectedHeader(@TempDir Path tempDir) throws IOException {
		Path csv = tempDir.resolve("bad-header.csv");
		Files.writeString(csv, """
				store,coffee,price
				store-1,LATTE,3.50
				""");

		assertThrows(IllegalArgumentException.class, () -> reader.read(csv));
	}

	@Test
	void rejectsUnknownCoffeeType(@TempDir Path tempDir) throws IOException {
		Path csv = tempDir.resolve("bad-coffee.csv");
		Files.writeString(csv, """
				storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
				store-1,key-1,MOCHA_LATTE,3.50,EUR,card-1
				""");

		IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> reader.read(csv));
		assertEquals("Line 2: unknown coffeeType 'MOCHA_LATTE'", ex.getMessage());
	}

	@Test
	void rejectsBlankStoreId(@TempDir Path tempDir) throws IOException {
		Path csv = tempDir.resolve("blank-store.csv");
		Files.writeString(csv, """
				storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId
				,key-1,LATTE,3.50,EUR,card-1
				""");

		IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> reader.read(csv));
		assertEquals("Line 2: storeId must not be blank", ex.getMessage());
	}
}
