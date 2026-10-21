import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--since", default="2026-10-21T23:10:00Z")
parser.add_argument("--bodies", action="store_true")
parser.add_argument("--source-ip")
args = parser.parse_args()
archive = Path("/var/lib/swh119-gateway")
events = [json.loads(line) for line in (archive / "requests.jsonl").read_text().splitlines() if line]
events = [event for event in events if datetime.fromisoformat(event["time"]) >= datetime.fromisoformat(args.since) and (args.source_ip is None or event.get("source_ip") == args.source_ip)]
if args.source_ip is not None:
    assert events, "Source IP requires matching forwarded campaign requests"
event_ids = {event["event_id"] for event in events}
completions = [json.loads(line) for line in (archive / "completions.jsonl").read_text().splitlines() if line]
completions = [item for item in completions if item["event_id"] in event_ids]
settings = json.loads(Path("/opt/swarmharm/swh119/key.json").read_text())
credentials = json.loads(Path("/opt/swarmharm/admin-credentials.json").read_text())["axonhub"]
session = requests.Session()
login = session.post("http://127.0.0.1:8090/admin/auth/signin", json=credentials, timeout=30)
login.raise_for_status()
session.headers["Authorization"] = "Bearer " + login.json()["token"]
body_fields = "requestBody responseBody responseChunks" if args.bodies else ""
query = """query($after: Cursor, $where: RequestWhereInput!) {
  requests(first: 100, after: $after, orderBy: {field: CREATED_AT, direction: ASC}, where: $where) {
    pageInfo { hasNextPage endCursor }
    edges { node { id createdAt externalID apiKeyID modelID reasoningEffort status stream format traceID trace { traceID }
      contentSaved contentStorageKey BODY_FIELDS
      executions { edges { node { id status format upstreamModelID responseStatusCode metricsLatencyMs channel { id name type } } } }
    } }
  }
}""".replace("BODY_FIELDS", body_fields)
records = []
cursor = None
where = {"apiKeyID": settings["api_key_id"], "createdAtGTE": args.since}
if args.source_ip is not None:
    where["hasTraceWith"] = [{"traceIDIn": sorted(event_ids)}]
while True:
    response = session.post("http://127.0.0.1:8090/admin/graphql", json={"query": query, "variables": {"after": cursor, "where": where}}, timeout=300)
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    page = body["data"]["requests"]
    records.extend(edge["node"] for edge in page["edges"])
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]
args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
if args.bodies:
    response_dir = args.output.parent / (args.output.stem + "-responses")
    response_dir.mkdir(mode=0o700, exist_ok=True)
    for completion in completions:
        name = completion["response_file"]
        assert Path(name).name == name
        shutil.copyfile(archive / name, response_dir / name)
        (response_dir / name).chmod(0o600)
        completion["response_file"] = str(Path(response_dir.name, name))
else:
    events = [{key: value for key, value in event.items() if key != "request"} for event in events]
args.output.write_text(json.dumps({"source_ip": args.source_ip, "forwarded": events, "completions": completions, "requests": records}, indent=2))
args.output.chmod(0o600)
print(json.dumps({"requests": len(records), "channels": sorted({execution["node"]["channel"]["name"] for record in records for execution in record["executions"]["edges"]}), "models": sorted({r["modelID"] for r in records})}))
