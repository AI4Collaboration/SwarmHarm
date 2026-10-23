"""Host-only AxonHub Responses transport for every live model run.

The credential is read only from ``AXONHUB_API_KEY`` or an explicitly supplied
host-side key file.  It is never copied into a task container, registration,
trajectory, or repository file.
"""
import json
import os
from pathlib import Path
import signal
import threading
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request

MODEL = None
ENDPOINT = "https://lmportal.iefbr14.xyz/v1/responses"
API_KEY_ENV = "AXONHUB_API_KEY"
API_KEY_FILE = None
MAX_OUTPUT_TOKENS = None


def configure(model, base_url="https://lmportal.iefbr14.xyz/v1", key_env=API_KEY_ENV,
              key_file=None, max_output_tokens=None):
    global MODEL, ENDPOINT, API_KEY_ENV, API_KEY_FILE, MAX_OUTPUT_TOKENS
    url = urlsplit(base_url)
    if (url.scheme != "https" or not url.netloc or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("Use an HTTPS API base URL without credentials or query parameters")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Provide an explicit AxonHub model ID")
    if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError("max_output_tokens must be a positive integer")
    MODEL = model
    ENDPOINT = base_url.rstrip("/") + "/responses"
    API_KEY_ENV = key_env
    API_KEY_FILE = Path(key_file).expanduser() if key_file else None
    MAX_OUTPUT_TOKENS = max_output_tokens


def key():
    value = API_KEY_FILE.read_text().strip() if API_KEY_FILE else os.environ.get(API_KEY_ENV, "").strip()
    if not value:
        raise ValueError("No AxonHub API credential configured; no request was sent")
    if any(c.isspace() for c in value):
        raise ValueError("The AxonHub key file must contain only the key")
    return value


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def payload(body):
    if MODEL is None:
        raise ValueError("AxonHub route is not configured")
    if "max_output_tokens" in body:
        raise ValueError("Output allowance must come from the registered AxonHub transport setup")
    result = {"model": MODEL, "store": False, "stream": True,
              "parallel_tool_calls": False,
              "include": ["reasoning.encrypted_content"], **body}
    if MAX_OUTPUT_TOKENS is not None:
        result["max_output_tokens"] = MAX_OUTPUT_TOKENS
    return result


def call(body, directory, label, timeout=150):
    credential = key()
    request_body = payload(body)
    directory = Path(directory)
    save(directory / (label + ".request.json"), request_body)
    request = urllib.request.Request(ENDPOINT, data=json.dumps(request_body).encode(), headers={
        "Authorization": "Bearer " + credential, "Content-Type": "application/json",
        "Accept": "text/event-stream", "User-Agent": "SwarmHarm-AxonHub/1.0"})
    started = time.monotonic()
    response = None

    def timed_out(signum, frame):
        raise TimeoutError("Inference request exceeded wall time")

    use_process_alarm = threading.current_thread() is threading.main_thread()
    old_handler = signal.getsignal(signal.SIGALRM) if use_process_alarm else None
    old_timer = signal.setitimer(signal.ITIMER_REAL, 0) if use_process_alarm else None
    if use_process_alarm:
        signal.signal(signal.SIGALRM, timed_out)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            for line in stream:
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Inference request exceeded wall time")
                if not line.startswith(b"data:"):
                    continue
                try:
                    event = json.loads(line[5:])
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get("type") == "error":
                    error = event.get("error") if isinstance(event.get("error"), dict) else event
                    diagnostic = {k: str(error[k]).replace(credential, "[REDACTED]")
                                  for k in ("type", "code", "message", "status", "param") if k in error}
                    save(directory / (label + ".error.json"), {"provider_error": diagnostic})
                    raise RuntimeError("Inference stream returned an AxonHub error")
                if event.get("type") in ("response.completed", "response.failed", "response.incomplete"):
                    response = event.get("response", {})
                    break
    except urllib.error.HTTPError as error:
        diagnostic = {"http_status": error.code}
        try:
            parsed = json.loads(error.read(65536))
            nested = parsed.get("error", parsed)
            if isinstance(nested, dict):
                diagnostic["provider_error"] = {
                    k: str(nested[k]).replace(credential, "[REDACTED]")[:2048]
                    for k in ("type", "code", "message", "status", "param") if k in nested}
        except (ValueError, TypeError, AttributeError):
            pass
        save(directory / (label + ".error.json"), diagnostic)
        raise RuntimeError("AxonHub HTTP " + str(error.code)) from None
    except TimeoutError:
        save(directory / (label + ".error.json"), {"timeout_seconds": timeout})
        raise
    finally:
        if use_process_alarm:
            signal.setitimer(signal.ITIMER_REAL, *old_timer)
            signal.signal(signal.SIGALRM, old_handler)
    if response is None:
        save(directory / (label + ".error.json"), {"provider_error": "No terminal response"})
        raise RuntimeError("AxonHub stream ended without a terminal response")
    save(directory / (label + ".response.json"), response)
    if response.get("status") != "completed" or response.get("model") != MODEL:
        save(directory / (label + ".error.json"), {
            "provider_error": {"type": "model_or_status_mismatch",
                "requested_model": MODEL, "returned_model": response.get("model"),
                "status": response.get("status")},
            "native_error": response.get("error"),
            "incomplete_details": response.get("incomplete_details")})
        raise RuntimeError("AxonHub status/model mismatch; native response preserved")
    return response


def output_text(response):
    return "\n".join(c.get("text", "") for item in response.get("output", [])
                     if item.get("type") == "message" for c in item.get("content", [])
                     if c.get("type") == "output_text")
