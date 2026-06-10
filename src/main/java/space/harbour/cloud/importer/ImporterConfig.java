package space.harbour.cloud.importer;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(ImporterProperties.class)
public class ImporterConfig {

	@Bean
	RestClient.Builder restClientBuilder() {
		return RestClient.builder();
	}
}
