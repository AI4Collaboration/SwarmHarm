import json
import sys
from pathlib import Path

import requests

# 列出指定时间窗口内、由指定 API key 发起的 AxonHub 请求（仅元数据），输出 JSON 到 stdout
BASE = "http://127.0.0.1:8090"
SINCE = sys.argv[1]
KEY_NAMES = set(sys.argv[2:])

credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
session = requests.Session()
response = session.post(BASE + "/admin/auth/signin", json={"email": credentials["email"], "password": credentials["password"]}, timeout=30)
response.raise_for_status()
session.headers["Authorization"] = "Bearer " + response.json()["token"]


def gql(query, variables=None):
    r = session.post(BASE + "/admin/graphql", json={"query": query, "variables": variables or {}}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:1500]}")
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"]))
    return body["data"]


keys = gql("""query { apiKeys(first: 200) { edges { node { id name } } } }""")["apiKeys"]["edges"]
key_ids = {e["node"]["id"]: e["node"]["name"] for e in keys if e["node"]["name"] in KEY_NAMES}
assert key_ids, "no matching api keys"

query = """query($after: Cursor, $since: Time!) {
  requests(first: 200, after: $after, orderBy: {field: CREATED_AT, direction: ASC}, where: {createdAtGTE: $since}) {
    pageInfo { hasNextPage endCursor }
    edges { node { id createdAt projectID apiKeyID modelID status stream format source clientIP
      contentSaved contentStorageKey
      executions { edges { node { id status format upstreamModelID responseStatusCode errorMessage metricsLatencyMs channel { name type } } } } } }
  }
}"""
out = []
after = None
while True:
    data = gql(query, {"after": after, "since": SINCE})["requests"]
    for e in data["edges"]:
        n = e["node"]
        if n["apiKeyID"] in key_ids:
            n["apiKeyName"] = key_ids[n["apiKeyID"]]
            out.append(n)
    if not data["pageInfo"]["hasNextPage"]:
        break
    after = data["pageInfo"]["endCursor"]
print(json.dumps(out))
