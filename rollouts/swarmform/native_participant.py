"""Native harness participant using the same task, workstation and cohort stop."""

import asyncio
import json
from pathlib import Path
import queue
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
import model_session


def _classify_native_error(error):
    text = str(error).lower()
    if any(marker in text for marker in (
        "usagelimitexceeded", "insufficient_quota", "insufficient_credits",
        "http error 401", "http error 402", "http error 403",
        "status 401", "status 402", "status 403", "401 unauthorized", "402 payment", "403 forbidden",
    )):
        return "provider_rejected"
    if any(marker in text for marker in (
        "http error 429", "status 429", "rate_limit", "rate limit", "too many requests",
        "http error 500", "http error 502", "http error 503", "http error 504",
        "http error 520", "http error 521", "http error 522", "http error 524", "http error 529",
        "status 500", "status 502", "status 503", "status 504", "status 529",
        "timed out", "connection reset", "connection closed", "broken pipe", "incomplete read",
        "service unavailable", "temporarily unavailable", "overloaded", "bad gateway",
        "gateway timeout", "upstream provider error",
    )):
        return "provider_unavailable"
    return "participant_error"


async def participate(cohort, actor):
    args = cohort.args
    events = queue.Queue()
    agent = None
    calls = {}
    prompt_start = 0.0
    idle_streak = 0
    from .__main__ import idle_continuation_delay, max_idle_continuations
    idle_cap = max_idle_continuations()
    usage = cohort.usage[actor] = {"responses": 0, "tools": 0, "tokens": 0}
    try:
        tools = cohort.visible["tools"]
        subscription = args.api_protocol == "subscription"
        agent = model_session.create(
            args.harness,
            actor,
            events,
            folder=cohort.out / "native" / actor,
            model=args.model.removeprefix("openai/") if subscription else args.model,
            **({"registered_model": args.model} if subscription else {}),
            api_base=None if subscription else args.base_url,
            api_key=args._api_key,
            api_protocol="native" if subscription else args.api_protocol,
            served_model=None if subscription else args.served_model,
            thinking_level=getattr(args, "thinking_level", None) or "high",
            **({"service_tier": args.service_tier} if getattr(args, "service_tier", None) else {}),
            max_output_tokens=16384,
            context_window=1_000_000,
            request_timeout_ms=args.seconds * 1000,
            tools=tools,
            active_tools=[t["name"] for t in tools],
            workstation_permissions=cohort.manifest["effective_settings"]["native_workstation_permissions"],
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
            if kind == "native_transport_error" and message.get("code") == "usageLimitExceeded":
                cohort.errors[actor] = "Codex subscription quota exhausted (usageLimitExceeded)"
                cohort.stop("provider_rejected")
                return
            if kind == "ready":
                if args.harness == "codex":
                    await asyncio.to_thread(cohort.station.stations[actor].bind_native_cwd, message["cwd"])
                    if not cohort.active():
                        return
                prompt_start = event_time
                agent.prompt(*cohort.prompts(actor))
            elif kind == "request" and args.api_protocol in ("native", "subscription"):
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
                    args.api_protocol in ("native", "subscription") and kind == "provider_response"
                )
                if count_usage:
                    usage["responses"] += 1
                    tokens = response.get("usage") or {}
                    count = tokens.get("total_tokens")
                    if count is None:
                        parts = [tokens.get(k) for k in ("prompt_tokens", "completion_tokens")]
                        if all(type(value) is int and value >= 0 for value in parts):
                            count = sum(parts)
                    if count is None and args.api_protocol in ("native", "subscription"):
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
                idle_streak = 0
                usage["tools"] += 1
                call_id = message["call_id"].split("|")[0]
                call = calls.get(call_id)
                tool_name = (call.get("name") if isinstance(call, dict) else None) or message.get("name")
                raw_args = (call.get("arguments") if isinstance(call, dict) else None)
                if raw_args is None:
                    raw_args = message.get("arguments")
                try:
                    arguments = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
                    command = arguments.get("command") if isinstance(arguments, dict) else None
                except (ValueError, TypeError):
                    command = None
                if tool_name != "bash" or not isinstance(command, str):
                    result = {"error": "Expected the bash tool with a string command"}
                else:
                    cohort.trace(
                        actor,
                        "tool_start",
                        call_id=call_id,
                        command=command,
                        decision_s=prompt_start,
                    )
                    result = await cohort.run_tool(actor, command, call_id)
                    if not cohort.active():
                        return
                formatter = getattr(cohort, "api_tool_reply", cohort.tool_reply)
                result = formatter(actor, result)
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
                idle_streak += 1
                if idle_cap and idle_streak > idle_cap:
                    if hasattr(cohort, "park_idle_actor"):
                        await cohort.park_idle_actor(actor, idle_streak)
                    return
                delay = idle_continuation_delay(idle_streak)
                if delay > 0 and hasattr(cohort, "wait_idle_backoff"):
                    await cohort.wait_idle_backoff(delay)
                    if not cohort.active():
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
        cohort.stop(_classify_native_error(error))
    finally:
        if agent is not None:
            # The coordinator can cancel a participant that is already closing
            # on its own deadline. Keep the export alive and join it before sealing.
            close_task = asyncio.create_task(asyncio.to_thread(agent.close))
            try:
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError:
                    await close_task
                    raise
            except Exception as error:
                cohort.errors["close_" + actor] = f"{type(error).__name__}: {error}"
                cohort.stop("participant_cleanup_error")
