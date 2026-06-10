package space.harbour.cloud.importer;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * REST API for importing notebook CSV exports into the Central System.
 */
@RestController
@RequestMapping("/api/v1/payment-imports")
class PaymentImportController {

	private final PaymentImportService paymentImportService;

	PaymentImportController(PaymentImportService paymentImportService) {
		this.paymentImportService = paymentImportService;
	}

	/**
	 * Imports a CSV file with columns:
	 * storeId,idempotencyKey,coffeeType,price,currency,loyaltyCardId.
	 *
	 * <p>The idempotencyKey column is optional; when absent or blank, a stable
	 * key is derived from the row number and content so retrying the same file is safe.
	 */
	@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
	PaymentImportResponse importPayments(@RequestParam("file") MultipartFile file) {
		return paymentImportService.importCsv(file);
	}

	@ExceptionHandler(PaymentImportException.class)
	ResponseEntity<ProblemDetail> onPaymentImportException(PaymentImportException ex) {
		ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ex.getMessage());
		problem.setTitle("Payment import failed");
		return ResponseEntity.badRequest().body(problem);
	}
}
