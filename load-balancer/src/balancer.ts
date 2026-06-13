// Routing algorithm: consistent hash on the Idempotency-Key, so retries of the
// same payment land on the same backend (preserving the server's in-memory
// idempotency). Keyless requests and failover pick a random healthy backend.
import { createHash } from "node:crypto";
import type { BackendPool } from "./backendPool";

const VNODES = 100;

function hash(value: string): number {
  return createHash("sha1").update(value).digest().readUInt32BE(0);
}

export class HashRing {
  private readonly ring: { pos: number; backend: string }[];

  constructor(backends: string[]) {
    this.ring = backends
      .flatMap((b) =>
        Array.from({ length: VNODES }, (_, v) => ({
          pos: hash(`${b}#${v}`),
          backend: b,
        })),
      )
      .sort((a, b) => a.pos - b.pos);
  }

  lookup(key: string): string {
    const h = hash(key);
    const node = this.ring.find((n) => n.pos >= h) ?? this.ring[0]!;
    return node.backend;
  }
}

function randomHealthy(healthy: string[]): string {
  return healthy[Math.floor(Math.random() * healthy.length)]!;
}

export function pickBackend(
  key: string | undefined,
  pool: BackendPool,
  ring: HashRing,
): string | null {
  const healthy = pool.healthy();
  if (healthy.length === 0) return null;
  if (key) {
    const primary = ring.lookup(key);
    if (pool.isHealthy(primary)) return primary;
  }
  return randomHealthy(healthy);
}
