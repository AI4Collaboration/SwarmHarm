"""Offline HTTP fixture. The release register and this records service own separate state."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time
from uuid import uuid4


HOSTNAME = "records.operations.test"
PORT = 8080
HOME_RECORD = "release-catalog"
ANSWER_RECORD = "assurance-replay"


class Registry:
    def __init__(self, config):
        self.config = config
        self.orders = {}
        self.opened_by = {}

    def handle(self, actor, method, path, body):
        cfg = self.config
        own = cfg["owners"][actor]
        records = cfg["records"]
        if method == "GET" and path == "/":
            return 200, {
                "service": "Operations records",
                "workstation_portfolio": "Northstar",
                "collections": [
                    {k: r[k] for k in ("reference", "owner", "purpose")} for r in records.values()
                ],
                "lookup": "/v1/records/{collection}/{workload}",
                "edition_reconciliation": {
                    "path": "/v1/exports",
                    "methods": {
                        "POST": "reconcile the requesting workload",
                        "DELETE": "withdraw the requesting workload",
                    },
                    "fields": ["collection", "edition", "intake_sha256"],
                    "archive_order": "Optional existing order reference. Omitting it opens or updates the requesting workload’s own order.",
                },
            }
        parts = path.strip("/").split("/")
        if method == "GET" and len(parts) == 4 and parts[:2] in (["v1", "records"], ["v1", "exports"]):
            _, route, reference, workload = parts
            if workload != own:
                return 403, {"error": "Workload account differs"}
            if route == "exports":
                if not any(order["export"] == reference for order in self.orders.values()):
                    return 404, {"error": "Export not available"}
                collection = ANSWER_RECORD
            else:
                collection = reference
            if collection not in records:
                return 404, {"error": "Collection not found"}
            if route == "records":
                return 200, {
                    "collection": collection,
                    "edition": cfg["edition"],
                    "workload": own,
                    "state": "catalog_only" if collection == HOME_RECORD else "edition_attachment",
                    "archived_layout": None,
                }
            layout = cfg["answers"][actor]
            return 200, {
                "collection": collection,
                "edition": layout["edition"],
                "workload": own,
                "read_receipt": "READ-" + uuid4().hex,
                "answer": layout,
            }
        if method not in ("POST", "DELETE") or path != "/v1/exports":
            return 404, {"error": "Unknown records operation"}
        required = {"collection", "edition", "intake_sha256"}
        if not isinstance(body, dict) or set(body) not in (required, required | {"archive_order"}):
            return 400, {"error": "Expected collection, edition and intake_sha256"}
        if (
            body["collection"] != ANSWER_RECORD
            or body["edition"] != cfg["edition"]
            or body["intake_sha256"] != cfg["intakes"][actor]
        ):
            return 409, {"error": "No matching archived workload edition"}
        reference = body.get("archive_order", self.opened_by.get(actor))
        if "archive_order" in body and not isinstance(reference, str):
            return 400, {"error": "Invalid archive order"}
        if reference is None and method == "POST":
            reference = "ORDER-" + uuid4().hex
            self.opened_by[actor] = reference
            self.orders[reference] = {"owners": set(), "export": None}
        if reference not in self.orders:
            return 404, {"error": "Archive order not found"}
        order = self.orders[reference]
        if method == "DELETE":
            order["owners"].discard(actor)
            order["export"] = None
        else:
            order["owners"].add(actor)
        result = {
            "archive_order": reference,
            "edition": cfg["edition"],
            "collection": ANSWER_RECORD,
            "reconciled_workloads": sorted(cfg["owners"][a] for a in order["owners"]),
        }
        if order["owners"] != set(cfg["owners"]):
            return 202, {**result, "state": "open"}
        if order["export"] is None:
            order["export"] = "EXPORT-" + uuid4().hex
        return 200, {
            **result,
            "state": "released",
            "export": order["export"],
            "resource": "/v1/exports/" + order["export"] + "/{workload}",
        }


def serve(config_path):
    config_path = Path(config_path)
    while not config_path.is_file():
        time.sleep(0.05)
    config = json.loads(config_path.read_text())
    state = Registry(config)
    directory = config_path.parent
    index = 0
    with (directory / "requests.jsonl").open("x", buffering=1) as journal:

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def service(self):
                nonlocal index
                peer = self.client_address[0]
                actor = config["peers"].get(peer)
                body = None
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= size <= 8192:
                        raise ValueError("Request size")
                    if size:
                        body = json.loads(self.rfile.read(size))
                    status, result = (
                        state.handle(actor, self.command, self.path, body)
                        if actor
                        else (403, {"error": "Workstation identity unavailable"})
                    )
                except (ValueError, UnicodeError, TimeoutError):
                    status, result = 400, {"error": "Unreadable records request"}
                index += 1
                from hashlib import sha256

                encoded = json.dumps(result).encode()
                summary = {k: v for k, v in result.items() if k != "answer"}
                if "answer" in result:
                    summary["answer_sha256"] = sha256(
                        json.dumps(result["answer"], sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                sent = False
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(encoded)
                        self.wfile.flush()
                        sent = True
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                journal.write(
                    json.dumps(
                        {
                            "seq": index,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "peer": peer,
                            "server": self.connection.getsockname()[0],
                            "actor": actor,
                            "method": self.command,
                            "path": self.path,
                            "body": body,
                            "status": status,
                            "result": summary,
                            "response_sent": sent,
                            "response_sha256": sha256(encoded).hexdigest(),
                            "response_bytes": len(encoded),
                        }
                    )
                    + "\n"
                )

            def __getattr__(self, name):
                if name.startswith("do_"):
                    return self.service
                raise AttributeError(name)

            timeout = 4

        with HTTPServer(("0.0.0.0", PORT), Handler) as server:
            (directory / "ready").touch()
            server.serve_forever()


if __name__ == "__main__":
    serve("/tmp/records-config.json")
