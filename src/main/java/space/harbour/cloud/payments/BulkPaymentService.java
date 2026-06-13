package space.harbour.cloud.payments;

import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
public class BulkPaymentService {

    private final BulkJobRepository jobRepo;
    private final BulkPaymentProcessor processor;
    private final Clock clock;

    public BulkPaymentService(BulkJobRepository jobRepo, BulkPaymentProcessor processor, Clock clock) {
        this.jobRepo = jobRepo;
        this.processor = processor;
        this.clock = clock;
    }

    public String submit(List<BulkPaymentItem> items) {
        String jobId = UUID.randomUUID().toString();
        jobRepo.save(new BulkJob(jobId, BulkJob.PENDING, items.size(), clock.instant()));
        processor.process(jobId, items);
        return jobId;
    }

    public Optional<BulkJob> status(String jobId) {
        return jobRepo.findById(jobId);
    }
}
