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
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"]))
    return body["data"]


if sys.argv[1] == "introspect":
    schema = gql("""query { __schema { mutationType { fields { name args { name type { name kind ofType { name } } } } } } }""")
    names = [f for f in schema["__schema"]["mutationType"]["fields"] if "key" in f["name"].lower() or "project" in f["name"].lower()]
    print(json.dumps(names, indent=1))
    inputs = gql("""query { __type(name: "CreateAPIKeyInput") { inputFields { name type { name kind ofType { name kind } } } } }""")
    print(json.dumps(inputs, indent=1))
    projects = gql("""query { projects(first: 20) { edges { node { id name } } } }""")
    print(json.dumps(projects, indent=1))
    keys = gql("""query { apiKeys(first: 50) { edges { node { id name key status } } } }""")
    print(json.dumps(keys, indent=1))
elif sys.argv[1] == "create":
    # 为每个 runtime 创建独立的 API key，便于在 AxonHub 日志中区分来源
    project_id = sys.argv[2]
    out = {}
    for name in sys.argv[3:]:
        existing = gql("""query { apiKeys(first: 100) { edges { node { id name key status } } } }""")
        match = [e["node"] for e in existing["apiKeys"]["edges"] if e["node"]["name"] == name]
        if match:
            out[name] = match[0]["key"]
            continue
        created = gql(
            """mutation($input: CreateAPIKeyInput!) { createAPIKey(input: $input) { id name key status } }""",
            {"input": {"name": name, "projectID": project_id}},
        )
        out[name] = created["createAPIKey"]["key"]
    print(json.dumps(out))
