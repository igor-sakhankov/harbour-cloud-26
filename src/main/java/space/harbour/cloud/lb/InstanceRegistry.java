package space.harbour.cloud.lb;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Holds the static instance list, each instance's health state, and the
 * round-robin cursor. Health is driven by a single threshold-based state machine
 * fed from BOTH sources:
 * <ul>
 *   <li>the active {@link ActiveHealthChecker} (scheduled probes), and</li>
 *   <li>passive client reports via {@code POST /lb/report}.</li>
 * </ul>
 *
 * <p>An instance is ejected after {@code unhealthy-after} consecutive failures and
 * re-admitted only after {@code healthy-after} consecutive successes — the hysteresis
 * prevents flapping. Instances start healthy (optimistic) so they are usable before
 * the first probe completes.
 */
@Component
public class InstanceRegistry {

    /** Immutable snapshot of one instance's state, for {@code GET /lb/status}. */
    public record InstanceHealth(
            String url, boolean healthy, int consecutiveSuccesses, int consecutiveFailures) {}

    private static final class Instance {
        final String url;
        volatile boolean healthy = true;
        int successes = 0;
        int failures = 0;
        Instance(String url) { this.url = url; }
    }

    private final List<Instance> instances;
    private final int unhealthyAfter;
    private final int healthyAfter;
    private final AtomicInteger cursor = new AtomicInteger();

    public InstanceRegistry(LbProperties props) {
        this.instances = props.instances().stream().map(Instance::new).toList();
        this.unhealthyAfter = props.unhealthyAfter();
        this.healthyAfter = props.healthyAfter();
    }

    /** All configured instance URLs, regardless of health (used by the active checker). */
    public List<String> urls() {
        return instances.stream().map(i -> i.url).toList();
    }

    /**
     * Round-robin over the <em>currently healthy</em> instances.
     *
     * @return the next healthy instance URL, or empty if none are healthy
     */
    public Optional<String> next() {
        List<Instance> healthy = instances.stream().filter(i -> i.healthy).toList();
        if (healthy.isEmpty()) return Optional.empty();
        int idx = Math.floorMod(cursor.getAndIncrement(), healthy.size());
        return Optional.of(healthy.get(idx).url);
    }

    /**
     * Feed one health observation (active probe or passive client report) into the
     * state machine for the matching instance. Unknown URLs are ignored.
     */
    public synchronized void recordResult(String url, boolean ok) {
        for (Instance i : instances) {
            if (i.url.equals(url)) { update(i, ok); return; }
        }
    }

    private void update(Instance i, boolean ok) {
        if (ok) {
            i.successes++;
            i.failures = 0;
            if (!i.healthy && i.successes >= healthyAfter) i.healthy = true;
        } else {
            i.failures++;
            i.successes = 0;
            if (i.healthy && i.failures >= unhealthyAfter) i.healthy = false;
        }
    }

    /** Immutable view of every instance's current state. */
    public synchronized List<InstanceHealth> snapshot() {
        return instances.stream()
                .map(i -> new InstanceHealth(i.url, i.healthy, i.successes, i.failures))
                .toList();
    }
}
