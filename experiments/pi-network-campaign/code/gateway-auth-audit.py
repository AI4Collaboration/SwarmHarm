import json
from pathlib import Path

import requests

credentials = json.loads(Path("/etc/swh119-gateway/credentials.json").read_text())
base = "http://127.0.0.1:8090"
paths = ["/v1/chat/completions", "/v1/responses", "/v1/responses/compact", "/anthropic/v1/messages", "/v1/messages", "/v1/completions", "/v1/embeddings", "/v1/images/generations", "/v1/audio/speech", "/v1/moderations", "/v1/alpha/search", "/v1/videos", "/v1/rerank", "/v1/systemone", "/jina/v1/embeddings", "/typesafe/v1/systemone", "/doubao/v3/contents/generations/tasks"]
output = []
for path in paths:
    response = requests.post(base + path, headers={"Authorization": "Bearer " + credentials["key"]}, json={"model": credentials["model"], "messages": [{"role": "user", "content": "Reply OK"}], "input": "Reply OK", "max_tokens": 8}, timeout=30)
    assert 400 <= response.status_code < 500, (path, response.status_code)
    output.append({"route": path, "auth": "bearer", "status": response.status_code})
for header in ["X-Api-Key", "Api-Key"]:
    response = requests.post(base + "/v1/chat/completions", headers={header: credentials["key"]}, json={"model": credentials["model"], "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 8}, timeout=30)
    assert 400 <= response.status_code < 500, (header, response.status_code)
    output.append({"route": "/v1/chat/completions", "auth": header, "status": response.status_code})
for parameter in ["key", "api_key"]:
    response = requests.post(base + "/v1/chat/completions", params={parameter: credentials["key"]}, json={"model": credentials["model"], "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 8}, timeout=30)
    assert 400 <= response.status_code < 500, (parameter, response.status_code)
    output.append({"route": "/v1/chat/completions", "auth": "query:" + parameter, "status": response.status_code})
for path in ["/v1/models", "/v1/responses", "/anthropic/v1/models"]:
    response = requests.get(base + path, headers={"Authorization": "Bearer " + credentials["key"]}, timeout=30)
    assert 400 <= response.status_code < 500, (path, response.status_code)
    output.append({"route": path, "auth": "bearer:GET", "status": response.status_code})
for path in ["/gemini/v1beta/models/model:generateContent", "/v1beta/models/model:generateContent"]:
    response = requests.post(base + path, headers={"X-Goog-Api-Key": credentials["key"]}, json={"contents": []}, timeout=30)
    assert 400 <= response.status_code < 500, (path, response.status_code)
    output.append({"route": path, "auth": "X-Goog-Api-Key", "status": response.status_code})
print(json.dumps({"direct_native_alias_probes": output}, indent=2))
