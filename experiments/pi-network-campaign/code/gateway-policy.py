import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from aiohttp import ClientSession, ClientTimeout, web

credentials = json.loads(Path("/etc/swh119-gateway/credentials.json").read_text())


async def handle(request):
    authorization = request.headers.get("Authorization", "")
    if authorization != "Bearer " + credentials["key"]:
        return web.json_response({"error": {"message": "Campaign bearer credential required", "type": "campaign_policy"}}, status=401)
    if request.method != "POST" or request.path != "/v1/chat/completions" or request.query_string:
        return web.json_response({"error": {"message": "Campaign API route restricted", "type": "campaign_policy"}}, status=403)
    body = await request.json()
    if body.get("model") != credentials["model"]:
        return web.json_response({"error": {"message": "Campaign model restricted", "type": "campaign_policy"}}, status=403)
    if any(tool.get("type") != "function" for tool in body.get("tools", [])):
        return web.json_response({"error": {"message": "Campaign tools require client functions", "type": "campaign_policy"}}, status=403)
    if any(field in body for field in ["plugins", "web_search_options", "browser", "mcp_servers", "search_parameters"]):
        return web.json_response({"error": {"message": "Campaign hosted tools restricted", "type": "campaign_policy"}}, status=403)
    if body.get("reasoning") != {"effort": "high"}:
        return web.json_response({"error": {"message": "Campaign reasoning setting required", "type": "campaign_policy"}}, status=403)
    event_id = str(uuid4())
    with Path("/var/lib/swh119-gateway/requests.jsonl").open("a") as output:
        output.write(json.dumps({"event_id": event_id, "time": datetime.now(timezone.utc).isoformat(), "source_ip": request.headers.get("CF-Connecting-IP"), "trial_id": request.headers.get("X-SWH119-Trial"), "subject_id": request.headers.get("X-SWH119-Subject"), "request": body}) + "\n")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"authorization", "host", "content-length", "connection", "accept-encoding", "transfer-encoding"}}
    headers["Authorization"] = "Bearer " + credentials["backend_key"]
    headers["AH-Trace-Id"] = event_id
    async with ClientSession(timeout=ClientTimeout(total=900), auto_decompress=False) as session:
        async with session.post("http://127.0.0.1:8090/v1/chat/completions", json=body, headers=headers) as upstream:
            response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in {"content-length", "connection", "transfer-encoding"}}
            response_headers["X-SWH119-Event-ID"] = event_id
            response = web.StreamResponse(status=upstream.status, headers=response_headers)
            await response.prepare(request)
            with Path("/var/lib/swh119-gateway", event_id + ".response").open("wb") as archive:
                async for chunk in upstream.content.iter_any():
                    archive.write(chunk)
                    await response.write(chunk)
            with Path("/var/lib/swh119-gateway/completions.jsonl").open("a") as output:
                output.write(json.dumps({"event_id": event_id, "time": datetime.now(timezone.utc).isoformat(), "status": upstream.status, "request_id": upstream.headers.get("AH-Request-Id"), "content_type": upstream.headers.get("Content-Type"), "response_file": event_id + ".response"}) + "\n")
            await response.write_eof()
            return response


app = web.Application(client_max_size=32 * 1024 * 1024)
app.router.add_route("*", "/{path:.*}", handle)
web.run_app(app, host="127.0.0.1", port=8093, access_log=None)
