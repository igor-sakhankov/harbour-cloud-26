// Active health checks: probe each backend on an interval and update the pool.
// A redirect LB never sees post-redirect traffic, so active probing is the only
// reliable signal. Healthy = any response < 500; 5xx / timeout / refused = down.
import type { BackendPool } from "./backendPool";

const HEALTH_PATH = "/api/v1/payments?storeId=lb-health-check";
const PROBE_TIMEOUT_MS = 5_000;

async function probe(pool: BackendPool, backend: string): Promise<void> {
  try {
    const res = await fetch(`${backend}${HEALTH_PATH}`, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    pool.setHealthy(backend, res.status < 500);
  } catch {
    pool.setHealthy(backend, false);
  }
}

export function startHealthChecks(pool: BackendPool, intervalMs: number): void {
  const runAll = () => {
    for (const backend of pool.backends) void probe(pool, backend);
  };
  runAll(); // probe immediately on startup
  setInterval(runAll, intervalMs).unref();
}
