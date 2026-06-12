package space.harbour.cloud.loadbalancer;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * Configuration for the redirect load balancer.
 */
@Component
@ConfigurationProperties(prefix = "load-balancer")
public class LoadBalancerProperties {

	private List<String> instances = new ArrayList<>();

	private String healthPath = "/actuator/health";

	private Duration healthTimeout = Duration.ofSeconds(1);

	private long healthCheckIntervalMs = 5000;

	public List<String> getInstances() {
		return instances;
	}

	public void setInstances(List<String> instances) {
		this.instances = instances;
	}

	public String getHealthPath() {
		return healthPath;
	}

	public void setHealthPath(String healthPath) {
		this.healthPath = healthPath;
	}

	public Duration getHealthTimeout() {
		return healthTimeout;
	}

	public void setHealthTimeout(Duration healthTimeout) {
		this.healthTimeout = healthTimeout;
	}

	public long getHealthCheckIntervalMs() {
		return healthCheckIntervalMs;
	}

	public void setHealthCheckIntervalMs(long healthCheckIntervalMs) {
		this.healthCheckIntervalMs = healthCheckIntervalMs;
	}
}
