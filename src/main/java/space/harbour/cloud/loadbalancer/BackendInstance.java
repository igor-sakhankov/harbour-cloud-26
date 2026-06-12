package space.harbour.cloud.loadbalancer;

import java.net.URI;

/**
 * A configured application instance that can receive redirected traffic.
 */
public record BackendInstance(String id, URI baseUrl) {
}
