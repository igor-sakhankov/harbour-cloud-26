// Redirect load balancer: answers each request with HTTP 307 pointing at a
// healthy backend chosen by ./balancer. 307 (not 302) preserves the POST method
// and body, so payments survive the redirect.
import { createServer } from "node:http";
import { loadConfig } from "./config";
import { BackendPool } from "./backendPool";
import { HashRing, pickBackend } from "./balancer";
import { startHealthChecks } from "./healthChecker";

const config = loadConfig();
const pool = new BackendPool(config.backends);
const ring = new HashRing(config.backends);
startHealthChecks(pool, config.healthIntervalMs);

const server = createServer((req, res) => {
  // Observability endpoint (not redirected).
  if (req.url === "/__lb/status") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        backends: config.backends.map((url) => ({
          url,
          healthy: pool.isHealthy(url),
        })),
      }),
    );
    return;
  }

  const raw = req.headers["idempotency-key"];
  const key = Array.isArray(raw) ? raw[0] : raw;
  const backend = pickBackend(key, pool, ring);

  if (!backend) {
    res.writeHead(503, { "Content-Type": "text/plain", "Retry-After": "5" });
    res.end("No healthy backends available\n");
    return;
  }

  res.writeHead(307, { Location: `${backend}${req.url ?? "/"}` });
  res.end();
});

server.listen(config.port, () => {
  console.log(
    `Load balancer listening on :${config.port} → ${config.backends.length} backend(s): ${config.backends.join(", ")}`,
  );
});
