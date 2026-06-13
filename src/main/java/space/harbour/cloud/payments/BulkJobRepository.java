package space.harbour.cloud.payments;

import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.util.Optional;

@Repository
public class BulkJobRepository {

    private final ShardRouter router;

    public BulkJobRepository(ShardRouter router) {
        this.router = router;
    }

    public void save(BulkJob job) {
        router.meta().update(
                "INSERT INTO bulk_jobs(id, status, total_count, created_at) VALUES (?,?,?,?)",
                job.id(), job.status(), job.totalCount(), Timestamp.from(job.createdAt()));
    }

    public Optional<BulkJob> findById(String id) {
        return router.meta().query(
                "SELECT id, status, total_count, created_at FROM bulk_jobs WHERE id = ?",
                (rs, n) -> new BulkJob(
                        rs.getString("id"),
                        rs.getString("status"),
                        rs.getInt("total_count"),
                        rs.getTimestamp("created_at").toInstant()),
                id
        ).stream().findFirst();
    }

    public void markDone(String id) {
        router.meta().update("UPDATE bulk_jobs SET status = ? WHERE id = ?", BulkJob.DONE, id);
    }
}
