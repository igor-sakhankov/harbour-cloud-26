package space.harbour.cloud.lb;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.List;

/**
 * The HTTP surface of the load balancer.
 *
 * <ul>
 *   <li>{@code /api/**} (any method) — pick a healthy instance and answer
 *       {@code 302 Found} with a {@code Location} that preserves the original path
 *       and query string; {@code 503} when nothing is healthy. Only {@code /api/**}
 *       is intercepted, so {@code /favicon.ico}, {@code /error} and {@code /lb/*}
 *       are never redirected.</li>
 *   <li>{@code POST /lb/report?instance=...&ok=false} — passive client health report.</li>
 *   <li>{@code GET /lb/status} — current health of every instance.</li>
 * </ul>
 */
@RestController
public class RedirectController {

    private static final Logger log = LoggerFactory.getLogger(RedirectController.class);

    private final InstanceRegistry registry;

    public RedirectController(InstanceRegistry registry) {
        this.registry = registry;
    }

    @RequestMapping("/api/**")
    public ResponseEntity<Void> redirect(HttpServletRequest request) {
        return registry.next()
                .map(target -> {
                    String location = target + request.getRequestURI()
                            + (request.getQueryString() != null ? "?" + request.getQueryString() : "");
                    log.debug("302 {} {} -> {}", request.getMethod(), request.getRequestURI(), location);
                    return ResponseEntity.status(HttpStatus.FOUND)
                            .location(URI.create(location))
                            .<Void>build();
                })
                .orElseGet(() -> {
                    log.warn("no healthy instance for {} {}", request.getMethod(), request.getRequestURI());
                    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
                });
    }

    @PostMapping("/lb/report")
    public ResponseEntity<Void> report(@RequestParam String instance, @RequestParam boolean ok) {
        registry.recordResult(instance, ok);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/lb/status")
    public List<InstanceRegistry.InstanceHealth> status() {
        return registry.snapshot();
    }
}
