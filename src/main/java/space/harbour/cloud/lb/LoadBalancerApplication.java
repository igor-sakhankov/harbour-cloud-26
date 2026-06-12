package space.harbour.cloud.lb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * A redirect (HTTP 302) load balancer for the StarHarbour Payments service.
 *
 * <p>This is a <em>second</em>, standalone Spring Boot application that shares the
 * module with the payments app. It does NOT proxy traffic: for each {@code /api/**}
 * request it picks one healthy backend instance and answers {@code 302 Found} with a
 * {@code Location} header, so the client follows the redirect to the instance directly.
 *
 * <p>The component scan is pinned to {@code space.harbour.cloud.lb} so that running the
 * balancer does not boot the payments controllers; symmetrically, {@code CloudApplication}
 * scans only {@code space.harbour.cloud.payments}, so a normal {@code bootRun} never boots
 * this balancer. Start it with the {@code bootRunLb} Gradle task (profile {@code lb}).
 */
@SpringBootApplication(scanBasePackages = "space.harbour.cloud.lb")
@EnableScheduling
@EnableConfigurationProperties(LbProperties.class)
public class LoadBalancerApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoadBalancerApplication.class, args);
    }
}
