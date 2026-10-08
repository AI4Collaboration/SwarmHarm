import json
import sys
from pathlib import Path

import requests

# 为 AxonHub 的 codex channel 打开 passThroughBody：原样转发 Responses API 请求体，
# 这样 Codex 放在 input 中的 additional_tools 项会被完整送到上游 Codex 后端。
BASE = "http://127.0.0.1:8090"
CHANNEL_ID = sys.argv[1]
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


before = gql(
    """query($id: ID!) { node(id: $id) { ... on Channel { id name type settings { passThroughBody passThroughUserAgent modelMappings { from to } autoTrimedModelPrefixes extraModelPrefix } } } }""",
    {"id": CHANNEL_ID},
)["node"]
settings = before["settings"] or {}
new_settings = {
    "passThroughBody": True,
    "passThroughUserAgent": settings.get("passThroughUserAgent"),
    "modelMappings": settings.get("modelMappings") or [],
    "autoTrimedModelPrefixes": settings.get("autoTrimedModelPrefixes") or [],
    "extraModelPrefix": settings.get("extraModelPrefix"),
}
new_settings = {k: v for k, v in new_settings.items() if v is not None}
gql(
    """mutation($id: ID!, $input: UpdateChannelInput!) { updateChannel(id: $id, input: $input) { id name settings { passThroughBody } } }""",
    {"id": CHANNEL_ID, "input": {"settings": new_settings}},
)
after = gql(
    """query($id: ID!) { node(id: $id) { ... on Channel { id name type status settings { passThroughBody passThroughUserAgent modelMappings { from to } } } } }""",
    {"id": CHANNEL_ID},
)["node"]
print(json.dumps({"before": before, "after": after}, indent=1))
