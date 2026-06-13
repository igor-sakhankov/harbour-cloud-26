"""Send a batch of requests through the load balancer, follow the 302s, and
print how many landed on each backend. Run it again after killing one backend
to see the traffic move to the survivors.

    python3 demo.py [LB_URL] [COUNT]
    python3 demo.py http://localhost:8080 20
"""

import collections
import sys
import urllib.request


def run(lb_url, count):
    landed = collections.Counter()
    for _ in range(count):
        req = urllib.request.Request(lb_url + "/api/v1/payments?storeId=demo")
        with urllib.request.urlopen(req, timeout=5) as resp:
            # geturl() is the final URL after the redirect was followed -> the backend
            backend = resp.geturl().split("/api/")[0]
            landed[backend] += 1
    return landed


def main():
    lb_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    landed = run(lb_url, count)
    print(f"{count} requests through {lb_url}:")
    for backend, n in sorted(landed.items()):
        print(f"  {backend}: {n}")


if __name__ == "__main__":
    main()
