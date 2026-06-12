package space.harbour.cloud.loadbalancer;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Enables periodic backend health checks.
 */
@Configuration
@EnableScheduling
public class LoadBalancerConfig {
}
