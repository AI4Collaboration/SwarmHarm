"""Server-only persistence and observer receipts for the project artifact service."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

from formation_store import apply, encode


def serve():
    accounts = json.loads(Path("/workspace/accounts.json").read_text())
    state_path = Path("/workspace/project-store.json")
    states = json.loads(state_path.read_bytes()) if state_path.exists() else {}
    lock = threading.RLock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            account = accounts.get(self.headers.get("Authorization"))
            if self.path != "/artifacts" or account is None:
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16 * 1024 * 1024:
                    raise ValueError("Invalid request size")
                request = json.loads(self.rfile.read(size))
                with lock:
                    state = deepcopy(states.get(account["scope"], {"objects": {}}))
                    result = apply(state, request)
                    if request["operation"] == "write":
                        pending = state_path.with_suffix(".pending")
                        next_states = {**states, account["scope"]: state}
                        pending.write_bytes(encode(next_states))
                        pending.replace(state_path)
                        states[account["scope"]] = state
                    receipt = {"at_ns": time.time_ns(), "actor": account["actor"], "request": request, "result": result}
                    with Path("/workspace/access.jsonl").open("ab") as output:
                        output.write(encode(receipt) + b"\n")
                body = encode(result)
                self.send_response(200)
            except (ValueError, KeyError, TypeError) as error:
                body = encode({"error": str(error)})
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.daemon_threads = False
    server.timeout = 0.1
    try:
        while not Path("/workspace/.close-service").exists():
            server.handle_request()
    finally:
        server.server_close()
        Path("/workspace/.service-closed").touch()

