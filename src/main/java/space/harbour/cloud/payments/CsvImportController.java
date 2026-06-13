package space.harbour.cloud.payments;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

/**
 * REST API for importing CSV payment files.
 */
@RestController
@RequestMapping("/api/v1/payments")
public class CsvImportController {

	private final CsvPaymentImportService csvPaymentImportService;

	public CsvImportController(CsvPaymentImportService csvPaymentImportService) {
		this.csvPaymentImportService = csvPaymentImportService;
	}

	/**
	 * Imports payments from a CSV file.
	 * 
	 * Expects multipart/form-data with a "file" field containing the CSV.
	 */
	@PostMapping("/import")
	public ResponseEntity<CsvImportResult> importPaymentsFromCsv(
			@RequestParam("file") MultipartFile file) {

		// Validate file
		if (file == null || file.isEmpty()) {
			return ResponseEntity.status(HttpStatus.BAD_REQUEST)
					.body(new CsvImportResult(0, 0, java.util.List.of(
							new CsvImportResult.CsvImportFailure(0, null, "File is empty")
					)));
		}

		if (!file.getOriginalFilename().endsWith(".csv")) {
			return ResponseEntity.status(HttpStatus.BAD_REQUEST)
					.body(new CsvImportResult(0, 0, java.util.List.of(
							new CsvImportResult.CsvImportFailure(0, null, "File must be a CSV file")
					)));
		}

		try {
			CsvImportResult result = csvPaymentImportService.importPayments(file.getInputStream());
			return ResponseEntity.ok(result);
		} catch (IOException e) {
			return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
					.body(new CsvImportResult(0, 0, java.util.List.of(
							new CsvImportResult.CsvImportFailure(0, null, "File read error: " + e.getMessage())
					)));
		}
	}
}
