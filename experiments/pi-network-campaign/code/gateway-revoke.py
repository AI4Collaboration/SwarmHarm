import json
import secrets
from pathlib import Path

import requests

credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
key = json.loads(Path("/opt/swarmharm/swh119/key.json").read_text())
session = requests.Session()
login = session.post("http://127.0.0.1:8090/admin/auth/signin", json=credentials, timeout=30)
login.raise_for_status()
session.headers["Authorization"] = "Bearer " + login.json()["token"]
response = session.post("http://127.0.0.1:8090/admin/graphql", json={"query": "mutation($id:ID!){updateAPIKeyStatus(id:$id,status:disabled){id name status}}", "variables": {"id": key["api_key_id"]}}, timeout=30)
response.raise_for_status()
body = response.json()
if body.get("errors"):
    raise RuntimeError(body["errors"])
policy = Path("/etc/swh119-gateway/credentials.json")
values = json.loads(policy.read_text())
values["key"] = "ah-swh119-revoked-" + secrets.token_hex(32)
policy.write_text(json.dumps(values))
print(json.dumps(body["data"]["updateAPIKeyStatus"]))
