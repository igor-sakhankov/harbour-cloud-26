package space.harbour.cloud.loadbalancer;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class RedirectLoadBalancerControllerTest {

	@Test
	void redirectsToChosenBackendWithOriginalPathAndQueryString() throws Exception {
		MockMvc mvc = MockMvcBuilders.standaloneSetup(new RedirectLoadBalancerController(
						new StubLoadBalancer(Optional.of(new BackendInstance(
								"backend-1", URI.create("http://localhost:8081"))))))
				.build();

		mvc.perform(get("/lb/api/v1/payments?storeId=store-london-01"))
				.andExpect(status().isFound())
				.andExpect(header().string(
						HttpHeaders.LOCATION,
						"http://localhost:8081/api/v1/payments?storeId=store-london-01"));
	}

	@Test
	void returns503WhenNoHealthyBackendExists() throws Exception {
		MockMvc mvc = MockMvcBuilders.standaloneSetup(new RedirectLoadBalancerController(
						new StubLoadBalancer(Optional.empty())))
				.build();

		mvc.perform(get("/lb/api/v1/payments?storeId=store-london-01"))
				.andExpect(status().isServiceUnavailable());
	}

	@Test
	void listsConfiguredBackendsWithHealthStatus() throws Exception {
		MockMvc mvc = MockMvcBuilders.standaloneSetup(new RedirectLoadBalancerController(
						new StubLoadBalancer(Optional.empty())))
				.build();

		mvc.perform(get("/lb/backends"))
				.andExpect(status().isOk())
				.andExpect(jsonPath("$", hasSize(1)))
				.andExpect(jsonPath("$[0].id").value("backend-1"))
				.andExpect(jsonPath("$[0].healthy").value(true));
	}

	private record StubLoadBalancer(Optional<BackendInstance> selected) implements RedirectLoadBalancer {

		@Override
		public Optional<BackendInstance> chooseBackend() {
			return selected;
		}

		@Override
		public List<BackendStatus> backends() {
			return List.of(new BackendStatus(
					"backend-1",
					URI.create("http://localhost:8081"),
					true,
					Instant.parse("2026-06-13T00:00:00Z")));
		}
	}
}
