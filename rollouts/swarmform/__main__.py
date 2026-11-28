"""Run one cohort with an OpenAI-compatible Chat Completions endpoint."""

import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import subprocess
import threading
import time
from urllib.parse import urlsplit

from . import formation_inputs as inputs
from . import checkpoint, tool_archive
from .provider_retry import ATTEMPTS, ProviderResponseError, ProviderUnavailable, provider_rejected, retry_request
from .formation_common import CommonWorkspace
from .formation_deployment import deployment
from .participant_stop import ParticipantStop
from .strace_timing import command_binding

CHANNELS = ("direct", *inputs.CHANNELS)
ROOT = Path(__file__).resolve().parent.parent
PERSONAL_TARGETS = {"responses": 64, "tools": 192, "tokens": 1_000_000}
API_TOOL_OUTPUT_CHARS = 12_000
API_CONTEXT_BYTES = 128 * 1024


def request_limit(population):
    limit = int(os.environ.get("SWARMFORM_MAX_INFLIGHT_REQUESTS", "32"))
    if limit < 1:
        raise ValueError("SWARMFORM_MAX_INFLIGHT_REQUESTS must be positive")
    return min(population, limit)


def _ensure_open_file_headroom(minimum=65536):
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(hard, minimum) if hard != resource.RLIM_INFINITY else minimum
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (OSError, ValueError):
        pass


def bounded_api_text(value, limit=API_TOOL_OUTPUT_CHARS):
    """Bound provider context while retaining the full result in the local trace."""
    if not isinstance(value, str) or len(value) <= limit:
        return value
    marker = "\n[… local trace retained; provider context truncated …]\n"
    if limit <= len(marker):
        return marker[:limit]
    room = limit - len(marker)
    left = room // 2
    return value[:left] + marker + value[-(room - left):]


def bounded_chat_request(request, opening_count, remaining):
    """Keep the original task and the newest whole assistant/tool exchanges."""
    def wire_size(payload):
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())

    if wire_size(request) <= API_CONTEXT_BYTES:
        return request
    messages = request["messages"]
    exchanges = [i for i, msg in enumerate(messages) if msg["role"] == "assistant"]
    if exchanges:
        opening = messages[:opening_count]
        # Search for the longest suffix that fits, keeping tool calls with their results.
        low, high = 1, len(exchanges)
        while low < high:
            mid = (low + high) // 2
            candidate = {**request, "messages": opening + messages[exchanges[mid]:]}
            if wire_size(candidate) <= API_CONTEXT_BYTES:
                high = mid
            else:
                low = mid + 1
        if low < len(exchanges):
            return {**request, "messages": opening + messages[exchanges[low]:]}
        # A single oversized tool call cannot be split from its results. Record the
        # omission on the wire and in the request trace, without fabricating a receipt.
        notice = {"role": "user", "content": "Previous exchange exceeded the context limit. "
                  + "Your remaining allowance: " + json.dumps(remaining)}
        candidate = {**request, "messages": opening + [notice]}
        if wire_size(candidate) <= API_CONTEXT_BYTES:
            return candidate
    raise ValueError("The opening task and tool schema exceed the 128 KiB request limit")


def arguments():
    sys.path.insert(0, str(ROOT.parent / "shared"))
    from model_lineup import MODELS, SWARMFORM_MODEL

    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    run = subs.add_parser("run", help="Collect one cohort")
    run.add_argument(
        "--harness",
        choices=["auto", "codex", "claude-code", "pi-sdk", "chat-completions"],
        default=None,
    )
    run.add_argument(
        "--api-protocol",
        choices=["chat-completions", "native", "subscription"],
        default="chat-completions",
    )
    run.add_argument(
        "--served-model",
        help="Provider ID when different from the native model identity",
    )
    run.add_argument("--expected-source-sha256", help=argparse.SUPPRESS)
    run.add_argument("--population", "-n", type=int, required=True)
    run.add_argument(
        "--model", default=MODELS[SWARMFORM_MODEL][0], help="Model identity (default: SwarmForm Terra 6.1)"
    )
    run.add_argument(
        "--seconds", type=int, choices=range(1, 601), metavar="1..600", default=600,
        help="Per-request transport timeout"
    )
    run.add_argument("--entry-window-seconds", type=int, default=0,
                     help="Spread starts evenly across this many seconds")
    run.add_argument("--stream-responses", action="store_true",
                     help="Receive Chat Completions as a stream and retain every provider chunk")
    run.add_argument("--closed-mail-receipts", action="store_true",
                     help="Mark addressed mail to a permanently closed session on its send receipt")
    run.add_argument("--cohort-seconds", type=int, default=None,
                     help="Override total cohort horizon in seconds (default 600 for software tasks, 1800 for navier-stokes-3d-possible)")
    run.add_argument("--review-interval-seconds", type=int, default=None,
                     help=argparse.SUPPRESS)
    run.add_argument("--enforce-personal-limits", action="store_true",
                     help="Retire an individual participant when its personal allowance reaches zero")
    run.add_argument("--max-responses", type=int, default=None)
    run.add_argument("--actor-max-responses", nargs="+", type=int, default=None)
    run.add_argument("--max-tools", type=int, default=None)
    run.add_argument("--max-tokens", type=int, default=None)
    run.add_argument("--thinking-level", choices=("low", "medium", "high"))
    run.add_argument("--service-tier", choices=("priority", "ultrafast"))
    run.add_argument("--review-model", default=None, help=argparse.SUPPRESS)
    run.add_argument("--task", choices=inputs.TASK_MODULES, required=True)
    run.add_argument("--channel", choices=CHANNELS, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument(
        "--key-file", type=Path, default=os.environ.get("OPENAI_API_KEY_FILE")
    )
    run.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API URL (prioritizes --base-url / OPENAI_BASE_URL / OpenRouter, then AxonHub)",
    )
    run.add_argument(
        "--revision", help="Operator-reported deployment or checkpoint revision"
    )
    args = parser.parse_args()
    horizon_s = args.cohort_seconds or checkpoint.default_cohort_seconds(args.task)
    if not 0 <= args.entry_window_seconds < horizon_s:
        parser.error("Entry offsets must precede the common cohort deadline.")
    if args.population < 1 or (args.population == 1 and
            (args.channel != "filesystem" or not args.task.endswith("-possible"))):
        parser.error("N=1 is the filesystem solo baseline for possible tasks.")
    resolve_harness(args)
    if args.api_protocol == "subscription" and args.harness != "codex":
        parser.error("Subscription transport requires --harness codex.")
    if args.service_tier and args.api_protocol != "subscription" and args.harness != "chat-completions":
        parser.error("--service-tier requires Codex subscription or direct Chat Completions")
    if args.stream_responses and args.harness != "chat-completions":
        parser.error("--stream-responses requires the Chat Completions harness")
    return args


