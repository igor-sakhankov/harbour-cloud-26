// Tracks the backends and their current health (updated by the health checker).
export class BackendPool {
  private readonly healthByUrl: Map<string, boolean>;

  constructor(public readonly backends: string[]) {
    // Optimistic until the first probe runs, so the LB serves immediately.
    this.healthByUrl = new Map(backends.map((b) => [b, true]));
  }

  setHealthy(backend: string, healthy: boolean): void {
    this.healthByUrl.set(backend, healthy);
  }

  isHealthy(backend: string): boolean {
    return this.healthByUrl.get(backend) ?? false;
  }

  healthy(): string[] {
    return this.backends.filter((b) => this.healthByUrl.get(b));
  }
}
