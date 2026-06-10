package space.harbour.cloud.importer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
class PaymentImportService {

	private final CsvPaymentParser parser;
	private final CentralPaymentClient centralPaymentClient;

	@Autowired
	PaymentImportService(CentralPaymentClient centralPaymentClient) {
		this(new CsvPaymentParser(), centralPaymentClient);
	}

	PaymentImportService(CsvPaymentParser parser, CentralPaymentClient centralPaymentClient) {
		this.parser = parser;
		this.centralPaymentClient = centralPaymentClient;
	}

	PaymentImportResponse importCsv(MultipartFile file) {
		if (file == null || file.isEmpty()) {
			throw new PaymentImportException("CSV file is required");
		}

		List<ParsedPaymentRow> rows = parse(file);
		if (rows.isEmpty()) {
			return PaymentImportResponse.empty();
		}

		int created = 0;
		int replayed = 0;
		List<PaymentImportFailure> failures = new ArrayList<>();
		for (ParsedPaymentRow row : rows) {
			try {
				ImportedPaymentStatus status = centralPaymentClient.register(row);
				if (status == ImportedPaymentStatus.CREATED) {
					created++;
				}
				else {
					replayed++;
				}
			}
			catch (CentralPaymentException ex) {
				failures.add(new PaymentImportFailure(row.lineNumber(), ex.getMessage()));
			}
		}

		return new PaymentImportResponse(rows.size(), created, replayed, failures.size(), List.copyOf(failures));
	}

	private List<ParsedPaymentRow> parse(MultipartFile file) {
		try {
			return parser.parse(file.getInputStream());
		}
		catch (IOException ex) {
			throw new PaymentImportException("Failed to read CSV file", ex);
		}
	}
}
