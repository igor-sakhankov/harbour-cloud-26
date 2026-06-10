package space.harbour.cloud.payments;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Clock;
import java.time.Duration;

@Configuration
public class PaymentConfig {

	/**
	 * A system-UTC clock. Injected into {@link PaymentService} so that tests can
	 * supply a fixed clock and assert on timestamps deterministically.
	 */
	@Bean
	public Clock clock() {
		return Clock.systemUTC();
	}

	/**
	 * Configures a default RestClient.Builder bean with client timeouts
	 * to prevent requests from hanging indefinitely.
	 */
	@Bean
	public RestClient.Builder restClientBuilder() {
		SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
		factory.setConnectTimeout(Duration.ofSeconds(2));
		factory.setReadTimeout(Duration.ofSeconds(2));
		return RestClient.builder().requestFactory(factory);
	}
}
