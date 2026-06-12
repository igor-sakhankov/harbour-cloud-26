package space.harbour.cloud.loadbalancer;

import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Round-robin selector that only returns backends marked healthy.
 */
@Service
public class RoundRobinRedirectLoadBalancer implements RedirectLoadBalancer {

	private final List<BackendInstance> backends;
	private final Map<String, BackendStatus> statuses = new ConcurrentHashMap<>();
	private final AtomicInteger cursor = new AtomicInteger();
	private final HealthCheckClient healthCheckClient;
	private final Clock clock;

	public RoundRobinRedirectLoadBalancer(
			LoadBalancerProperties properties,
			HealthCheckClient healthCheckClient,
			Clock clock) {
		this.backends = parseBackends(properties.getInstances());
		this.healthCheckClient = healthCheckClient;
		this.clock = clock;
		this.backends.forEach(backend -> statuses.put(backend.id(),
				new BackendStatus(backend.id(), backend.baseUrl(), false, Instant.EPOCH)));
	}

	@PostConstruct
	public void initializeHealth() {
		refreshHealth();
	}

	@Scheduled(fixedDelayString = "${load-balancer.health-check-interval-ms:5000}")
	public void refreshHealth() {
		for (BackendInstance backend : backends) {
			boolean healthy = healthCheckClient.isHealthy(backend);
			statuses.put(backend.id(), new BackendStatus(
					backend.id(), backend.baseUrl(), healthy, clock.instant()));
		}
	}

	@Override
	public Optional<BackendInstance> chooseBackend() {
		List<BackendInstance> healthyBackends = backends.stream()
				.filter(backend -> {
					BackendStatus status = statuses.get(backend.id());
					return status != null && status.healthy();
				})
				.toList();

		if (healthyBackends.isEmpty()) {
			return Optional.empty();
		}

		int index = Math.floorMod(cursor.getAndIncrement(), healthyBackends.size());
		return Optional.of(healthyBackends.get(index));
	}

	@Override
	public List<BackendStatus> backends() {
		return statuses.values().stream()
				.sorted(Comparator.comparing(BackendStatus::id))
				.toList();
	}

	private static List<BackendInstance> parseBackends(List<String> configuredBackends) {
		List<BackendInstance> parsed = new ArrayList<>();
		for (int i = 0; i < configuredBackends.size(); i++) {
			String value = configuredBackends.get(i);
			if (value == null || value.isBlank()) {
				continue;
			}
			URI uri = URI.create(value.trim());
			if (uri.getScheme() == null || uri.getHost() == null) {
				throw new IllegalArgumentException("Backend instance must be an absolute URI: " + value);
			}
			parsed.add(new BackendInstance("backend-" + (parsed.size() + 1), uri));
		}
		return List.copyOf(parsed);
	}
}
