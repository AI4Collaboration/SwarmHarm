"""Run one cohort with an OpenAI-compatible Chat Completions endpoint."""

import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import threading
import time
from urllib.parse import urlsplit

from . import formation_inputs as inputs
from .formation_common import CommonWorkspace
from .formation_deployment import deployment
from .participant_stop import ParticipantStop
from .program_reference import asset
from .strace_timing import command_binding

CHANNELS = ("direct", *inputs.CHANNELS)
ROOT = Path(__file__).resolve().parent.parent
MAX_RESPONSES, MAX_TOOLS, MAX_TOKENS = 32, 96, 500_000


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="mode", required=True)
    run = subs.add_parser("run", help="Collect one cohort")
    run.add_argument("--harness", choices=['auto','codex','claude-code','pi-sdk','chat-completions'], default='auto')
    run.add_argument("--api-protocol", choices=['chat-completions','native'], default='chat-completions')
    run.add_argument("--served-model", help='Provider ID when different from the native model identity')
    run.add_argument("--population", "-n", type=int, required=True)
    run.add_argument("--names", choices=("numbered", "physicists"), default="numbered")
    run.add_argument(
        "--model", required=True, help="Exact model ID served by your endpoint"
    )
    run.add_argument(
        "--seconds", type=int, choices=range(1, 601), metavar="1..600", default=600
    )
    run.add_argument("--task", choices=inputs.TASK_MODULES, required=True)
    run.add_argument("--channel", choices=CHANNELS, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--key-file", type=Path, default=os.environ.get("OPENAI_API_KEY_FILE"))
    run.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    run.add_argument(
        "--revision", help="Operator-reported deployment or checkpoint revision"
    )
    run.add_argument("--reference", type=Path, default=ROOT / "assets/jq-linux-arm64")
    args = parser.parse_args()
    if args.population < 2 or (args.names == "physicists" and args.population != 3):
        parser.error("Use N >= 2; the surname treatment requires N=3.")
    if args.harness == 'auto':
        sys.path.insert(0, str(ROOT.parent / 'shared'))
        from guardrails import native_harness
        args.harness = native_harness({'model': args.model})
    return args


def source_files():
    return sorted(
        [
            *ROOT.glob("*.py"),
            *ROOT.glob("swarmform/*.py"),
            *ROOT.glob("swarmform/fixtures/*"),
            *sorted((ROOT.parent / 'shared').glob('*.py')),
            *[p for d in ('codex','claude','pi') for p in (ROOT.parent/'shared'/d).iterdir()
              if p.is_file() and p.suffix in ('.json','.mjs')],
            ROOT / "requirements.txt",
            ROOT / "build-jq",
            ROOT.parent / "shared/workstation_patch.py",
            ROOT.parent / "shared/workstation-patch.LICENSE",
            ROOT.parent / "shared/Dockerfile.workstation",
        ]
    )


def source_digest(base=None):
    digest = hashlib.sha256()
    for path in source_files():
        relative = path.relative_to(ROOT.parent)
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256((Path(base)/relative if base else path).read_bytes()).digest())
    return digest.hexdigest()


def runtime_info(image):
    details = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", image], text=True, timeout=30
        )
    )[0]
    host = json.loads(
        subprocess.check_output(
            [
                "docker",
                "info",
                "--format",
                '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"server_version":"{{.ServerVersion}}"}',
            ],
            text=True,
            timeout=30,
        )
    )
    packages = subprocess.check_output(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            image,
            "dpkg-query",
            "-W",
            "curl",
            "procps",
            "ripgrep",
            "strace",
        ],
        text=True,
        timeout=30,
    )
    return {
        "image_id": details["Id"],
        "architecture": details["Architecture"],
        "host": host,
        "packages": dict(line.split("\t", 1) for line in packages.splitlines()),
    }


def write_json(path, value):
    from atomic import atomic_json

    atomic_json(path, value)


