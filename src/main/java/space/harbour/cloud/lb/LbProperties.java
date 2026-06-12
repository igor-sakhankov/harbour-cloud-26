package space.harbour.cloud.lb;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;
import java.util.List;

/**
 * Externalised configuration for the load balancer, bound from the {@code lb.*}
 * keys in {@code application-lb.properties} (relaxed binding applies, so
 * {@code lb.unhealthy-after} maps to {@link #unhealthyAfter}).
 *
 * @param instances      static list of backend base URLs, e.g. {@code http://localhost:8081}
 * @param healthPath     path the active checker probes on each instance (e.g. {@code /actuator/health})
 * @param interval       how often the active checker runs
 * @param timeout        connect/read timeout for each active probe
 * @param unhealthyAfter consecutive failures before an instance is ejected from rotation
 * @param healthyAfter   consecutive successes before an ejected instance is re-admitted
 */
@ConfigurationProperties("lb")
public record LbProperties(
        List<String> instances,
        String healthPath,
        Duration interval,
        Duration timeout,
        int unhealthyAfter,
        int healthyAfter) {

    public LbProperties {
        instances = (instances == null) ? List.of() : List.copyOf(instances);
        if (healthPath == null || healthPath.isBlank()) healthPath = "/actuator/health";
        if (interval == null) interval = Duration.ofSeconds(2);
        if (timeout == null) timeout = Duration.ofSeconds(1);
        if (unhealthyAfter < 1) unhealthyAfter = 2;
        if (healthyAfter < 1) healthyAfter = 2;
    }
}
