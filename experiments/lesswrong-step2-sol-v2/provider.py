"""Host-only AxonHub transport for the retry-tolerant Step 2 reproduction."""
from __future__ import annotations

import asyncio
import contextvars
import itertools
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from inspect_ai.model import ModelAPI, ModelCall, ModelOutput, modelapi
from inspect_ai.model._openai_responses import (
    openai_responses_chat_choices,
    openai_responses_inputs,
    openai_responses_tool_choice,
    openai_responses_tools,
)
from inspect_ai.model._providers.openai_responses import model_usage_from_response
from openai.types.responses import Response

MODEL = "gpt-5.6-sol"
ENDPOINT = "https://lmportal.iefbr14.xyz/v1/responses"
SCOPE = contextvars.ContextVar("lw_step2_scope", default="preflight")
COUNTER = itertools.count(1)
REQUEST_SESSION = uuid.uuid4().hex[:12]


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    temporary.replace(path)


def event(kind, **fields):
    root = Path(os.environ["SWH_LW_STEP2_OUTPUT"])
    with (root / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                                 "kind": kind, **fields}, default=str) + "\n")


@modelapi(name="axonhub_step2")
def axonhub_step2():
    return AxonHubStep2


class AxonHubStep2(ModelAPI):
    def max_connections(self):
        return 1

    def connection_key(self):
        return self.model_name

    def should_retry(self, ex):
        text = str(ex)
        return (
            text == "Provider stream ended without a terminal response"
            or text == "Provider stream error"
            or any(text == f"Provider HTTP {status}" for status in (408, 429, 500, 502, 503, 504))
        )

    async def generate(self, input, tools, tool_choice, config):
        if self.model_name != MODEL:
            raise ValueError(f"Only the registered model {MODEL} is allowed")
        messages = list(input)
        instructions = []
        while messages and messages[0].role == "system":
            instructions.append(messages.pop(0).text)
        body = {
            "model": self.model_name,
            "instructions": "\n\n".join(instructions),
            "input": await openai_responses_inputs(messages),
            "store": False,
            "stream": True,
            "parallel_tool_calls": False,
            "include": ["reasoning.encrypted_content"],
            "reasoning": {"effort": config.reasoning_effort or "high", "summary": "auto"},
        }
        tool_params = openai_responses_tools(tools, self.model_name, config, is_latest=True)
        if tool_params:
            body["tools"] = tool_params
            if tool_choice != "auto":
                body["tool_choice"] = openai_responses_tool_choice(tool_choice, tool_params)
        label = f"{REQUEST_SESSION}-{next(COUNTER):07d}-{self.model_name}"
        folder = Path(os.environ["SWH_LW_STEP2_OUTPUT"]) / "requests" / SCOPE.get()
        save(folder / f"{label}.request.json", body)
        started = time.monotonic()
        event("request_started", scope=SCOPE.get(), label=label, model=self.model_name)
        response = None
        try:
            credential = os.environ.get("AXONHUB_API_KEY", "").strip()
            if not credential:
                raise RuntimeError("AXONHUB_API_KEY is not configured; no request was sent")
            headers = {
                "Authorization": "Bearer " + credential,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "SwarmHarm-LessWrong-Step2/2.0",
            }
            async with asyncio.timeout(300):
                async with httpx.AsyncClient(timeout=300, trust_env=True) as client:
                    async with client.stream("POST", ENDPOINT, json=body, headers=headers) as stream:
                        if stream.status_code != 200:
                            raw = (await stream.aread()).decode(errors="replace")[:4000]
                            save(folder / f"{label}.error.json", {
                                "http_status": stream.status_code, "body": raw,
                            })
                            raise RuntimeError(f"Provider HTTP {stream.status_code}")
                        async for line in stream.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            try:
                                item = json.loads(line[5:])
                            except ValueError:
                                continue
                            if item.get("type") == "error":
                                save(folder / f"{label}.error.json", {"provider_error": item})
                                raise RuntimeError("Provider stream error")
                            if item.get("type") in {
                                "response.completed", "response.failed", "response.incomplete"
                            }:
                                response = item.get("response", {})
                                break
            if response is None:
                raise RuntimeError("Provider stream ended without a terminal response")
            save(folder / f"{label}.response.json", response)
            if response.get("status") != "completed":
                raise RuntimeError(f"Provider returned {response.get('status')}")
            if response.get("model") != self.model_name:
                raise RuntimeError("Provider model mismatch")
            if response.get("reasoning", {}).get("effort") != body["reasoning"]["effort"]:
                raise RuntimeError("Provider reasoning-effort mismatch")
            parsed = Response.model_validate(response)
            result = ModelOutput(
                model=response["model"],
                choices=openai_responses_chat_choices(self.model_name, parsed, tools),
                usage=model_usage_from_response(parsed),
            )
            elapsed = time.monotonic() - started
            event("request_completed", scope=SCOPE.get(), label=label,
                  model=self.model_name, elapsed_seconds=elapsed,
                  tool_calls=[call.function for call in (result.message.tool_calls or [])],
                  usage=response.get("usage"))
            return result, ModelCall(request=body, response=response, time=elapsed)
        except BaseException as error:
            elapsed = time.monotonic() - started
            safe_error = {"type": type(error).__name__, "message": str(error),
                          "elapsed_seconds": elapsed}
            save(folder / f"{label}.failure.json", safe_error)
            event("request_failed", scope=SCOPE.get(), label=label,
                  model=self.model_name, **safe_error)
            raise
