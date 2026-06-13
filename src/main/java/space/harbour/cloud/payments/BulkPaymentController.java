package space.harbour.cloud.payments;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/payments/bulk")
public class BulkPaymentController {

    private final BulkPaymentService bulkService;

    public BulkPaymentController(BulkPaymentService bulkService) {
        this.bulkService = bulkService;
    }

    /**
     * Accepts a list of payments, stores the job, and returns immediately.
     * Processing happens asynchronously; poll the status endpoint to track completion.
     */
    @PostMapping
    public ResponseEntity<Map<String, String>> submit(@Valid @RequestBody List<@Valid BulkPaymentItem> items) {
        String jobId = bulkService.submit(items);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(Map.of("jobId", jobId));
    }

    /**
     * Returns the current status of a bulk job — PENDING or DONE.
     */
    @GetMapping("/{jobId}")
    public BulkJob status(@PathVariable String jobId) {
        return bulkService.status(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "No job with id " + jobId));
    }
}
