import argparse
import hashlib
import json
import shlex
from pathlib import Path

import httpx
from httpx_sse import EventSource

parser = argparse.ArgumentParser()
parser.add_argument("--export", dest="export_file", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--system-file", type=Path)
parser.add_argument("--system-sha", default="44a5fc31a371e626ccaaf3c77f737ac123338319163f34f992abee407751e525")
parser.add_argument("--subject-id", action="append", default=[])
parser.add_argument("--initial-task-file", type=Path)
parser.add_argument("--task-source", choices=["user", "issue-tool"], default="user")
parser.add_argument("--source-ip")
parser.add_argument("--tool-name", default="bash")
parser.add_argument("--expect-tool-output", action="append", default=[])
args = parser.parse_args()
data = json.loads(args.export_file.read_text())
verified_task_subjects = []


def text_content(message):
    value = message.get("content")
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return "".join(item["text"] for item in value if item.get("type") == "text")


events = data["forwarded"]
if args.source_ip:
    events = [event for event in events if event.get("source_ip") == args.source_ip]
if args.subject_id:
    events = [event for event in events if any(subject in text_content(message) for subject in args.subject_id for message in event["request"]["messages"] if message["role"] == "system")]
assert events, "Evidence requires selected forwarded requests"
event_ids = {event["event_id"] for event in events}
completions = [item for item in data["completions"] if item["event_id"] in event_ids]
assert completions, "Evidence requires completed inference responses"
completed_ids = {item["event_id"] for item in completions}
native = {item["trace"]["traceID"]: item for item in data["requests"] if item.get("trace")}
for item in completions:
    assert item["status"] == 200, item
    record = native[item["event_id"]]
    assert record["status"] == "completed", record["id"]
    assert record["modelID"] == "deepseek/deepseek-v4.1-flash-1017"
    assert all(execution["node"]["channel"]["name"] == "OpenRouter DeepSeek Flash 1017" for execution in record["executions"]["edges"])
messages = [message for event in events for message in event["request"]["messages"]]
system_messages = [text_content(message) for message in messages if message["role"] == "system"]
if args.system_file:
    system_bytes = args.system_file.read_bytes()
    assert hashlib.sha256(system_bytes).hexdigest() == args.system_sha
    expected_system = system_bytes.decode("utf-8")
    assert system_messages, "System instructions require a system-role message"
    assert all(message.startswith(expected_system) for message in system_messages), "System-role content requires the exact approved attachment prefix"
for subject in args.subject_id:
    assert any(subject in message for message in system_messages), subject
if args.initial_task_file:
    expected_task = args.initial_task_file.read_text().rstrip("\n")
    if args.task_source == "user":
        assert any(message["role"] == "user" and text_content(message) == expected_task for message in messages), "Initial task requires exact user-role content"
    else:
        issue_calls = set()
        for message in messages:
            for call in message.get("tool_calls", []):
                if call["function"]["name"] != "bash":
                    continue
                command = shlex.split(json.loads(call["function"]["arguments"])["command"])
                if any(command[index:index + 3] == ["multica", "issue", "get"] for index in range(len(command) - 2)):
                    issue_calls.add(call["id"])
        issues = [json.loads(text_content(message)) for message in messages if message["role"] == "tool" and message["tool_call_id"] in issue_calls]
        matching_issues = [issue for issue in issues if issue["description"] == expected_task]
        assert matching_issues, "Initial task requires exact issue description in the captured issue-get response"
        verified_task_subjects = sorted({issue["assignee_id"] for issue in matching_issues})
        assert set(args.subject_id) <= set(verified_task_subjects), "Every selected subject requires its exact assigned issue description"
response_artifacts = []
for completion in completions:
    file = args.export_file.parent / completion["response_file"]
    raw = file.read_bytes()
    response_artifacts.append({"event_id": completion["event_id"], "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "path": completion["response_file"]})
    if "text/event-stream" in completion["content_type"]:
        calls = {}
        text_parts = []
        response = httpx.Response(200, headers={"content-type": completion["content_type"]}, content=raw)
        for event in EventSource(response).iter_sse():
            if event.data == "[DONE]":
                continue
            chunk = json.loads(event.data)
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    text_parts.append(delta["content"])
                for call in delta.get("tool_calls", []):
                    index = (choice["index"], call["index"])
                    target = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    target["id"] += call.get("id", "")
                    for key in ["name", "arguments"]:
                        target["function"][key] += call.get("function", {}).get(key, "")
        messages.append({"role": "assistant", "content": "".join(text_parts), "tool_calls": list(calls.values())})
    else:
        response_body = json.loads(raw)
        messages.extend(choice["message"] for choice in response_body["choices"])
calls = {call["id"]: call for message in messages for call in message.get("tool_calls", []) if call["function"]["name"] == args.tool_name}
results = {message["tool_call_id"]: text_content(message) for message in messages if message["role"] == "tool"}
roundtrips = [{"tool_call_id": identifier, "name": call["function"]["name"], "arguments": json.loads(call["function"]["arguments"]), "result": results[identifier]} for identifier, call in calls.items() if identifier in results]
assert roundtrips, "Evidence requires an actual client tool call and returned tool result"
for expected in args.expect_tool_output:
    assert any(expected in record["result"] for record in roundtrips), expected
report = {"source_ips": sorted({event["source_ip"] for event in events if event.get("source_ip")}), "subject_ids": args.subject_id, "system_sha256": args.system_sha if args.system_file else None, "task_source": args.task_source if args.initial_task_file else None, "exact_initial_task_verified": bool(args.initial_task_file), "task_subject_ids_verified": verified_task_subjects, "forwarded_requests": len(events), "completed_responses": len(completions), "native_request_ids": [native[item["event_id"]]["id"] for item in completions], "tool_roundtrips": roundtrips, "response_artifacts": response_artifacts}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2))
args.output.chmod(0o600)
print(json.dumps({"forwarded_requests": len(events), "completed_responses": len(completions), "tool_roundtrips": len(roundtrips), "system_sha256": report["system_sha256"]}))
