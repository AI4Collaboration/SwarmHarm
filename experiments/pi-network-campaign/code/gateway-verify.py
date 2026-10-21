import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--key-file", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
settings = json.loads(args.key_file.read_text())
base = settings["base_url"].removesuffix("/v1")
session = requests.Session()
session.headers["Authorization"] = "Bearer " + settings["key"]
model = settings["model"]
body = {"model": model, "messages": [{"role": "user", "content": "Use the campaign_preflight function with hostname from your user input: gateway-preflight. Then report the hostname returned by the function."}], "reasoning": {"effort": "high"}, "max_tokens": 2048, "tools": [{"type": "function", "function": {"name": "campaign_preflight", "description": "Return the operator's current machine hostname.", "parameters": {"type": "object", "properties": {"hostname": {"type": "string"}}, "required": ["hostname"]}}}], "tool_choice": "required"}
evidence = {"verified_at": datetime.now(timezone.utc).isoformat(), "model": model, "base_url": base, "reasoning": body["reasoning"], "checks": []}
first = session.post(base + "/v1/chat/completions", json=body, timeout=180)
evidence["first"] = {"status": first.status_code, "body": first.json()}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(evidence, indent=2))
first.raise_for_status()
assistant = first.json()["choices"][0]["message"]
call = assistant["tool_calls"][0]
assert call["function"]["name"] == "campaign_preflight"
hostname = socket.gethostname()
body["messages"].extend([assistant, {"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"hostname": hostname})}])
body["tool_choice"] = "none"
second = session.post(base + "/v1/chat/completions", json=body, timeout=180)
evidence["second"] = {"status": second.status_code, "body": second.json()}
args.output.write_text(json.dumps(evidence, indent=2))
second.raise_for_status()
assert hostname in second.json()["choices"][0]["message"]["content"]
checks = [("responses", "/v1/responses", {"model": model, "input": "Reply OK"}), ("anthropic", "/anthropic/v1/messages", {"model": model, "messages": [], "max_tokens": 8}), ("models", "/v1/models", {}), ("alternate_model", "/v1/chat/completions", dict(body, model="gpt-6-astra")), ("hosted_tool", "/v1/chat/completions", dict(body, tools=[{"type": "web_search"}])), ("hosted_plugin", "/v1/chat/completions", dict(body, plugins=[{"id": "web"}]))]
checks.extend(("route_" + name, path, body) for name, path in [("completions", "/v1/completions"), ("embeddings", "/v1/embeddings"), ("images", "/v1/images/generations"), ("audio", "/v1/audio/speech"), ("messages", "/v1/messages"), ("openai_prefix", "/openai/v1/chat/completions")])
for name, path, request_body in checks:
    response = session.post(base + path, json=request_body, timeout=30)
    item = {"name": name, "status": response.status_code, "body": response.json()}
    evidence["checks"].append(item)
    args.output.write_text(json.dumps(evidence, indent=2))
    assert response.status_code == 403, item
print(json.dumps({"verified_at": evidence["verified_at"], "tool_roundtrip": [first.status_code, second.status_code], "checks": [{"name": c["name"], "status": c["status"]} for c in evidence["checks"]]}, indent=2))
