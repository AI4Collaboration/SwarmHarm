"""Native harness participant using the same task, workstation and cohort stop."""

import asyncio
import json
from pathlib import Path
import queue
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
import model_session
from .checkpoint import output_text


async def participate(cohort, actor):
    args = cohort.args
    events = queue.Queue()
    agent = None
    calls = {}
    prompt_start = 0.0
    usage = cohort.usage[actor] = {"responses": 0, "tools": 0, "tokens": 0}
    try:
        tools = cohort.visible["tools"]
        agent = model_session.create(
            args.harness,
            actor,
            events,
            folder=cohort.out / "native" / actor,
            model=args.model,
            api_base=args.base_url,
            api_key=args._api_key,
            api_protocol=args.api_protocol,
            served_model=args.served_model,
            thinking_level=getattr(args, "thinking_level", None) or "high",
            max_output_tokens=16384,
            context_window=1_000_000,
            request_timeout_ms=args.seconds * 1000,
            tools=tools,
            active_tools=[t["name"] for t in tools],
            job_context=None,
            goal_mode="off",
            on_transport_response=lambda response: events.put(
                (
                    actor,
                    {
                        "type": "transport_response",
                        "model": response.get("model"),
                        "usage": response.get("usage"),
                    },
                )
            ),
        )
        while cohort.active():
            try:
                _, message = await asyncio.to_thread(events.get, True, 0.25)
            except queue.Empty:
                continue
            if not cohort.active():
                return
            kind = message["type"]
            event_time = cohort.trace(actor, "native_event", event=message)
            if kind == "ready":
                prompt_start = event_time
                agent.prompt(*cohort.prompts(actor))
            elif kind == "request" and args.api_protocol == "native":
                payload = message.get("payload", {})
                # Pi exposes the provider request; SDK controllers expose their input projection.
                # Use only tool outputs explicitly present in the current request history.
                items = payload.get("input", [])
                if isinstance(items, list):
                    with cohort.lock:
                        for item in reversed(items):
                            if item.get("type") == "function_call" or item.get("role") == "assistant":
                                break
                            if item.get("type") == "function_call_output":
                                cohort.review.receipt(actor, item.get("call_id"), event_time,
                                                      output_text(item.get("output")))
                prompt_start = event_time
            elif kind in ("transport_response", "provider_response", "response_update"):
                response = (
                    message
                    if kind == "transport_response"
                    else message.get("response", {})
                    if kind == "response_update"
                    else message.get("event", {}).get("response", {})
                )
                if response.get("status") == "failed":
                    raise RuntimeError(str(response.get("error")))
                for call in response.get("output", []):
                    if call.get("type") == "function_call":
                        calls[call["call_id"]] = call
                count_usage = kind == "transport_response" or (
                    args.api_protocol == "native" and kind == "provider_response"
                )
                if count_usage:
                    usage["responses"] += 1
                    tokens = response.get("usage") or {}
                    count = tokens.get("total_tokens")
                    if count is None and args.api_protocol == "native":
                        fields = (
                            "input_tokens",
                            "output_tokens",
                            "cache_read_input_tokens",
                            "cache_creation_input_tokens",
                        )
                        values = [tokens.get(k, 0) for k in fields]
                        if all(type(value) is int and value >= 0 for value in values):
                            count = sum(values)
                    if type(count) is not int or count < 1:
                        raise ValueError(
                            "Provider must return positive token usage for matched budgets"
                        )
                    usage["tokens"] += count
            elif kind == "tool_call":
                usage["tools"] += 1
                call_id = message["call_id"].split("|")[0]
                call = calls[call_id]
                arguments = json.loads(call["arguments"])
                if call["name"] != "bash" or not isinstance(
                    arguments.get("command"), str
                ):
                    result = {"error": "Expected the bash tool with a string command"}
                else:
                    cohort.trace(
                        actor,
                        "tool_start",
                        call_id=call_id,
                        command=arguments["command"],
                        decision_s=prompt_start,
                    )
                    task = asyncio.create_task(
                        asyncio.to_thread(
                            cohort.tool, actor, arguments["command"], call_id
                        )
                    )
                    cohort.active_tools.add(task)
                    task.add_done_callback(
                        lambda done, call_id=call_id: cohort.tool_completed(
                            done, actor, call_id
                        )
                    )
                    result, _ = await asyncio.shield(task)
                result = cohort.tool_reply(actor, result)
                agent.reply(message["id"], output=json.dumps(result))
                if getattr(cohort, "allowance_exhausted", lambda _: False)(actor):
                    await cohort.retire_actor(actor)
                    return
            elif kind == "settled":
                if message.get("error_message"):
                    raise RuntimeError(message["error_message"])
                if getattr(cohort, "allowance_exhausted", lambda _: False)(actor):
                    await cohort.retire_actor(actor)
                    return
                prompt_start = event_time
                agent.prompt(cohort.continue_research(actor))
            elif kind in ("fatal", "exited", "closed"):
                raise RuntimeError(str(message))
    except asyncio.CancelledError:
        cohort.trace(actor, "cancelled", reason=cohort.reason)
        raise
    except Exception as error:
        cohort.errors[actor] = f"{type(error).__name__}: {error}"
        cohort.stop("participant_error")
    finally:
        if agent is not None:
            try:
                await asyncio.to_thread(agent.close)
            except Exception as error:
                cohort.errors["close_" + actor] = f"{type(error).__name__}: {error}"
                cohort.stop("participant_cleanup_error")
