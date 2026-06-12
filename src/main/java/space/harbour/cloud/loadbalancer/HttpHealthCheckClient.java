package space.harbour.cloud.loadbalancer;

import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

/**
 * Health-check implementation that calls each backend over HTTP.
 */
@Component
public class HttpHealthCheckClient implements HealthCheckClient {

	private final HttpClient httpClient;
	private final LoadBalancerProperties properties;

	public HttpHealthCheckClient(LoadBalancerProperties properties) {
		this.properties = properties;
		this.httpClient = HttpClient.newBuilder()
				.connectTimeout(properties.getHealthTimeout())
				.build();
	}

	@Override
	public boolean isHealthy(BackendInstance backend) {
		HttpRequest request = HttpRequest.newBuilder(healthUri(backend.baseUrl()))
				.GET()
				.timeout(properties.getHealthTimeout())
				.build();

		try {
			HttpResponse<Void> response =
					httpClient.send(request, HttpResponse.BodyHandlers.discarding());
			return response.statusCode() >= 200 && response.statusCode() < 300;
		}
		catch (IOException | InterruptedException ex) {
			if (ex instanceof InterruptedException) {
				Thread.currentThread().interrupt();
			}
			return false;
		}
	}

	private URI healthUri(URI baseUrl) {
		String base = trimTrailingSlash(baseUrl.toString());
		String path = properties.getHealthPath();
		if (!path.startsWith("/")) {
			path = "/" + path;
		}
		return URI.create(base + path);
	}

	private static String trimTrailingSlash(String value) {
		if (value.endsWith("/")) {
			return value.substring(0, value.length() - 1);
		}
		return value;
	}
}
