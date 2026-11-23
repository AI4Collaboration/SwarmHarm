"""Optional streaming transport for OpenAI-compatible Chat Completions."""
import gzip
import json
import re
import time

import httpx


async def collect_response(client, request, out, actor, turn, attempt=1):
    chunks = out / "provider-streams" / actor
    chunks.mkdir(parents=True, exist_ok=True)
    arguments = {k: v for k, v in request.items() if k != "stream"}
    suffix = "" if attempt == 1 else f".attempt-{attempt}"
    with gzip.open(chunks / f"{turn:03d}{suffix}.jsonl.gz", "xt") as log:
        async with client.chat.completions.stream(**arguments) as stream:
            finished = False
            async for event in stream:
                if event.type == "chunk":
                    finished |= any(choice.index == 0 and choice.finish_reason is not None
                                    for choice in event.chunk.choices)
                    row = {"at": time.time(), "chunk": event.chunk.model_dump(exclude_unset=True)}
                    log.write(json.dumps(row, separators=(",", ":")) + "\n")
            if not finished:
                raise httpx.RemoteProtocolError("Stream ended before its finish reason")
            completion = await stream.get_final_completion()
    data = completion.model_dump(exclude_unset=True)
    for choice in data["choices"]:
        message = choice["message"]
        # Some compatible servers repeat the scalar role on each SSE delta.
        # The SDK concatenates it like content; restore the protocol value.
        if re.fullmatch(r"(?:assistant){2,}", message.get("role") or ""):
            message["role"] = "assistant"
        message.pop("parsed", None)
        for call in message.get("tool_calls") or []:
            call["function"].pop("parsed_arguments", None)
    return data
