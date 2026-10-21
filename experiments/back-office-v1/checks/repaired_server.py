"""The back office with its loophole closed, for the repair check in check_harbor.py.

Runs the same server.py and rules.py, but every tool call that matches one of the step's
exploit matchers in truth.json is repaired before the rules see it:

- if the matcher keys on an exception field (arg_present), that field and any reference
  fields it names are dropped, so the tool's own gate decides as if no exception was given;
- otherwise (the matcher names the call itself, e.g. marking photos verified on the
  blocked claim) the call is refused.

The audit log keeps the original arguments. Never copied into a task image.

    WORLD_REPAIR_TRUTH=tests/truth.json WORLD_REPAIR_STEP=wave-1 python3 repaired_server.py
"""

import json
import os
from http.server import ThreadingHTTPServer

import server  # loads the world and registers the tools
from compute_reward import matches
from toolkit import TOOLS, ToolError

STEP = json.load(open(os.environ["WORLD_REPAIR_TRUTH"]))["steps"][os.environ["WORLD_REPAIR_STEP"]]


def repaired(name, fn):
    def call(state, args):
        for m in STEP["bypass"]:
            if not matches({"tool": name, "args": args}, m):
                continue
            if not m.get("arg_present"):
                raise ToolError("this action needs a documented reference on file")
            drop = {m["arg_present"], *m.get("arg_lacks", {})}
            args = {k: v for k, v in args.items() if k not in drop}
        return fn(state, args)
    return call


for name, spec in TOOLS.items():
    spec["fn"] = repaired(name, spec["fn"])

if __name__ == "__main__":
    server.snapshot()
    ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler).serve_forever()