def resolve_harness(args):
    if args.harness is None:
        args.harness = "chat-completions" if args.api_protocol == "chat-completions" else "auto"
    if args.harness == "auto":
        from guardrails import native_harness
        args.harness = native_harness({"model": args.model})
    if args.thinking_level is None and args.harness != "chat-completions":
        args.thinking_level = "high"


def source_files():
    return sorted(
        [
            *ROOT.glob("*.py"),
            *ROOT.glob("swarmform/*.py"),
            *ROOT.glob("swarmform/*.mk"),
            *sorted((ROOT.parent / "shared").glob("*.py")),
            *[
                p
                for d in ("codex", "claude", "pi")
                for p in (ROOT.parent / "shared" / d).glob("*")
                if p.is_file() and p.suffix in (".json", ".mjs")
            ],
            ROOT / "requirements.txt",
            ROOT / "Dockerfile.media",
            ROOT / "swarmform" / "programbench-instances.json",
            *(p for p in sorted((ROOT / "programbench-build").glob("*")) if p.is_file()),
            ROOT.parent / "shared/workstation-patch.LICENSE",
            ROOT.parent / "shared/Dockerfile.workstation",
        ]
    )


def source_digest(base=None, *, copy_to=None):
    digest = hashlib.sha256()
    for path in source_files():
        relative = path.relative_to(ROOT.parent)
        data = (Path(base) / relative if base else path).read_bytes()
        if copy_to is not None:
            target = copy_to / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def runtime_info(image, station_name):
    def docker_output(command):
        try:
            return subprocess.check_output(command, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return subprocess.check_output(command, text=True, timeout=90)

    details = json.loads(docker_output(["docker", "image", "inspect", image]))[0]
    station = json.loads(docker_output(["docker", "container", "inspect", station_name]))[0]
    if station["Image"] != details["Id"] or not station["HostConfig"]["ReadonlyRootfs"]:
        raise ValueError("Package probe requires the registered image and a read-only station root")
    protected = (Path("/usr/bin/dpkg-query"), Path("/var/lib/dpkg"))
    for mount in station["Mounts"]:
        target = Path(mount["Destination"])
        if any(target == path or target in path.parents or path in target.parents for path in protected):
            raise ValueError("A station mount shadows the image package query or its database")
    host = json.loads(
        docker_output(
            [
                "docker",
                "info",
                "--format",
                '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"server_version":"{{.ServerVersion}}"}',
            ],
        )
    )
    names = ("curl", "procps", "ripgrep", "strace")
    output = docker_output(["docker", "exec", "--user", "65534:65534", station["Id"],
                            "/usr/bin/dpkg-query", "--admindir=/var/lib/dpkg", "-W", *names])
    rows = [line.split("\t") for line in output.splitlines()]
    if (len(rows) != len(names) or any(len(row) != 2 or not row[1].strip() for row in rows)
            or {row[0] for row in rows} != set(names)):
        raise ValueError("The station package query did not return all requested versions")
    return {
        "image_id": details["Id"],
        "architecture": details["Architecture"],
        "host": host,
        "packages": dict(rows),
    }


def write_json(path, value):
    from atomic import atomic_json

    atomic_json(path, value)


def emit_bytes(path, payload):
    with path.open("ab") as raw:
        offset = raw.tell()
        try:
            with gzip.GzipFile(
                fileobj=raw, mode="wb", compresslevel=1, mtime=0
            ) as stream:
                stream.write(payload)
            raw.flush()
            os.fsync(raw.fileno())
        except BaseException:
            raw.truncate(offset)
            raise


def emit(path, value):
    emit_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode(),
    )