def emit(path, value):
    with path.open("ab") as raw:
        offset = raw.tell()
        try:
            with gzip.GzipFile(
                fileobj=raw, mode="wb", compresslevel=1, mtime=0
            ) as stream:
                stream.write(
                    (
                        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    ).encode()
                )
            raw.flush()
            os.fsync(raw.fileno())
        except BaseException:
            raw.truncate(offset)
            raise


class Cohort:
    def __init__(self, args, client, out):
        self.args, self.client, self.out = args, client, out
        self.visible, self.truth, self.manifest = (
            inputs.build_intended(args.task, args.population, names=args.names)
            if args.channel == "direct"
            else inputs.build(
                args.task, args.channel, args.population, names=args.names
            )
        )
        self.last = {}
        self.window_open = None
        self.deadline = None
        self.lock = threading.Lock()
        self.usage = {}
        self.returns = {}
        self.stopping = asyncio.Event()
        self.reason = "all_finished"
        self.errors = {}
        self.active_tools = set()
        self.snapshot_count = 0

    def snapshot(self, actor, phase, value):
        with self.lock:
            sequence = self.snapshot_count + 1
            emit(
                self.out / "observations.jsonl.gz",
                {
                    "sequence": sequence,
                    "actor": actor,
                    "phase": phase,
                    "at": time.time(),
                    "snapshot": value,
                },
            )
            self.snapshot_count = sequence
            if (
                self.window_open
                and time.monotonic() <= self.deadline
                and phase != "terminal"
            ):
                self.last[actor] = value
            return {"path": "observations.jsonl.gz", "sequence": sequence}

    def stop(self, reason):
        if not self.stopping.is_set():
            self.window_open = False
            self.reason = reason
            self.stopping.set()

    def trace(self, actor, kind, **fields):
        with self.lock:
            emit(
                self.out / (actor + ".jsonl.gz"),
                {"kind": kind, "s": time.monotonic() - self.start, **fields},
            )

    def tool(self, actor, cmd, call_id):
        with command_binding(actor=actor, call_id=call_id):
            try:
                result, snapshot = self.station.execute(actor, cmd)
                self.trace(
                    actor,
                    "tool_result",
                    call_id=call_id,
                    result=result,
                    observation=snapshot.get("observation_reference"),
                    command_observation=snapshot.get("command_observation"),
                    timing=snapshot.get("workstation_service_timing"),
                )
                return result, snapshot
            except Exception as error:
                self.trace(actor, "tool_error", call_id=call_id, error=str(error))
                raise

    def tool_completed(self, task, actor, call_id):
        self.active_tools.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self.errors[f"tool_{actor}_{call_id}"] = repr(error)
            self.stop("tool_error")

    async def participant(self, actor):
        if getattr(self.args, 'harness', 'chat-completions') != 'chat-completions':
            from .native_participant import participate
            return await participate(self, actor, {'tokens': MAX_TOKENS, 'responses': MAX_RESPONSES, 'tools': MAX_TOOLS})
        fn = self.visible["tools"][0]
        tools = [
            {
                "type": "function",
                "function": {k: fn[k] for k in ("name", "description", "parameters")},
            }
        ]
        messages = [
            {"role": "user", "content": text} for text in self.visible["prompts"][actor]
        ]
        usage = self.usage[actor] = {"responses": 0, "tools": 0, "tokens": 0}
        try:
            while not self.stopping.is_set():
                request = {
                    "model": self.args.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                }
                self.trace(actor, "request", body=request)
                reply = await self.client.post(
                    self.args.base_url.rstrip("/") + "/chat/completions", json=request
                )
                if reply.is_error:
                    self.trace(
                        actor,
                        "http_error",
                        status=reply.status_code,
                        request_id=reply.headers.get("x-request-id"),
                    )
                    raise RuntimeError(
                        f"Chat Completions returned HTTP {reply.status_code}"
                    )
                data = reply.json()
                self.trace(actor, "response", body=data)
                choice = data["choices"][0]
                msg = choice["message"]
                counter = (data.get("usage") or {}).get("total_tokens")
                if type(counter) != int or counter < 1:
                    raise ValueError(
                        "Server must return usage.total_tokens for matched budgets"
                    )
                usage["responses"] += 1
                usage["tokens"] += counter
                if usage["tokens"] >= MAX_TOKENS:
                    self.stop("observed_token_budget")
                    return
                calls = msg.get("tool_calls") or []
                if not calls:
                    if choice.get("finish_reason") != "stop":
                        raise ValueError(
                            "Incomplete model response: "
                            + str(choice.get("finish_reason"))
                        )
                    self.returns[actor] = "model_finished"
                    return
                # Preserve model reasoning fields required on follow-up calls by some serving stacks.
                messages.append({k: v for k, v in msg.items() if v is not None})
                for call in calls:
                    if self.stopping.is_set():
                        return
                    if usage["tools"] >= MAX_TOOLS:
                        self.stop("tool_budget")
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
                            actor, "tool_start", call_id=call["id"], command=command
                        )
                        task = asyncio.create_task(
                            asyncio.to_thread(self.tool, actor, command, call["id"])
                        )
                        self.active_tools.add(task)
                        task.add_done_callback(
                            lambda completed, actor=actor, call_id=call["id"]: (
                                self.tool_completed(completed, actor, call_id)
                            )
                        )
                        result, snapshot = await asyncio.shield(task)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result),
                        }
                    )
                if usage["responses"] >= MAX_RESPONSES or usage["tools"] >= MAX_TOOLS:
                    self.stop("response_or_tool_budget")
                    return
        except asyncio.CancelledError:
            self.trace(actor, "cancelled", reason=self.reason)
            raise
        except Exception as error:
            self.errors[actor] = f"{type(error).__name__}: {error}"
            self.stop("participant_error")

    async def run(self):
        args = self.args
        reg = {
            "population": args.population,
            "deployment": {"shared": True},
            "channel_family": self.manifest["channel_family"],
        }
        if args.task == "jq-reconstruction":
            reg["reference_program"] = asset(
                args.reference, expected_sha256=self.truth["reference_binary_sha256"]
            )
        from workstation import IMAGE
        import platform
        import httpx
        from .inputs import digest

        write_json(
            self.out / "runtime.json", await asyncio.to_thread(runtime_info, IMAGE)
        )
        write_json(
            self.out / "registration.json",
            {
                "task": args.task,
                "condition": self.manifest["condition"],
                "channel": args.channel,
                "population": args.population,
                "names": args.names,
                "model": args.model,
                "revision": args.revision,
                "base_url": args.base_url,
                "study_version": "native-session-v1" if getattr(args, 'harness', 'chat-completions') != 'chat-completions' else "chat-completions-v1",
                "harness": getattr(args, 'harness', 'chat-completions'),
                "api_protocol": getattr(args, 'api_protocol', 'chat-completions'),
                "served_model": getattr(args, 'served_model', None) or args.model,
                "native_runtime": getattr(args, '_native_runtime', None),
                "observation_policy": "post_tool_and_terminal_v1",
                "source_sha256": source_digest(),
                "python": platform.python_version(),
                "httpx": httpx.__version__,
                "image": IMAGE,
                "input_sha256": digest(self.visible),
                "manifest": self.manifest,
                "per_actor_limits": {
                    "seconds": args.seconds,
                    "responses": MAX_RESPONSES,
                    "tools": MAX_TOOLS,
                    "observed_tokens": MAX_TOKENS,
                },
            },
        )
        write_json(self.out / "inputs.json", self.visible)
        write_json(self.out / "truth.json", self.truth)
        for path in source_files():
            target = self.out/'code'/path.relative_to(ROOT.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        if args.task == 'jq-reconstruction':
            target = self.out/'code/rollouts/assets/jq-linux-arm64'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.reference, target)
        registered = json.loads((self.out/'registration.json').read_text())
        if source_digest(self.out/'code') != registered['source_sha256']:
            raise RuntimeError('Source changed during preparation; no participants started')
        constructor = CommonWorkspace if args.channel == "direct" else deployment
        self.station = await asyncio.to_thread(
            constructor,
            self.visible["startup"],
            reg,
            observation_archive=self.out / "reads",
            observation_sink=self.snapshot,
        )
        stopper = ParticipantStop(self.station)
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
            self.start = time.monotonic()
            self.deadline = self.start + args.seconds
            self.window_open = True
            write_json(
                self.out / "activation.json",
                {"unix": time.time(), "monotonic": self.start},
            )
            workers = [
                asyncio.create_task(self.participant(a))
                for a in self.visible["startup"]
            ]
            group = asyncio.gather(*workers, return_exceptions=True)
            watch = asyncio.create_task(self.stopping.wait())
            done, _ = await asyncio.wait(
                [group, watch],
                timeout=args.seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                self.stop("time_budget")
            horizon = min(time.monotonic() - self.start, args.seconds)
        finally:
            self.window_open = False
            self.stopping.set()
            if watch:
                watch.cancel()
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            try:
                receipt = await asyncio.to_thread(stopper.stop, reason=self.reason)
                write_json(self.out / "physical-stop.json", receipt)
            except Exception as error:
                self.errors["shutdown"] = repr(error)
            await asyncio.gather(*workers, return_exceptions=True)
            results = await asyncio.gather(
                *tuple(self.active_tools), return_exceptions=True
            )
            for index, result in enumerate(results):
                if isinstance(result, BaseException):
                    self.errors[f"tool_{index}"] = str(result)
            try:
                if receipt["research_stop_verified"]:
                    await asyncio.to_thread(self.station.close)
                else:
                    self.errors["shutdown"] = (
                        "Participant stop unverified; original resources retained"
                    )
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
        outputs = {actor: {} for actor in self.visible["startup"]}
        for actor, snap in self.last.items():
            if actor not in outputs:
                continue
            outputs[actor] = {}
            for key, data in snap.get("/workspace", {}).items():
                if key.startswith("/workspace/output/"):
                    raw = base64.b64decode(data)
                    if key.endswith(".zip") and args.task == "jq-reconstruction":
                        folder = self.out / "candidates"
                        folder.mkdir(exist_ok=True)
                        (
                            folder / (hashlib.sha256(raw).hexdigest() + ".zip")
                        ).write_bytes(raw)
                    outputs[actor][key] = (
                        raw if key.endswith(".zip") else raw.decode(errors="replace")
                    )
        write_json(
            self.out / "outcomes.json",
            inputs.module(args.task).outcome(args.task, outputs, self.truth),
        )
        passed = bool(receipt["research_stop_verified"]) and not self.errors
        summary = {
            "complete": passed,
            "reason": self.reason,
            "research_seconds": horizon,
            "usage": self.usage,
            "finished": self.returns,
            "errors": self.errors,
            "physical_stop_verified": receipt["research_stop_verified"],
        }
        write_json(self.out / "summary.json", summary)
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


async def collect(args):
    import httpx

    validate_endpoint(args.base_url)
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=max(32, args.population + 4))
    )
    key_file = getattr(args, 'key_file', None)
    key = (Path(key_file).expanduser().read_text().strip() if key_file
           else os.environ.get("OPENAI_API_KEY"))
    args._api_key = key
    if getattr(args, 'harness', 'chat-completions') != 'chat-completions':
        if not key: raise ValueError('Native harnesses require the configured API key')
        sys.path.insert(0, str(ROOT.parent / 'shared'))
        import model_session
        args._native_runtime = model_session.registration(args.harness, args.model, args.base_url)
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
            max_connections=args.population, max_keepalive_connections=args.population
        ),
    ) as client:
        try:
            summary = await Cohort(args, client, out).run()
        except Exception as error:
            stop = out / "physical-stop.json"
            summary = {
                "complete": False,
                "reason": "collection_error",
                "errors": {"collector": f"{type(error).__name__}: {error}"},
                "physical_stop_verified": bool(
                    stop.exists()
                    and json.loads(stop.read_text()).get("research_stop_verified")
                ),
            }
            write_json(out / "summary.json", summary)
        seal_evidence(out)
    print(json.dumps(summary, indent=2))
    return 0 if summary["complete"] else 1


def main():
    args = arguments()
    return asyncio.run(collect(args))


if __name__ == "__main__":
    sys.exit(main())
