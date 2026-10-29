"""Exit when every listed campaign has completion.json or OpenRouter usage reaches a ceiling.

Usage: python3 e1_watch.py CEILING_USD RUN_DIR...
OPENROUTER_KEY_FILE overrides the host-only key path.
"""
import json
import os
import pathlib
import sys
import time
import urllib.request

KEY_FILE = pathlib.Path(os.environ.get("OPENROUTER_KEY_FILE",
                                       pathlib.Path.home() / "swarm-harm/keys/openrouter.key"))
if not KEY_FILE.is_file():
    sys.exit(f"OpenRouter key file not found: {KEY_FILE}. Set OPENROUTER_KEY_FILE.")
KEY = KEY_FILE.read_text().strip()
ceiling = float(sys.argv[1])
runs = [pathlib.Path(p) for p in sys.argv[2:]]
if not runs or not all(r.is_dir() for r in runs):
    sys.exit("every RUN_DIR must exist")


def usage():
    request = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                     headers={"Authorization": "Bearer " + KEY})
    return json.load(urllib.request.urlopen(request, timeout=30))["data"]["usage"]


start = usage()
while True:
    used = usage()
    done = sum((r / "completion.json").exists() for r in runs)
    if used >= ceiling or done == len(runs):
        stamp = time.strftime("%H:%M:%SZ", time.gmtime())
        print(f"usage_usd={used:.2f} spent_since_watch={used - start:.2f} completed={done}/{len(runs)} at {stamp}")
        break
    time.sleep(60)
