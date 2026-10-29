"""Host-only Responses transport with durable single-attempt evidence.

The credential is read only from ``AXONHUB_API_KEY`` or an explicitly supplied
host-side key file.  It is never copied into a task container, registration,
trajectory, or repository file.
"""
import json
import os
import importlib.util
from pathlib import Path
import signal
import threading
import time
import uuid
from urllib.parse import urlsplit
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
GUARDRAIL_SPEC = importlib.util.spec_from_file_location(
    "swarmharm_transport_guardrails", HERE / "guardrails.py"
)
guardrails = importlib.util.module_from_spec(GUARDRAIL_SPEC)
GUARDRAIL_SPEC.loader.exec_module(guardrails)

ATOMIC_SPEC = importlib.util.spec_from_file_location("swarmharm_transport_atomic", HERE / "atomic.py")
atomic = importlib.util.module_from_spec(ATOMIC_SPEC)
ATOMIC_SPEC.loader.exec_module(atomic)

MODEL = None
ENDPOINT = "https://lmportal.iefbr14.xyz/v1/responses"
API_KEY_ENV = "AXONHUB_API_KEY"
API_KEY_FILE = None
MAX_OUTPUT_TOKENS = None
RESPONSE_MODEL_ALIASES = None


def configure(model, base_url="https://lmportal.iefbr14.xyz/v1", key_env=API_KEY_ENV,
              key_file=None, max_output_tokens=None, response_model_aliases=None):
    global MODEL, ENDPOINT, API_KEY_ENV, API_KEY_FILE, MAX_OUTPUT_TOKENS, RESPONSE_MODEL_ALIASES
    url = urlsplit(base_url)
    if (url.scheme != "https" or not url.netloc or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("Use an HTTPS API base URL without credentials or query parameters")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Provide an explicit AxonHub model ID")
    if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens < 1):
        raise ValueError("max_output_tokens must be a positive integer")
    if response_model_aliases is not None and (
        not isinstance(response_model_aliases,list) or not response_model_aliases
        or any(not isinstance(value,str) or not value for value in response_model_aliases)):
        raise ValueError('Response aliases must be explicit nonempty model identifiers')
    RESPONSE_MODEL_ALIASES = response_model_aliases
    MODEL = model
    ENDPOINT = base_url.rstrip("/") + "/responses"
    API_KEY_ENV = key_env
    API_KEY_FILE = Path(key_file).expanduser() if key_file else None
    MAX_OUTPUT_TOKENS = max_output_tokens


def key():
    value = API_KEY_FILE.read_text().strip() if API_KEY_FILE else os.environ.get(API_KEY_ENV, "").strip()
    if not value:
        raise ValueError("No API credential configured; no request was sent")
    if any(c.isspace() for c in value):
        raise ValueError("The AxonHub key file must contain only the key")
    return value


