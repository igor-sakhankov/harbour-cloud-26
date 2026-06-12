package space.harbour.cloud.loadbalancer;

/**
 * Checks whether a backend instance can currently receive traffic.
 */
public interface HealthCheckClient {

	boolean isHealthy(BackendInstance backend);
}
