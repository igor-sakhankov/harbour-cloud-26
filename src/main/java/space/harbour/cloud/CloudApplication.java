package space.harbour.cloud;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * The payments application entry point. Its component scan is pinned to
 * {@code space.harbour.cloud.payments} so that the redirect load balancer
 * (in {@code space.harbour.cloud.lb}, a subpackage that the default scan would
 * otherwise pick up) is never booted by a normal {@code bootRun}. Run the
 * balancer with the {@code bootRunLb} Gradle task instead.
 */
@SpringBootApplication(scanBasePackages = "space.harbour.cloud.payments")
public class CloudApplication {

	public static void main(String[] args) {
		SpringApplication.run(CloudApplication.class, args);
	}

}
