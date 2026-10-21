import argparse
import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--token", default="54cc39c7-f9a5-4b94-b507-de4f084ffe5e")
parser.add_argument("--source-ip", action="append", required=True)
parser.add_argument("--since", required=True)
parser.add_argument("--until", default=datetime.now(timezone.utc).isoformat())
parser.add_argument("--method", choices=["POST", "GET"], default="POST")
parser.add_argument("--body-file", action="append", type=Path, default=[])
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sources = {str(ipaddress.ip_address(value)) for value in args.source_ip}
since = datetime.fromisoformat(args.since).astimezone(timezone.utc)
until = datetime.fromisoformat(args.until).astimezone(timezone.utc)
assert since <= until
expected = {hashlib.sha256(path.read_bytes()).hexdigest(): str(path) for path in args.body_file}
endpoint = "https://webhook.site/token/" + args.token + "/requests"
query = "type:web AND method:" + args.method + " AND (" + " OR ".join('ip:"' + value + '"' for value in sorted(sources)) + ")"
receipts = {}
pages = []
page = 1
while True:
    response = requests.get(endpoint, params={"sorting": "oldest", "per_page": 100, "page": page, "date_from": since.strftime("%Y-%m-%d %H:%M:%S"), "date_to": until.strftime("%Y-%m-%d %H:%M:%S"), "query": query}, timeout=30)
    response.raise_for_status()
    data = response.json()
    pages.append({"page": page, "status": response.status_code, "total": data["total"], "is_last_page": data["is_last_page"]})
    for receipt in data["data"]:
        received = datetime.fromisoformat(receipt["created_at"]).replace(tzinfo=timezone.utc)
        if receipt.get("method") == args.method and receipt.get("ip") in sources and since.replace(microsecond=0) <= received <= until:
            body = receipt["content"].encode("utf-8")
            receipt["body_sha256"] = hashlib.sha256(body).hexdigest()
            receipt["matched_body_file"] = expected.get(receipt["body_sha256"])
            receipts[receipt["uuid"]] = receipt
    if data["is_last_page"]:
        break
    page += 1
result = {"collected_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint, "http_status": response.status_code, "source_ips": sorted(sources), "since": since.isoformat(), "until": until.isoformat(), "method": args.method, "receipt_time_zone": "UTC", "receipt_time_precision": "seconds", "pages": pages, "receipt_count": len(receipts), "exact_body_match_count": sum(bool(item["matched_body_file"]) for item in receipts.values()), "receipts": list(receipts.values())}
args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2))
args.output.chmod(0o600)
print(json.dumps({"http_status": result["http_status"], "receipt_count": result["receipt_count"], "exact_body_match_count": result["exact_body_match_count"], "pages": len(pages)}))
