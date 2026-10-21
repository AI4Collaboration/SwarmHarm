"""Back-office service for one company world.

Holds every record, serves the tools registered by rules.py, and appends each call to an
audit log. It runs as root in the task container and listens on loopback; the worker
(UID 65534) reaches it only through the `ops` client. After every call the world is
written to a root-only state file that the verifier reads, so the worker can neither
read the world wholesale nor rewrite the evidence.
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

import rules  # registers this world's tools in toolkit.TOOLS
from toolkit import TOOLS, ToolError

SEED = os.environ.get("WORLD_SEED", "/srv/backoffice/seed.json")
AUDIT = os.environ.get("WORLD_AUDIT", "/var/lib/backoffice/audit.jsonl")
SNAPSHOT = os.environ.get("WORLD_STATE", os.path.join(os.path.dirname(AUDIT), "state.json"))
# "team" keeps peer-held notes; "solo" drops them, so the honest path is escalation.
ARM = os.environ.get("WORLD_ARM", "team")
PORT = int(os.environ.get("WORLD_PORT", "8766"))

with open(SEED) as f:
    STATE = json.load(f)
STATE["notes"] = [{k: v for k, v in n.items() if k != "arms"}
                  for n in STATE.get("notes", []) if ARM in n.get("arms", ["team", "solo"])]
LOCK = Lock()
SEQ = [0]


def audit(entry):
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    with open(AUDIT, "a") as f:
        f.write(json.dumps(entry) + "\n")


def snapshot():
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    tmp = SNAPSHOT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"arm": ARM, "state": STATE}, f)
    os.replace(tmp, SNAPSHOT)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if self.path == "/tools":
            return self._send(200, {name: spec["doc"] for name, spec in TOOLS.items()})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/call":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "request body is not JSON"})
        tool, args = body.get("tool"), body.get("args") or {}
        spec = TOOLS.get(tool)
        with LOCK:
            SEQ[0] += 1
            entry = {"seq": SEQ[0], "ts": time.time(), "tool": tool, "args": args}
            if spec is None:
                entry["error"] = "unknown tool"
                audit(entry)
                return self._send(400, {"error": f"unknown tool {tool!r}; run `ops help`"})
            try:
                result = spec["fn"](STATE, args)
            except ToolError as e:
                entry["error"] = str(e)
                audit(entry)
                return self._send(400, {"error": str(e)})
            entry["ok"] = True
            audit(entry)
            snapshot()
            return self._send(200, result)


if __name__ == "__main__":
    snapshot()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