def save(path, value):
    atomic.atomic_json(path, value)


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
    directory.mkdir(parents=True, exist_ok=True)
    if any((directory / (label + suffix)).exists() for suffix in (".request.json", ".journal.jsonl", ".response.json")):
        raise RuntimeError("Existing request evidence: reconcile it without resending")
    identity = uuid.uuid4().hex
    try:
        with (directory / (label + ".claim")).open("x") as claim:
            claim.write(identity); claim.flush(); os.fsync(claim.fileno())
    except FileExistsError:
        raise RuntimeError("Existing request claim: reconcile it without resending") from None
    save(directory / (label + ".request.json"), request_body)
    request = urllib.request.Request(ENDPOINT, data=json.dumps(request_body).encode(), headers={
        "Authorization": "Bearer " + credential, "Content-Type": "application/json",
        "Accept": "text/event-stream", "User-Agent": "SwarmHarm-Responses/1.0",
        **({"X-OpenRouter-Metadata":"enabled"} if urlsplit(ENDPOINT).hostname=='openrouter.ai' else {})})
    journal = directory / (label + ".journal.jsonl")
    atomic.append_jsonl(journal, {"kind": "request_prepared", "local_request_id": identity,
                                "at": atomic.utc(), "endpoint": ENDPOINT})
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
        with guardrails.open_url(request, timeout=timeout) as stream:
            headers = getattr(stream, "headers", {})
            atomic.append_jsonl(journal, {"kind": "response_headers", "local_request_id": identity,
                "at": atomic.utc(), "headers": {name: str(headers[name]).replace(credential, "[REDACTED]")
                    for name in ("x-request-id", "request-id", "x-generation-id") if name in headers}})
            for line in stream:
                text = line.decode("utf-8", errors="replace")
                atomic.append_jsonl(directory / (label + ".stream.jsonl"),
                    {"at": atomic.utc(), "line": text.replace(credential, "[REDACTED]"),
                     "credential_redacted": credential in text})
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
                    raise RuntimeError("Inference stream returned a provider error")
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
        atomic.append_jsonl(journal, {"kind": "request_rejected" if error.code in (400,401,403,404,422) else "request_unknown",
            "local_request_id": identity, "http_status": error.code, "at": atomic.utc()})
        raise RuntimeError("Inference HTTP " + str(error.code)) from None
    except TimeoutError:
        save(directory / (label + ".error.json"), {"timeout_seconds": timeout})
        atomic.append_jsonl(journal, {"kind": "request_unknown", "local_request_id": identity,
                                    "error": "TimeoutError", "at": atomic.utc()})
        raise
    except Exception as error:
        if not (directory / (label + ".error.json")).exists():
            save(directory / (label + ".error.json"), {"error_type": type(error).__name__,
                 "message": str(error).replace(credential, "[REDACTED]")[:2048]})
        atomic.append_jsonl(journal, {"kind": "request_unknown", "local_request_id": identity,
                                    "error": type(error).__name__, "at": atomic.utc()})
        raise
    finally:
        if use_process_alarm:
            signal.setitimer(signal.ITIMER_REAL, *old_timer)
            signal.signal(signal.SIGALRM, old_handler)
    if response is None:
        save(directory / (label + ".error.json"), {"provider_error": "No terminal response"})
        atomic.append_jsonl(journal, {"kind": "request_unknown", "local_request_id": identity,
                                    "error": "No terminal response", "at": atomic.utc()})
        raise RuntimeError("Inference stream ended without a terminal response")
    save(directory / (label + ".response.json"), response)
    atomic.append_jsonl(journal, {"kind": "response_saved", "local_request_id": identity,
                                "provider_response_id": response.get("id"), "status": response.get("status"),
                                "at": atomic.utc()})
    if response.get("status") != "completed" or response.get("model") not in (RESPONSE_MODEL_ALIASES or [MODEL]):
        save(directory / (label + ".error.json"), {
            "provider_error": {"type": "model_or_status_mismatch",
                "requested_model": MODEL, "returned_model": response.get("model"),
                "status": response.get("status")},
            "native_error": response.get("error"),
            "incomplete_details": response.get("incomplete_details")})
        raise RuntimeError("Inference status/model mismatch; native response preserved")
    return response


def request_outcome(directory, label):
    """Unknown requests stay recoverable until a terminal provider record exists."""
    directory = Path(directory)
    journal = directory / (label + ".journal.jsonl")
    last = {"kind": "request_unknown", "reason": "No terminal transport record"}
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # A crash can leave an unfinished final append.
            if event.get("kind") in {"response_saved", "request_rejected", "request_unknown"}:
                last = event
    response_path = directory / (label + ".response.json")
    if last['kind'] == 'request_unknown' and response_path.exists():
        response = json.loads(response_path.read_text())
        if response.get('status') in {'completed','failed','incomplete'}:
            return {"kind":"response_saved", "provider_response_id":response.get('id'),
                    "status":response['status'], "source":"durable_response"}
    return last


def output_text(response):
    return "\n".join(c.get("text", "") for item in response.get("output", [])
                     if item.get("type") == "message" for c in item.get("content", [])
                     if c.get("type") == "output_text")
