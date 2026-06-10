import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_CSV_FILE = "payments.csv"
DEFAULT_STORE_ID = "store-starharbour-01"
SENT_LOG_FILE   = "sent_orders.json"   

MAX_RETRIES      = 3
INITIAL_DELAY_S  = 1   

def load_sent_orders(log_path: str) -> set:
    path = Path(log_path)
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_sent_orders(log_path: str, sent: set) -> None:
    with open(log_path, "w") as f:
        json.dump(sorted(sent), f, indent=2)


def send_payment(base_url: str, store_id: str, order: dict) -> int:
    payload = {
        "coffeeType":   order["coffee_type"],
        "price":        float(order["price"]),
        "currency":     order["currency"],
        "loyaltyCardId": order["loyalty_card_id"],
    }
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url    = f"{base_url}/api/v1/payments",
        data   = data,
        method = "POST",
        headers = {
            "Content-Type":    "application/json",
            "Store-Id":        store_id,
            "Idempotency-Key": order["order_id"],  
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code  


def upload_with_retry(base_url: str, store_id: str, order: dict) -> bool:

    delay = INITIAL_DELAY_S
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            status = send_payment(base_url, store_id, order)

            if status in (200, 201):
                label = "CREATED" if status == 201 else "ALREADY EXISTS"
                print(f"{order['order_id']}  →  {status} {label}")
                return True

            if 400 <= status < 500:
                print(f"{order['order_id']}  →  {status} client error (skipping)")
                return False

            print(f"{order['order_id']}  →  {status}  (attempt {attempt}/{MAX_RETRIES})")

        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"{order['order_id']}  →  network error: {exc}  (attempt {attempt}/{MAX_RETRIES})")

        if attempt < MAX_RETRIES:
            print(f"      retrying in {delay}s …")
            time.sleep(delay)
            delay *= 2 

    print(f"{order['order_id']}  →  failed after {MAX_RETRIES} attempts")
    return False

def main():
    parser = argparse.ArgumentParser(description="Upload coffee payments from a CSV file.")
    parser.add_argument("--file",  default=DEFAULT_CSV_FILE, help="Path to the CSV file")
    parser.add_argument("--url",   default=DEFAULT_BASE_URL, help="Base URL of the Payments API")
    parser.add_argument("--store", default=DEFAULT_STORE_ID, help="Store ID header value")
    args = parser.parse_args()

    csv_path = Path(args.file)
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, newline="") as f:
        orders = list(csv.DictReader(f))

    if not orders:
        print("No orders found in CSV. Exiting.")
        sys.exit(0)

    sent = load_sent_orders(SENT_LOG_FILE)

    print(f"\n StarHarbour CSV Uploader")
    print(f"    API  : {args.url}")
    print(f"    Store: {args.store}")
    print(f"    File : {csv_path}  ({len(orders)} rows)")
    print(f"    Already sent: {len(sent)} order(s) — will skip them\n")

    succeeded = 0
    skipped   = 0
    failed    = 0

    for order in orders:
        order_id = order.get("order_id", "").strip()

        if not order_id:
            print("Row missing order_id — skipping")
            skipped += 1
            continue

        if order_id in sent:
            print(f"{order_id} already sent, skipping")
            skipped += 1
            continue

        ok = upload_with_retry(args.url, args.store, order)
        if ok:
            sent.add(order_id)
            save_sent_orders(SENT_LOG_FILE, sent)  
            succeeded += 1
        else:
            failed += 1

    print(f"\nDone — {succeeded} sent, {skipped} skipped, {failed} failed")
    if failed:
        print("Some payments failed. Re-run the script to retry them.")
        sys.exit(1)


if __name__ == "__main__":
    main()