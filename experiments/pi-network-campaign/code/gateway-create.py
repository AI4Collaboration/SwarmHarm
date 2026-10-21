import json
import os
import secrets
from pathlib import Path

import requests

base = "http://127.0.0.1:8090"
root = Path("/opt/swarmharm/swh119")
root.mkdir(mode=0o700, exist_ok=True)
credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
session = requests.Session()
login = session.post(base + "/admin/auth/signin", json=credentials, timeout=30)
login.raise_for_status()
session.headers["Authorization"] = "Bearer " + login.json()["token"]


def gql(query, variables=None):
    response = session.post(base + "/admin/graphql", json={"query": query, "variables": variables or {}}, timeout=60)
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


if (root / "backend.json").exists():
    key = json.loads((root / "backend.json").read_text())
else:
    key = gql("mutation($input:CreateAPIKeyInput!){createAPIKey(input:$input){id key name status}}", {"input": {"name": "swh119-campaign-policy-backend", "type": "service_account", "projectID": "gid://axonhub/Project/1", "scopes": ["write_requests"]}})["createAPIKey"]
    (root / "backend.json").write_text(json.dumps(key, indent=2))
    (root / "backend.json").chmod(0o600)
model = "deepseek/deepseek-v4.1-flash-1017"
profile = {"activeProfile": "campaign", "profiles": [{"name": "campaign", "channelIDs": [12], "modelIDs": [model]}]}
configured = gql("mutation($id:ID!,$input:UpdateAPIKeyProfilesInput!){updateAPIKeyProfiles(id:$id,input:$input){id name status scopes profiles{activeProfile profiles{name channelIDs modelIDs}}}}", {"id": key["id"], "input": profile})["updateAPIKeyProfiles"]
if (root / "key.json").exists():
    public = json.loads((root / "key.json").read_text())
else:
    public = {"key": "ah-swh119-" + secrets.token_hex(32), "base_url": "https://lmportal.iefbr14.xyz/v1", "model": model, "reasoning_effort": "high", "api_key_id": key["id"]}
    (root / "key.json").write_text(json.dumps(public, indent=2))
    (root / "key.json").chmod(0o600)
policy = Path("/etc/swh119-gateway")
policy.mkdir(mode=0o750, exist_ok=True)
os.chown(policy, 0, 33)
(policy / "credentials.json").write_text(json.dumps({"key": public["key"], "backend_key": key["key"], "model": model}))
(policy / "credentials.json").chmod(0o640)
os.chown(policy / "credentials.json", 0, 33)
(root / "native-scope.json").write_text(json.dumps(configured, indent=2))
print(json.dumps(configured, indent=2))
