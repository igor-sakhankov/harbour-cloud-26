package space.harbour.cloud.loadbalancer;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.List;

/**
 * Redirect-based load balancer.
 *
 * <p>Requests sent to {@code /lb/<target-path>} receive a {@code 302 Found}
 * response whose {@code Location} header points at a healthy backend instance.
 */
@RestController
public class RedirectLoadBalancerController {

	private static final String LOAD_BALANCER_PREFIX = "/lb";

	private final RedirectLoadBalancer loadBalancer;

	public RedirectLoadBalancerController(RedirectLoadBalancer loadBalancer) {
		this.loadBalancer = loadBalancer;
	}

	/**
	 * Lists configured backend instances and their latest health-check result.
	 */
	@GetMapping("/lb/backends")
	public List<BackendStatus> backends() {
		return loadBalancer.backends();
	}

	/**
	 * Chooses a healthy backend and redirects the client to the matching path.
	 */
	@RequestMapping({"/lb", "/lb/**"})
	public ResponseEntity<Void> redirect(HttpServletRequest request) {
		return loadBalancer.chooseBackend()
				.map(backend -> {
					URI location = redirectLocation(
							backend.baseUrl(), targetPath(request), request.getQueryString());
					return ResponseEntity.status(HttpStatus.FOUND)
							.header(HttpHeaders.LOCATION, location.toString())
							.<Void>build();
				})
				.orElseGet(() -> ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build());
	}

	private static String targetPath(HttpServletRequest request) {
		String path = request.getRequestURI().substring(request.getContextPath().length());
		if (path.equals(LOAD_BALANCER_PREFIX)) {
			return "/";
		}
		if (path.startsWith(LOAD_BALANCER_PREFIX + "/")) {
			return path.substring(LOAD_BALANCER_PREFIX.length());
		}
		return path;
	}

	private static URI redirectLocation(URI baseUrl, String targetPath, String queryString) {
		String base = trimTrailingSlash(baseUrl.toString());
		String path = targetPath.startsWith("/") ? targetPath : "/" + targetPath;
		String query = queryString == null || queryString.isBlank() ? "" : "?" + queryString;
		return URI.create(base + path + query);
	}

	private static String trimTrailingSlash(String value) {
		if (value.endsWith("/")) {
			return value.substring(0, value.length() - 1);
		}
		return value;
	}
}
