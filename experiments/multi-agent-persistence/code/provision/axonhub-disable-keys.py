import json
import sys
from pathlib import Path

import requests

# 停用名称以给定前缀开头的 AxonHub API key（可恢复，记录保留）。用法：axonhub-disable-keys.py PREFIX
BASE = "http://127.0.0.1:8090"
prefix = sys.argv[1]
credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
session = requests.Session()
response = session.post(BASE + "/admin/auth/signin", json={"email": credentials["email"], "password": credentials["password"]}, timeout=30)
response.raise_for_status()
session.headers["Authorization"] = "Bearer " + response.json()["token"]


def gql(query, variables=None):
    r = session.post(BASE + "/admin/graphql", json={"query": query, "variables": variables or {}}, timeout=120)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"]))
    return body["data"]


keys = gql("query { apiKeys(first: 500) { edges { node { id name status } } } }")["apiKeys"]["edges"]
ids = [e["node"]["id"] for e in keys if e["node"]["name"].startswith(prefix) and e["node"]["status"] == "enabled"]
if ids:
    gql("mutation($ids: [ID!]!) { bulkDisableAPIKeys(ids: $ids) }", {"ids": ids})
after = gql("query { apiKeys(first: 500) { edges { node { name status } } } }")["apiKeys"]["edges"]
mine = [e["node"] for e in after if e["node"]["name"].startswith(prefix)]
print(json.dumps({"disabled_now": len(ids), "matching": len(mine), "statuses": sorted({n["status"] for n in mine})}))
