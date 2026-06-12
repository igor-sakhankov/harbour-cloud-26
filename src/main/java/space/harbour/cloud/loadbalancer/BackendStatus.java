package space.harbour.cloud.loadbalancer;

import java.net.URI;
import java.time.Instant;

/**
 * Current health information for a configured backend.
 */
public record BackendStatus(
		String id,
		URI baseUrl,
		boolean healthy,
		Instant checkedAt
) {
}
