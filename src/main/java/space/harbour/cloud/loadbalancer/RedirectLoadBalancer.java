package space.harbour.cloud.loadbalancer;

import java.util.List;
import java.util.Optional;

/**
 * Selects healthy backends for redirect responses.
 */
public interface RedirectLoadBalancer {

	Optional<BackendInstance> chooseBackend();

	List<BackendStatus> backends();
}
