import json
import sys
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8090"
credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
session = requests.Session()
response = session.post(BASE + "/admin/auth/signin", json={"email": credentials["email"], "password": credentials["password"]}, timeout=30)
response.raise_for_status()
session.headers["Authorization"] = "Bearer " + response.json()["token"]


def gql(query, variables=None):
    r = session.post(BASE + "/admin/graphql", json={"query": query, "variables": variables or {}}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:1500]}")
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"]))
    return body["data"]


def fields(type_name):
    t = gql("""query($n: String!) { __type(name: $n) { fields { name type { name kind ofType { name kind } } } inputFields { name type { name kind ofType { name kind } } } enumValues { name } } }""", {"n": type_name})["__type"]
    return t


mode = sys.argv[1]
if mode == "channels":
    print(json.dumps(fields("Channel"), indent=1)[:3000])
    print(json.dumps(fields("ChannelType"), indent=1)[:3000])
    data = gql("""query { channels(first: 50) { edges { node { id name type status baseURL supportedModels defaultTestModel settings { modelMappings { from to } } } } } }""")
    print(json.dumps(data, indent=1))
elif mode == "requests":
    print(json.dumps(fields("Request"), indent=1)[:4000])
elif mode == "dump":
    # 打印最近 N 条请求的请求体/响应体，用于排查工具调用丢失问题
    n = int(sys.argv[2])
    data = gql("""query($n: Int!) { requests(first: $n, orderBy: {field: CREATED_AT, direction: DESC}) { edges { node { id modelID status source format stream createdAt clientIP requestBody responseBody executions { edges { node { id requestID status format upstreamModelID requestURL passThroughApplied errorMessage responseStatusCode channel { name type } requestBody responseBody } } } } } } }""", {"n": n})
    print(json.dumps(data))
