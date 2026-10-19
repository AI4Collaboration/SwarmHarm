"""Host-only inference transport. Never inject this module or credentials into a subject."""
import json
import signal
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "gpt-6-luna"


class InferenceTimeout(TimeoutError):
    """Raised when a streaming response stops producing bytes before the deadline."""


def _raise_inference_timeout(signum, frame):
    raise InferenceTimeout("Inference request exceeded wall time")


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def call(body, directory, label, timeout=150):
    auth = json.loads((Path.home() / ".codex/auth.json").read_text())["tokens"]
    payload = {"model": MODEL, "store": False, "stream": True,
               "parallel_tool_calls": False, "include": ["reasoning.encrypted_content"], **body}
    directory = Path(directory)
    save(directory / f"{label}.request.json", payload)
    req = urllib.request.Request("https://chatgpt.com/backend-api/codex/responses",
        data=json.dumps(payload).encode(), headers={
            "Authorization": "Bearer " + auth["access_token"],
            "ChatGPT-Account-ID": auth["account_id"], "Content-Type": "application/json",
            "Accept": "text/event-stream", "User-Agent": "SwarmHarm-contained-safety-pilot/1.0"})
    started = time.monotonic()
    response = None
    # Calibration and natural worlds may submit provider calls from a thread
    # pool. Python only permits signal handlers/timers in the main thread, so
    # keep the hard alarm there and rely on urllib's socket timeout in workers.
    in_main_thread = threading.current_thread() is threading.main_thread()
    previous_handler = signal.getsignal(signal.SIGALRM) if in_main_thread else None
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0) if in_main_thread else None
    if in_main_thread:
        signal.signal(signal.SIGALRM, _raise_inference_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as stream:
            for line in stream:
                if time.monotonic() - started > timeout:
                    raise InferenceTimeout("Inference request exceeded wall time")
                if not line.startswith(b"data:"):
                    continue
                try:
                    event = json.loads(line[5:])
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get("type") == "error":
                    # Preserve only provider diagnostics needed to classify a
                    # failed run; do not persist the full event or request.
                    nested = event.get("error") if isinstance(event.get("error"), dict) else {}
                    save(directory / f"{label}.error.json", {
                        "provider_error": {
                            key: event.get(key)
                            for key in ("type", "code", "message", "status", "param")
                            if event.get(key) is not None
                        },
                        "provider_error_detail": {
                            key: nested.get(key)
                            for key in ("code", "message", "status", "param", "type")
                            if nested.get(key) is not None
                        },
                    })
                    raise RuntimeError("Inference stream returned an error")
                if event.get("type") in ("response.completed", "response.failed", "response.incomplete"):
                    response = event.get("response", {})
                    break
    except urllib.error.HTTPError as error:
        save(directory / f"{label}.error.json", {"http_status": error.code})
        raise RuntimeError(f"Inference HTTP {error.code}") from None
    except InferenceTimeout:
        save(directory / f"{label}.error.json", {"timeout_seconds": timeout})
        raise
    finally:
        if in_main_thread:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_handler)
    if response is None:
        raise RuntimeError("Inference stream ended without a terminal response")
    save(directory / f"{label}.response.json", response)
    if response.get("status") != "completed" or response.get("model") != MODEL:
        raise RuntimeError("Inference status/model mismatch")
    if response.get("reasoning", {}).get("effort") != body.get("reasoning", {}).get("effort"):
        raise RuntimeError("Inference reasoning setting mismatch")
    return response


def output_text(response):
    return "\n".join(c.get("text", "") for item in response.get("output", [])
                     if item.get("type") == "message" for c in item.get("content", [])
                     if c.get("type") == "output_text")
