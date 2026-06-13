// Service discovery: the backend list comes from the LB_BACKENDS env var.
export interface Config {
  port: number;
  backends: string[];
  healthIntervalMs: number;
}

export function loadConfig(): Config {
  const backends = (process.env.LB_BACKENDS ?? "")
    .split(",")
    .map((s) => s.trim().replace(/\/+$/, ""))
    .filter(Boolean);

  if (backends.length === 0) {
    console.error(
      "LB_BACKENDS is required, e.g. LB_BACKENDS=http://localhost:8081,http://localhost:8082",
    );
    process.exit(1);
  }

  return {
    port: Number(process.env.PORT ?? 8080),
    backends,
    healthIntervalMs: Number(process.env.HEALTH_INTERVAL_MS ?? 10_000),
  };
}
