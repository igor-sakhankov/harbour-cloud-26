package space.harbour.cloud.payments;

import java.time.Instant;

public record BulkJob(String id, String status, int totalCount, Instant createdAt) {

    public static final String PENDING = "PENDING";
    public static final String DONE    = "DONE";
}
