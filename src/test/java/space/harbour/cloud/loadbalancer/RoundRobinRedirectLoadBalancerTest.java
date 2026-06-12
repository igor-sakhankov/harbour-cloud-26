package space.harbour.cloud.loadbalancer;

import org.junit.jupiter.api.Test;

import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RoundRobinRedirectLoadBalancerTest {

	private static final Clock FIXED_CLOCK =
			Clock.fixed(Instant.parse("2026-06-13T00:00:00Z"), ZoneOffset.UTC);

	@Test
	void selectsHealthyBackendsRoundRobin() {
		LoadBalancerProperties properties = properties(
				"http://localhost:8081",
				"http://localhost:8082",
				"http://localhost:8083");
		HealthCheckClient healthChecks = backend ->
				!backend.baseUrl().equals(URI.create("http://localhost:8082"));
		RoundRobinRedirectLoadBalancer loadBalancer =
				new RoundRobinRedirectLoadBalancer(properties, healthChecks, FIXED_CLOCK);

		loadBalancer.refreshHealth();

		assertEquals(URI.create("http://localhost:8081"), loadBalancer.chooseBackend().orElseThrow().baseUrl());
		assertEquals(URI.create("http://localhost:8083"), loadBalancer.chooseBackend().orElseThrow().baseUrl());
		assertEquals(URI.create("http://localhost:8081"), loadBalancer.chooseBackend().orElseThrow().baseUrl());
	}

	@Test
	void returnsEmptyWhenEveryBackendIsUnhealthy() {
		RoundRobinRedirectLoadBalancer loadBalancer =
				new RoundRobinRedirectLoadBalancer(
						properties("http://localhost:8081"),
						backend -> false,
						FIXED_CLOCK);

		loadBalancer.refreshHealth();

		assertTrue(loadBalancer.chooseBackend().isEmpty());
		assertFalse(loadBalancer.backends().getFirst().healthy());
	}

	@Test
	void rejectsRelativeBackendUris() {
		LoadBalancerProperties properties = properties("localhost:8081");

		assertThrows(IllegalArgumentException.class,
				() -> new RoundRobinRedirectLoadBalancer(properties, backend -> true, FIXED_CLOCK));
	}

	private static LoadBalancerProperties properties(String... instances) {
		LoadBalancerProperties properties = new LoadBalancerProperties();
		properties.setInstances(java.util.Arrays.asList(instances));
		return properties;
	}
}
