package space.harbour.cloud.importer;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.net.URI;

@ConfigurationProperties(prefix = "payment-importer")
public class ImporterProperties {

	private URI centralSystemBaseUrl = URI.create("http://localhost:9091");
	private int maxAttempts = 3;

	public URI getCentralSystemBaseUrl() {
		return centralSystemBaseUrl;
	}

	public void setCentralSystemBaseUrl(URI centralSystemBaseUrl) {
		this.centralSystemBaseUrl = centralSystemBaseUrl;
	}

	public int getMaxAttempts() {
		return maxAttempts;
	}

	public void setMaxAttempts(int maxAttempts) {
		if (maxAttempts < 1) {
			throw new IllegalArgumentException("maxAttempts must be at least 1");
		}
		this.maxAttempts = maxAttempts;
	}
}
