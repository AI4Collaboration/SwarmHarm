#!/usr/bin/env python3
"""Audit exported payloads/events without calling models or changing a trial."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
DATA = REPO / "data/simple-tasks/wayfinding"
sys.path.insert(0, str(DATA))
from local_world import outcomes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(directory):
    registration = json.loads((directory / "registration.json").read_text())
    task = (DATA / "family-2026-10-17/subject/task.txt").read_text()
    tools = [{**item, "strict": False} for item in json.loads((DATA / "family-2026-10-17/subject/tools.json").read_text())]
    requests = sorted(directory.rglob("*.request.json"))
    responses = sorted(directory.rglob("*.response.json"))
    assert requests, "No model requests"
    assert all(sha(REPO / relative) == expected for relative, expected in registration["input_code_hashes"].items()), "Registered code/input changed"
    model_matches = []
    reasoning_matches = []
    for path in responses:
        value = json.loads(path.read_text())
        model_matches.append(value.get("model") == registration["model"] and value.get("status") == "completed")
        reasoning_matches.append(value.get("reasoning", {}).get("effort") == registration["reasoning"])
    worlds = []
    histories_checked = 0
    for world_path in sorted(directory.glob("*/world.json")):
        world = json.loads(world_path.read_text())
        result_path = world_path.parent / "results.json"
        assert result_path.exists(), "World incomplete; audit after collection"
        actors = json.loads(result_path.read_text())
        for actor in actors:
            actor_dir = world_path.parent / actor["id"]
            history = [{"role": "user", "content": task}]
            actor_requests = sorted((actor_dir / "trace").glob("*.request.json"))
            for request_path in actor_requests:
                body = json.loads(request_path.read_text())
                assert body["input"] == history, "Actor history does not match its own exact outputs"
                assert body["instructions"] == registration["instructions"]
                assert body["tools"] == tools
                assert body["store"] is False and body["parallel_tool_calls"] is False
                assert body["model"] == registration["model"] and body["reasoning"]["effort"] == registration["reasoning"]
                assert "conversation" not in body and "previous_response_id" not in body
                assert [item for item in body["input"] if item.get("role") == "user"] == [{"role": "user", "content": task}], "Added subject prompt"
                response_path = request_path.with_name(request_path.name.replace(".request.json", ".response.json"))
                if not response_path.exists():
                    assert actor["status"] == "episode_error"
                    continue
                response = json.loads(response_path.read_text())
                history.extend(response["output"])
                calls = [item for item in response["output"] if item["type"] == "function_call"]
                label = request_path.name.removesuffix(".request.json")
                for index, item in enumerate(calls):
                    tool_path = request_path.parent / f"{label}-tool-{index+1}.json"
                    if not tool_path.exists():
                        assert actor["status"] in {"budget_exhausted", "episode_error"}
                        continue
                    record = json.loads(tool_path.read_text())
                    assert record["name"] == item["name"] and record["arguments"] == item["arguments"]
                    history.append({"type": "function_call_output", "call_id": item["call_id"],
                                    "output": json.dumps(record["result"], ensure_ascii=False)})
            assert json.loads((actor_dir / "history.json").read_text()) == history
            histories_checked += 1
        facts = outcomes(world)
        assert json.loads((world_path.parent / "outcomes.json").read_text()) == facts
        worlds.append({"id": world["world_id"], "condition": world["condition"],
                       "actors": [{key: item[key] for key in ("id", "status", "steps", "tools")} for item in actors],
                       "facts": facts,
                       "notice_exposed_actors": sorted({event["actor"] for event in world["events"] if event["operation"] == "describe" and event["accepted"]}),
                       "cleanup": json.loads((world_path.parent / "cleanup.json").read_text())})
    # Check actual local credential bytes without printing, saving, or using them.
    auth = json.loads((Path.home() / ".codex/auth.json").read_text()).get("tokens", {})
    needles = [value.encode() for key, value in auth.items()
               if key in {"access_token", "refresh_token", "id_token", "account_id"} and isinstance(value, str) and value]
    credential_free = all(not any(needle in path.read_bytes() for needle in needles)
                          for path in directory.rglob("*") if path.is_file())
    assert credential_free, "Credential-bearing trial artifact: do not export"
    behavioral_requests = [path for path in requests if "preflight" not in path.parts]
    behavioral_responses = [path for path in responses if "preflight" not in path.parts]
    return {
        "scope": "Operator read-only trace integrity audit; task-answer/intent review remains separate",
        "model": registration["model"], "reasoning": registration["reasoning"],
        "request_attempts": len(requests), "completed_responses": len(responses),
        "behavioral_request_attempts": len(behavioral_requests), "behavioral_completed_responses": len(behavioral_responses),
        "preflight_requests": len(requests) - len(behavioral_requests),
        "all_response_models_completed_and_match": all(model_matches),
        "all_response_reasoning_settings_match": all(reasoning_matches),
        "independent_stateless_actor_histories_checked": histories_checked,
        "exact_task_and_no_followup_user_prompts": True,
        "only_registered_function_tools": True,
        "native_tool_changes": registration["native_tool_changes"],
        "operator_credential_values_absent_from_artifacts": credential_free,
        "registered_code_and_inputs_unchanged": True,
        "worlds": worlds,
        "all_source_states_unchanged": all(item["facts"]["source_unchanged"] for item in worlds),
        "owned_resources_cleaned": all(not item["cleanup"]["provider_live"] for item in worlds),
        "causal_pressure_effect_established": False,
        "causal_propagation_established": False,
        "long_horizon_established": False,
        "auditor_sha256": sha(Path(__file__)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new JSON file")
    args = parser.parse_args()
    result = audit(args.run)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({key: result[key] for key in ("request_attempts", "completed_responses", "behavioral_request_attempts",
                                                  "independent_stateless_actor_histories_checked", "all_source_states_unchanged",
                                                  "operator_credential_values_absent_from_artifacts")}))


if __name__ == "__main__":
    main()
