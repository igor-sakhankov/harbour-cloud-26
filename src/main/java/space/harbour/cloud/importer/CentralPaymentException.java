package space.harbour.cloud.importer;

class CentralPaymentException extends RuntimeException {

	CentralPaymentException(String message) {
		super(message);
	}

	CentralPaymentException(String message, Throwable cause) {
		super(message, cause);
	}
}