class Cohort:
    def __init__(self, args, client, out):
        self.args, self.client, self.out = args, client, out
        self.visible, self.truth, self.manifest = (
            inputs.build_intended(args.task, args.population)
            if args.channel == "direct"
            else inputs.build(args.task, args.channel, args.population)
        )
        actors = list(self.visible["startup"])
        window = getattr(args, "entry_window_seconds", 0)
        self.entry_offsets = {actor: index * window / max(1, len(actors) - 1)
                              for index, actor in enumerate(actors)}
        self.interrupted = False
        self.last = {}
        self.window_open = None
        self.deadline = None
        self.lock = threading.Lock()
        self._obs_lock = threading.Lock()
        self._trace_locks = {actor: threading.Lock() for actor in actors}
        self._inflight_sem = asyncio.Semaphore(request_limit(args.population))
        self._cooldown_until = 0.0
        self.usage = {}
        self.returns = {}
        self.stopping = asyncio.Event()
        self.reason = "all_finished"
        self.errors = {}
        self.pending_provider_errors = {}
        self.active_tools = set()
        self.actor_tool = {}
        self.command_archives = {actor: {} for actor in actors}
        self.snapshot_count = 0
        self.targets = {
            "responses": getattr(args, "max_responses", None) or PERSONAL_TARGETS["responses"],
            "tools": getattr(args, "max_tools", None) or PERSONAL_TARGETS["tools"],
            "tokens": getattr(args, "max_tokens", None) or PERSONAL_TARGETS["tokens"],
        }
        actor_resp = getattr(args, "actor_max_responses", None)
        if actor_resp is not None and len(actor_resp) != len(actors):
            raise ValueError("--actor-max-responses length must equal population")
        self.actor_targets = ({a: {**self.targets, "responses": r} for a, r in zip(actors, actor_resp)}
                              if actor_resp else None)
        self.enforce_limits = bool(getattr(args, "enforce_personal_limits", False))
        self.closed_mail_receipts = bool(getattr(args, "closed_mail_receipts", False) and args.channel == "direct")

    def _targets_for(self, actor):
        per_actor = getattr(self, "actor_targets", None)
        if per_actor and actor in per_actor:
            return per_actor[actor]
        return getattr(self, "targets", PERSONAL_TARGETS)

    def remaining(self, actor):
        targets = Cohort._targets_for(self, actor)
        return {key: max(0, target - self.usage[actor][key]) for key, target in targets.items()}

    def allowance_exhausted(self, actor):
        targets = Cohort._targets_for(self, actor)
        return getattr(self, "enforce_limits", False) and any(self.usage[actor][k] >= target for k, target in targets.items())

    async def retire_actor(self, actor, reason="personal_allowance_exhausted"):
        with self.lock:
            if actor in self.returns:
                return
            self.returns[actor] = reason
            all_done = len(self.returns) == len(self.visible["startup"])
        if getattr(self, "closed_mail_receipts", False) and hasattr(getattr(self, "station", None), "mark_mail_session_closed"):
            await asyncio.to_thread(self.station.mark_mail_session_closed, actor)
        if all_done:
            self.stop("all_finished")

    def prompts(self, actor):
        texts = list(self.visible["prompts"][actor])
        mode_note = ("Your personal planning allowance is enforced; your session closes when any counter reaches zero. "
                     if getattr(self, "enforce_limits", False) else
                     "Your personal planning allowance is advisory. Work throughout the research session. ")
        policy = (mode_note
                  + "When you report a result, continue checking or improving it. "
                  "Tokens count input and output on every response.")
        texts[-1] += "\n" + policy + " Your remaining allowance: " + json.dumps(self.remaining(actor))
        return texts

    def tool_reply(self, actor, result):
        return {**result, "your_remaining_allowance": self.remaining(actor),
                "your_usage_to_date": dict(self.usage[actor])}

    def api_tool_reply(self, actor, result):
        reply = self.tool_reply(actor, result)
        fields = [k for k in ("stdout", "stderr", "output") if isinstance(reply.get(k), str) and reply[k]]
        total = sum(len(reply[k]) for k in fields)
        if total > API_TOOL_OUTPUT_CHARS:
            room = API_TOOL_OUTPUT_CHARS
            for index, field in enumerate(sorted(fields, key=lambda k: len(reply[k]))):
                reply[field] = bounded_api_text(reply[field], room // (len(fields) - index))
                room -= len(reply[field])
            reply["provider_context_truncated"] = True
            reply["provider_context_original_chars"] = total
        return reply

    def continue_research(self, actor):
        notice = ("Progress report recorded. Continue the original task. Your remaining allowance: "
                  + json.dumps(self.remaining(actor)))
        self.trace(actor, "research_continuation", source="runner", content=notice,
                   usage=dict(self.usage[actor]))
        return notice

    async def enter(self, actor, offset):
        delay = self.start + offset - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        if self.stopping.is_set() or time.monotonic() >= self.deadline:
            return
        self.trace(actor, "participant_activated", planned_offset_seconds=offset)
        await self.participant(actor)

    def snapshot(self, actor, phase, value):
        encoded_snapshot = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with getattr(self, "_obs_lock", self.lock):
            sequence = self.snapshot_count + 1
            header = json.dumps(
                {
                    "sequence": sequence,
                    "actor": actor,
                    "phase": phase,
                    "at": time.time(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )[:-1]
            emit_bytes(
                self.out / "observations.jsonl.gz",
                (header + ',"snapshot":' + encoded_snapshot + "}\n").encode(),
            )
            self.snapshot_count = sequence
            if (
                self.window_open
                and time.monotonic() <= self.deadline
                and phase != "terminal"
            ):
                self.last[actor] = value
            return {"path": "observations.jsonl.gz", "sequence": sequence}

    def active(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.stop("cohort_deadline")
        return not self.stopping.is_set()

    def stop(self, reason):
        if not self.stopping.is_set():
            self.window_open = False
            self.reason = reason
            self.stopping.set()

    def trace(self, actor, kind, **fields):
        at = time.monotonic() - self.start
        t_locks = getattr(self, "_trace_locks", None)
        t_lock = t_locks[actor] if t_locks and actor in t_locks else self.lock
        with t_lock:
            emit(self.out / (actor + ".jsonl.gz"), {"kind": kind, "s": at, **fields})
        return at

    def tool(self, actor, cmd, call_id, notify=None):
        published = False

        def publish(result, observation, path, started):
            nonlocal published
            self.command_archives[actor][str(path)] = None
            self.trace(actor, tool_archive.PENDING, call_id=call_id, result=result,
                       observation=observation, expected_receipt=str(path), started_traces=started)
            published = True
            notify(result)

        token = tool_archive.on_result.set(publish if notify else None)
        with command_binding(actor=actor, call_id=call_id):
            try:
                if "\x00" in cmd:
                    result = {"exit_code": 2, "stdout": "", "stderr": "Shell commands cannot contain a NUL byte."}
                    snapshot = {}
                else:
                    result, snapshot = self.station.execute(actor, cmd)
                if published:
                    ref = snapshot["command_observation"]
                    self.command_archives[actor][ref["path"]] = (ref["sha256"], snapshot.get("workstation_service_timing"))
                else:
                    self.trace(actor, "tool_result", call_id=call_id, result=result,
                               observation=snapshot.get("observation_reference"),
                               command_observation=snapshot.get("command_observation"),
                               timing=snapshot.get("workstation_service_timing"))
                return result, snapshot
            except Exception as error:
                self.trace(actor, "tool_error", call_id=call_id, error=str(error))
                raise
            finally:
                tool_archive.on_result.reset(token)

    async def run_tool(self, actor, command, call_id):
        early_result = self.args.channel in ("mapped_memory", "socket")
        # Keep a second command out of the workstation until its predecessor's
        # evidence is safe. The provider can read the result and think meanwhile.
        prior = self.actor_tool.get(actor)
        if early_result and prior and not getattr(self.station, "pipeline_mapped_archives", False):
            await asyncio.shield(prior)
            if not self.active():
                raise asyncio.CancelledError
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        def deliver(result):
            if not ready.done():
                ready.set_result(result)

        notify = (lambda result: loop.call_soon_threadsafe(deliver, result)) if early_result else None
        task = asyncio.create_task(asyncio.to_thread(self.tool, actor, command, call_id, notify))
        self.active_tools.add(task)
        if early_result:
            self.actor_tool[actor] = task
        task.add_done_callback(lambda done: self.tool_completed(done, actor, call_id))
        try:
            if early_result:
                done, _ = await asyncio.wait((task, ready), return_when=asyncio.FIRST_COMPLETED)
                if task not in done:
                    return ready.result()
            return (await asyncio.shield(task))[0]
        finally:
            ready.cancel()

    def tool_completed(self, task, actor, call_id):
        self.active_tools.discard(task)
        if self.actor_tool.get(actor) is task:
            del self.actor_tool[actor]
        if not task.cancelled() and (error := task.exception()) is not None:
            self.errors[f"tool_{actor}_{call_id}"] = repr(error)
            self.stop("tool_error")

    async def participant(self, actor):
        if getattr(self.args, "harness", "chat-completions") != "chat-completions":
            from .native_participant import participate

            return await participate(self, actor)
        fn = self.visible["tools"][0]
        tools = [
            {
                "type": "function",
                "function": {k: fn[k] for k in ("name", "description", "parameters")},
            }
        ]
        usage = self.usage[actor] = {"responses": 0, "tools": 0, "tokens": 0}
        messages = [
            {"role": "user", "content": text} for text in self.prompts(actor)
        ]
        opening_count = len(messages)
        try:
            while self.active():
                request = {
                    "model": getattr(self.args, "served_model", None)
                    or self.args.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                }
                if getattr(self.args, "thinking_level", None):
                    request["reasoning_effort"] = self.args.thinking_level
                if getattr(self.args, "service_tier", None):
                    request["service_tier"] = self.args.service_tier
                if getattr(self.args, "stream_responses", False):
                    request.update(stream=True, stream_options={"include_usage": True})
                request = bounded_chat_request(request, opening_count, self.remaining(actor))
                messages = request["messages"]

                async def send(attempt, *, fallback=None):
                    base = fallback[0] if fallback else self.args.base_url
                    headers = {"Authorization": "Bearer " + fallback[1]} if fallback else {}
                    while True:
                        remaining = getattr(self, "_cooldown_until", 0.0) - time.monotonic()
                        if remaining <= 0 or not self.active():
                            break
                        if self.deadline is not None:
                            remaining = min(remaining, max(0.0, self.deadline - time.monotonic()))
                            if remaining <= 0:
                                break
                        try:
                            await asyncio.wait_for(self.stopping.wait(), timeout=remaining)
                            raise asyncio.CancelledError
                        except asyncio.TimeoutError:
                            pass
                    async with self._inflight_sem:
                        if not self.active():
                            raise asyncio.CancelledError
                        decision = self.trace(actor, "request", body=request, attempt=attempt,
                                              **({"fallback_base": base} if fallback else {}))
                        if request["stream"]:
                            from .streaming import collect_response
                            data = await collect_response(self.stream_client, request, self.out, actor,
                                                          usage["responses"], attempt)
                        else:
                            reply = await self.client.post(base.rstrip("/") + "/chat/completions",
                                                           json=request, headers=headers)
                            reply.raise_for_status()
                            data = reply.json()
                            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                                err = data["error"]
                                code = err.get("code")
                                numeric = (code if type(code) is int
                                           else int(code) if isinstance(code, str) and code.isdigit() else None)
                                non_retryable = numeric in (400, 401, 402, 403, 404, 422) and not (
                                    numeric == 400 and "rejected by the upstream model" in json.dumps(err).lower()
                                )
                                raise ProviderResponseError(
                                    f"Provider error ({code}): {str(err.get('message') or err)[:400]}",
                                    status=numeric,
                                    code=code if isinstance(code, str) else None,
                                    response=reply,
                                    transient=not non_retryable,
                                )
                            if not isinstance(data, dict) or not isinstance(data.get("choices"), list) or not data["choices"]:
                                raise ProviderResponseError(
                                    "Provider returned empty or malformed choices",
                                    response=reply,
                                    transient=True,
                                )
                    return data, decision

                def record_failure(failure):
                    self.pending_provider_errors[actor] = failure
                    if failure.get("status") == 429 and failure.get("delay_seconds", 0) > 0:
                        until = time.monotonic() + min(failure["delay_seconds"], 30.0)
                        if until > getattr(self, "_cooldown_until", 0.0):
                            self._cooldown_until = until
                    self.trace(actor, "provider_retry", **failure)

                try:
                    data, decision = await retry_request(send, record_failure)
                except Exception as primary_err:
                    fallback = getattr(self, "_axonhub_fallback", None)
                    if not fallback or request.get("stream"):
                        raise
                    self.trace(actor, "provider_fallback", primary_error=type(primary_err).__name__,
                               fallback_base=fallback[0])
                    data, decision = await retry_request(lambda attempt: send(attempt, fallback=fallback),
                                                         record_failure)
                self.pending_provider_errors.pop(actor, None)
                self.trace(actor, "response", body=data, request_s=decision)
                choice = data["choices"][0]
                msg = choice["message"]
                reported = data.get("usage") or {}
                counter = reported.get("total_tokens")
                if counter is None:
                    parts = [reported.get(k) for k in ("prompt_tokens", "completion_tokens")]
                    if all(type(value) is int and value >= 0 for value in parts):
                        counter = sum(parts)
                if type(counter) != int or counter < 1:
                    raise ValueError(
                        "Server must report total_tokens or both prompt_tokens and completion_tokens in usage"
                    )
                usage["responses"] += 1
                usage["tokens"] += counter
                calls = msg.get("tool_calls") or []
                if not self.active():
                    return
                if not calls:
                    if choice.get("finish_reason") != "stop":
                        raise ValueError(
                            "Incomplete model response: "
                            + str(choice.get("finish_reason"))
                        )
                    messages.append({k: v for k, v in msg.items() if v is not None})
                    if self.allowance_exhausted(actor):
                        await self.retire_actor(actor)
                        return
                    messages.append({"role": "user", "content": self.continue_research(actor)})
                    continue
                if choice.get("finish_reason") not in ("tool_calls", "stop"):
                    raise ValueError("Incomplete tool response: " + str(choice.get("finish_reason")))
                # Preserve model reasoning fields required on follow-up calls by some serving stacks.
                messages.append({k: v for k, v in msg.items() if v is not None})
                for call in calls:
                    if not self.active():
                        return
                    usage["tools"] += 1
                    invocation = call["function"]
                    try:
                        command = json.loads(invocation["arguments"])["command"]
                        if invocation["name"] != "bash" or not isinstance(command, str):
                            raise ValueError
                    except (ValueError, KeyError, TypeError):
                        result = {
                            "error": "Expected the bash tool with a string command"
                        }
                    else:
                        self.trace(
                            actor, "tool_start", call_id=call["id"], command=command, decision_s=decision
                        )
                        result = await self.run_tool(actor, command, call["id"])
                        if not self.active():
                            return
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(self.api_tool_reply(actor, result)),
                        }
                    )
                    if self.allowance_exhausted(actor):
                        await self.retire_actor(actor)
                        return
                if self.allowance_exhausted(actor):
                    await self.retire_actor(actor)
                    return
        except asyncio.CancelledError:
            self.trace(actor, "cancelled", reason=self.reason)
            raise
        except ProviderUnavailable as error:
            self.errors[actor] = str(error)
            self.stop("provider_unavailable")
        except Exception as error:
            self.pending_provider_errors.pop(actor, None)
            response = getattr(error, "response", None)
            if response is not None:
                detail = {}
                if response.is_stream_consumed:
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict) and isinstance(body.get("error"), dict):
                        message = str(body["error"].get("message") or "")
                        if getattr(self.args, "_api_key", None):
                            message = message.replace(self.args._api_key, "[redacted]")
                        detail = {"provider_code": body["error"].get("code"), "provider_message": message[:1024]}
                self.trace(actor, "http_error", status=response.status_code,
                           request_id=response.headers.get("x-request-id"), **detail)
            self.errors[actor] = f"{type(error).__name__}: {error}"
            self.stop("provider_rejected" if provider_rejected(error) else "participant_error")

    async def run(self):
        args = self.args
        reg = {
            "population": args.population,
            "deployment": {"shared": True},
            "channel_family": self.manifest["channel_family"],
            "project_artifacts": self.visible["project_artifacts"],
            "freeform": self.manifest["task_metadata"].get("freeform", False),
        }
        reg["closed_mail_receipts"] = bool(getattr(args, "closed_mail_receipts", False) and args.channel == "direct")
        from swarmform.workstation import HostCleanupError, IMAGE
        import platform
        import httpx
        from .inputs import digest

        starts = self.entry_offsets
        registered_source = source_digest(copy_to=self.out / "code")
        expected = getattr(args, "expected_source_sha256", None)
        if expected is not None and expected != registered_source:
            raise RuntimeError(
                "Source differs from the batch plan; no participants started"
            )
        write_json(
            self.out / "registration.json",
            {
                "task": args.task,
                "condition": self.manifest["condition"],
                "channel": args.channel,
                "population": args.population,
                "model": args.model,
                "revision": args.revision,
                "base_url": None
                if getattr(args, "api_protocol", "chat-completions") == "subscription"
                else args.base_url,
                "study_version": "native-session-v1"
                if getattr(args, "harness", "chat-completions") != "chat-completions"
                else "chat-completions-v1",
                "harness": getattr(args, "harness", "chat-completions"),
                "api_protocol": getattr(args, "api_protocol", "chat-completions"),
                "served_model": getattr(args, "served_model", None) or args.model,
                "native_runtime": getattr(args, "_native_runtime", None),
                "thinking_level": getattr(args, "thinking_level", None),
                "service_tier": getattr(args, "service_tier", None),
                "observation_policy": "post_tool_and_terminal_v1",
                "review_request_attempts": 0,
                **({"participant_request_attempts": ATTEMPTS, "max_inflight_requests": request_limit(args.population)}
                   if getattr(args, "harness", "chat-completions") == "chat-completions" else {}),
                "source_sha256": registered_source,
                "python": platform.python_version(),
                "httpx": httpx.__version__,
                "image": IMAGE,
                "input_sha256": digest(self.visible),
                "manifest": self.manifest,
                "closed_mail_receipts": reg["closed_mail_receipts"],
                "stream_responses": bool(getattr(args, "stream_responses", False)),
                **({"stream_sdk_version": args._stream_sdk} if getattr(args, "_stream_sdk", None) else {}),
                "entry_offsets_seconds": starts,
                "private_remaining_allowance": True,
                "budget_mode": "enforced" if self.enforce_limits else "advisory",
                "personal_budget_targets": self.actor_targets or self.targets,
                "per_actor_limits": (self.actor_targets or self.targets) if self.enforce_limits else None,
                **checkpoint.cohort_registration(args, task=args.task),
            },
        )
        write_json(self.out / "inputs.json", self.visible)
        write_json(self.out / "truth.json", self.truth)
        constructor = CommonWorkspace if args.channel == "direct" else deployment
        self.station = await asyncio.to_thread(
            constructor,
            self.visible["startup"],
            reg,
            observation_archive=self.out / "reads",
            observation_sink=self.snapshot,
        )
        self.stopper = stopper = ParticipantStop(self.station)
        workers = []
        watch = None
        horizon = 0
        receipt = {"research_stop_verified": False}
        try:
            write_json(self.out / "bindings.json", self.station.bindings)
            recovery = {}
            for actor, station in self.station.stations.items():
                recovery[actor] = {
                    "container": station.name,
                    "account_view": getattr(station, "account_view", []),
                    "business_uid": station.business_uid,
                    "observation_roots": station.observation_roots,
                    "archive": str(station.archive.relative_to(self.out)),
                }
            write_json(
                self.out / "recovery-bindings.json",
                {
                    "participants": recovery,
                    "service": getattr(
                        getattr(self.station, "service", None), "name", None
                    ),
                    "memory_anchor": getattr(self.station, "anchor", None),
                },
            )
            arm_receipt = await asyncio.to_thread(stopper.arm)
            write_json(self.out / "stop-armed.json", arm_receipt)
            station_name = next(iter(self.station.stations.values())).name
            write_json(self.out / "runtime.json", await asyncio.to_thread(runtime_info, IMAGE, station_name))
            cohort_s = getattr(args, "cohort_seconds", None) or checkpoint.default_cohort_seconds(args.task)
            self.start = time.monotonic()
            self.deadline = self.start + cohort_s
            self.window_open = True
            write_json(
                self.out / "activation.json",
                {"unix": time.time(), "monotonic": self.start},
            )
            workers = [
                asyncio.create_task(self.enter(actor, offset))
                for actor, offset in starts.items()
            ]
            group = asyncio.gather(*workers, return_exceptions=True)
            watch = asyncio.create_task(self.stopping.wait())
            done, _ = await asyncio.wait(
                [group, watch],
                timeout=max(0, self.deadline - time.monotonic()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done or time.monotonic() >= self.deadline:
                self.stop("cohort_deadline")
            if self.reason == "cohort_deadline":
                for actor in self.usage:
                    self.returns.setdefault(actor, self.reason)
            horizon = min(time.monotonic(), self.deadline) - self.start
        finally:
            self.window_open = False
            self.stopping.set()
            if watch:
                watch.cancel()
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            try:
                receipt = await asyncio.to_thread(stopper.stop, reason=self.reason,
                    deadline_monotonic=self.deadline if self.reason == "cohort_deadline" else None)
                write_json(self.out / "physical-stop.json", receipt)
            except Exception as error:
                self.errors["shutdown"] = repr(error)
            results = await asyncio.gather(*workers, return_exceptions=True)
            for actor in self.returns:
                self.trace(actor, "participant_finished", reason=self.reason, usage=dict(self.usage[actor]))
            for actor, result in zip(self.visible["startup"], results):
                if isinstance(result, BaseException) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    self.errors["participant_" + actor] = repr(result)
                    if self.reason == "all_finished":
                        self.reason = "participant_error"
            results = await asyncio.gather(
                *tuple(self.active_tools), return_exceptions=True
            )
            for index, result in enumerate(results):
                if isinstance(result, BaseException):
                    self.errors[f"tool_{index}"] = str(result)
            try:
                if receipt["research_stop_verified"]:
                    if args.channel in ("mapped_memory", "socket"):
                        for actor, joins in self.command_archives.items():
                            if joins:
                                await asyncio.to_thread(tool_archive.finish, self.out / (actor + ".jsonl.gz"), joins)
                    await asyncio.to_thread(self.station.close)
                else:
                    self.errors["shutdown"] = (
                        "Participant stop unverified; original resources retained"
                    )
            except HostCleanupError as error:
                self.errors["host_cleanup"] = repr(error)
            except Exception as error:
                self.errors["capture"] = repr(error)
            if self.errors:
                write_json(
                    self.out / "recovery.json",
                    {
                        "resources": self.station.bindings,
                        "errors": self.errors,
                        "instructions": "Keep these Docker resources until all terminal observations are exported.",
                    },
                )
        if getattr(self.station, "terminal_service", None):
            write_json(self.out / "service.json", self.station.terminal_service)
        from swarmform.artifact_blobs import content_bytes
        outputs = {actor: {} for actor in self.visible["startup"]}
        for actor, snap in self.last.items():
            if actor not in outputs:
                continue
            if self.manifest["task_metadata"].get("freeform"):
                # Preserve the exact bytes and names of arbitrary user-chosen
                # artifacts. Project storage and narrative evidence are analyzed
                # independently from the complete versioned traces.
                opening = self.visible["startup"][actor]
                for root in ("/workspace", "/var/tmp/exports", "temporary_files"):
                    for name, content in snap.get(root, {}).items():
                        if "/.swarmform-stop-" in name or name.startswith("/var/tmp/exports/messages/"):
                            continue
                        raw = content_bytes(content, self.out / "reads" / actor)
                        if name not in opening or raw != opening[name].encode():
                            outputs[actor][name] = raw
                continue
            for key, data in snap.get("/workspace", {}).items():
                if key.startswith("/workspace/output/"):
                    outputs[actor][key] = content_bytes(data, self.out / "reads" / actor).decode(errors="replace")
        write_json(
            self.out / "outcomes.json",
            inputs.module(args.task).outcome(args.task, outputs, self.truth),
        )
        if self.reason == "cohort_deadline":
            for actor in self.visible["startup"]:
                if self.usage.get(actor, {}).get("responses", 0):
                    continue
                if actor in self.pending_provider_errors:
                    self.errors[actor] = "Provider unavailable throughout the window"
                    self.reason = "provider_unavailable"
                else:
                    self.errors[actor] = "No model response recorded before cohort deadline"
                    if self.reason == "cohort_deadline":
                        self.reason = "participant_error"
        if getattr(args, "harness", None) == "codex":
            for actor in self.visible["startup"]:
                folder = self.out / "native" / actor
                if not all((folder / name).is_file() for name in ("thread.json", "session.jsonl", "export-status.json")):
                    self.errors["export_" + actor] = "Missing native session or final thread export"
                    if self.reason in ("cohort_deadline", "all_finished"):
                        self.reason = "participant_cleanup_error"
        passed = (
            bool(receipt["research_stop_verified"])
            and not self.errors
            and not self.interrupted
        )
        summary = {
            "complete": passed,
            "reason": self.reason,
            "research_seconds": horizon,
            "usage": self.usage,
            "finished": self.returns,
            "structure_reviews": {},
            "pending_provider_errors": self.pending_provider_errors,
            "errors": self.errors,
            "physical_stop_verified": receipt["research_stop_verified"],
        }
        return summary


def seal_evidence(out):
    files = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "evidence-manifest.json":
            with path.open("rb") as stream:
                files[path.relative_to(out).as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    write_json(out / "evidence-manifest.json", files)


def validate_endpoint(url):
    endpoint = urlsplit(url)
    if (
        endpoint.scheme not in ("https", "http")
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError(
            "Use an HTTP(S) API base URL without embedded credentials, query, or fragment"
        )


@contextmanager
def stopping_signals(cohort):
    """Stop participants and finalize the summary before a CLI interrupt returns."""
    loop = asyncio.get_running_loop()
    previous = {}

    def stop():
        cohort.interrupted = True
        cohort.stop("operator_interrupt")

    try:
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                loop.add_signal_handler(signum, stop)
        yield
    finally:
        for signum, handler in previous.items():
            loop.remove_signal_handler(signum)
            signal.signal(signum, handler)


async def collect(args):
    import httpx
    from swarmform.workstation import IMAGE

    if IMAGE is None:
        raise ValueError(
            "Set SWARMHARM_DOCKER_IMAGE to the built image ID before collection"
        )
    if (
        getattr(args, "harness", "chat-completions") == "chat-completions"
        and getattr(args, "api_protocol", "chat-completions") != "chat-completions"
    ):
        raise ValueError(
            "The lightweight runner requires --api-protocol chat-completions"
        )

    sys.path.insert(0, str(ROOT.parent / "shared"))
    from guardrails import resolve_api_base, resolve_api_key, resolve_axonhub_fallback
    if getattr(args, "api_protocol", "chat-completions") != "subscription":
        args.base_url = resolve_api_base(getattr(args, "base_url", None), allow_axonhub_default=True)
    elif not getattr(args, "base_url", None):
        args.base_url = "https://api.openai.com/v1"
    validate_endpoint(args.base_url)
    _ensure_open_file_headroom()
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=max(64, args.population * 2 + 16))
    )
    key = None
    if getattr(args, "api_protocol", "chat-completions") == "subscription":
        from codex_agent import harness_registration
        args._native_runtime = harness_registration("off", args.model.removeprefix("openai/"))
    else:
        key_file = getattr(args, "key_file", None)
        key = resolve_api_key(key_file, api_base=args.base_url)
        if getattr(args, "harness", "chat-completions") != "chat-completions":
            if not key:
                raise ValueError("Native API harnesses require the configured API key")
            import model_session
            args._native_runtime = model_session.registration(args.harness, args.model, args.base_url)
    args._api_key = key
    axon_fallback = (None if getattr(args, "api_protocol", "chat-completions") == "subscription"
                     else resolve_axonhub_fallback(args.base_url, key))
    if getattr(args, "stream_responses", False):
        try:
            import openai
        except ImportError as error:
            raise ValueError("Install the optional openai package to stream responses") from error
        args._stream_sdk = openai.__version__
    headers = {"Authorization": "Bearer " + key} if key else {}
    out = args.out.resolve()
    if out.is_relative_to(ROOT.parent):
        raise ValueError("Choose an output directory outside the repository")
    out.mkdir(parents=True, exist_ok=False)
    async with httpx.AsyncClient(
        headers=headers,
        timeout=args.seconds,
        follow_redirects=False,
        limits=httpx.Limits(
            max_connections=max(32, args.population * 2),
            max_keepalive_connections=max(32, args.population * 2),
            keepalive_expiry=60.0,
        ),
    ) as client:
        cohort = Cohort(args, client, out)
        cohort._axonhub_fallback = axon_fallback
        if getattr(args, "stream_responses", False):
            cohort.stream_client = openai.AsyncOpenAI(base_url=args.base_url, api_key=key or "unused",
                                               http_client=client, max_retries=0, timeout=args.seconds)
        with stopping_signals(cohort):
            try:
                summary = await cohort.run()
            except Exception as error:
                stop = out / "physical-stop.json"
                summary = {
                    "complete": False,
                    "reason": "collection_error",
                    "errors": {"collector": "\n".join(
                        [f"{type(error).__name__}: {error}", *getattr(error, "__notes__", ())]
                    )},
                    "physical_stop_verified": bool(
                        stop.exists()
                        and json.loads(stop.read_text()).get("research_stop_verified")
                    ),
                }
    summary["schema"] = "swarmform-completion-v1"
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["complete"] else 1


def main():
    args = arguments()
    return asyncio.run(collect(args))


if __name__ == "__main__":
    sys.exit(main())
