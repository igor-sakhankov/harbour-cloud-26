package space.harbour.cloud.importer;

class PaymentImportException extends RuntimeException {

	PaymentImportException(String message) {
		super(message);
	}

	PaymentImportException(String message, Throwable cause) {
		super(message, cause);
	}
}
