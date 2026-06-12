"""Demonstration client for the redirect load balancer.

Sends 20 requests to the load balancer without following redirects, then
prints the Location header of each response. This makes the Round Robin
distribution across backend instances directly visible.
"""

import requests

LOAD_BALANCER_URL = "http://localhost:8000/api/v1/payments"
NUMBER_OF_REQUESTS = 20


def main() -> None:
    for request_number in range(1, NUMBER_OF_REQUESTS + 1):
        try:
            # allow_redirects=False lets us inspect the 302 ourselves instead
            # of requests transparently following it.
            response = requests.get(
                LOAD_BALANCER_URL,
                allow_redirects=False,
                timeout=5,
            )
        except requests.RequestException as error:
            print(f"Request #{request_number} -> Failed: {error}")
            continue

        location = response.headers.get("Location")
        if location is not None:
            print(
                f"Request #{request_number} -> Status: {response.status_code}"
                f" -> Redirected to: {location}"
            )
        else:
            print(
                f"Request #{request_number} -> Status: {response.status_code}"
                " -> No redirect (no healthy instances?)"
            )


if __name__ == "__main__":
    main()
