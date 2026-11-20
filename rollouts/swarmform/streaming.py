"""Optional streaming transport for OpenAI-compatible Chat Completions."""
import gzip
import json
import re
import time


async def collect_response(client, request, out, actor, turn):
    chunks = out / "provider-streams" / actor
    chunks.mkdir(parents=True, exist_ok=True)
    arguments = {k: v for k, v in request.items() if k != "stream"}
    with gzip.open(chunks / f"{turn:03d}.jsonl.gz", "xt") as log:
        async with client.chat.completions.stream(**arguments) as stream:
            async for event in stream:
                if event.type == "chunk":
                    row = {"at": time.time(), "chunk": event.chunk.model_dump(exclude_unset=True)}
                    log.write(json.dumps(row, separators=(",", ":")) + "\n")
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
