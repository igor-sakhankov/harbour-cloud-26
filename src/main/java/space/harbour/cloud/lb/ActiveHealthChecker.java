package space.harbour.cloud.lb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

/**
 * Active half of the health model: on a fixed schedule, probes every configured
 * instance's health path and feeds the outcome into the shared
 * {@link InstanceRegistry} state machine. The passive half (client reports) feeds
 * the same machine through {@code POST /lb/report}.
 */
@Component
public class ActiveHealthChecker {

    private static final Logger log = LoggerFactory.getLogger(ActiveHealthChecker.class);

    private final InstanceRegistry registry;
    private final LbProperties props;
    private final HttpClient http;

    public ActiveHealthChecker(InstanceRegistry registry, LbProperties props) {
        this.registry = registry;
        this.props = props;
        this.http = HttpClient.newBuilder()
                .connectTimeout(props.timeout())
                .build();
    }

    @Scheduled(fixedDelayString = "${lb.interval}")
    public void probe() {
        for (String url : registry.urls()) {
            boolean ok = check(url);
            registry.recordResult(url, ok);
        }
    }

    private boolean check(String url) {
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url + props.healthPath()))
                    .timeout(props.timeout())
                    .GET()
                    .build();
            HttpResponse<Void> resp = http.send(req, HttpResponse.BodyHandlers.discarding());
            boolean ok = resp.statusCode() >= 200 && resp.statusCode() < 300;
            if (!ok) log.warn("probe {} -> HTTP {}", url, resp.statusCode());
            return ok;
        } catch (IOException e) {
            log.warn("probe {} failed: {}", url, e.toString());
            return false;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }
}
