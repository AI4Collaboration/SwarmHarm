"""Single-model SwarmForm component. Use scripts/run-evals for the full default lineup."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
import time
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import model_lineup as defaults
from guardrails import resolve_api_base
from process_control import run_process

from swarmform.__main__ import CHANNELS, ROOT, request_limit, resolve_harness, source_digest, write_json
from swarmform.formation_inputs import add_task_selection
from swarmform import checkpoint


def sealed_summary(directory):
    """Read the authenticated summary and verify the files it was sealed with."""
    try:
        files = json.loads((directory / "evidence-manifest.json").read_bytes())
        if "summary.json" not in files or not any(name.endswith(".jsonl.gz") for name in files):
            return None
        for name, expected in files.items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()):
                return None
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    return None
        summary = json.loads((directory / "summary.json").read_bytes())
        return summary if isinstance(summary, dict) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def finalized_summary(directory):
    try:
        summary = json.loads((directory / "summary.json").read_bytes())
    except (OSError, ValueError):
        return None
    if isinstance(summary, dict) and summary.get("schema") == "swarmform-completion-v1":
        if type(summary.get("complete")) is bool and type(summary.get("physical_stop_verified")) is bool:
            return summary
        return None
    return sealed_summary(directory)


def completed_evidence(directory):
    summary = finalized_summary(directory)
    return bool(summary and summary.get("complete") and summary.get("physical_stop_verified"))


def resume_details(summary):
    if not summary or summary.get("complete") or not summary.get("physical_stop_verified"):
        return {}
    reason = summary.get("reason")
    # Older Codex cohorts recorded the native quota rejection as a participant error.
    if reason == "participant_error" and any(
        "Codex error: usageLimitExceeded (native/" in str(error)
        for error in summary.get("errors", {}).values()
    ):
        reason = "provider_rejected"
    if reason not in ("operator_interrupt", "provider_unavailable", "provider_rejected"):
        return {}
    if set(summary.get("errors", {})) - set(summary.get("usage", {})):
        return {}
    delays = summary.get("pending_provider_errors", {}).values()
    return {"retry_reason": reason,
            "retry_not_before": max((failure["retry_not_before"] for failure in delays), default=0)}


def archived_evidence(index):
    """Verify the bundle before counting a moved or resumed attempt as complete."""
    try:
        row = json.loads(index.read_text())
        sibling = index.with_name(index.name.removesuffix(".archive.json") + ".tar.gz")
        archive = sibling if sibling.is_file() else Path(row["archive"])
        if not archive.is_file():
            return {"status": "archive_missing", "archive": str(archive)}
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                raise ValueError("Archive checksum differs")
        with tarfile.open(archive, "r:gz") as bundle:
            entry = bundle.getmember("summary.json")
            if not entry.isfile():
                raise ValueError("Archive has no regular summary file")
            with bundle.extractfile(entry) as stream:
                status = json.load(stream)
        complete = status.get("complete") and status.get("physical_stop_verified")
        return {
            "status": "archived" if complete else "incomplete",
            **resume_details(status),
            "archive": str(archive),
            "sha256": row["sha256"],
        }
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        tarfile.TarError,
    ) as error:
        return {"status": "archive_damaged", "error": str(error)}


@contextmanager
def batch_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "This output directory already has a running batch"
            ) from None
        yield


def cases(args):
    selected = set(getattr(args, "channels", None) or CHANNELS)
    for population in args.populations:
        for rep in range(1, args.repeats + 1):
            for task in args.tasks:
                # Cycle the first condition across replicates.
                offset = (rep - 1) % len(CHANNELS)
                for channel in CHANNELS[offset:] + CHANNELS[:offset]:
                    if channel not in selected or (population == 1 and channel != "filesystem"):
                        continue
                    yield dict(
                        task=task,
                        channel=channel,
                        population=population,
                        seconds=args.seconds,
                        **({"max_inflight_requests": request_limit(population)}
                           if getattr(args, "harness", "chat-completions") == "chat-completions" else {}),
                        thinking_level=getattr(args, "thinking_level", None),
                        **({"service_tier": args.service_tier} if getattr(args, "service_tier", None) else {}),
                        **checkpoint.cohort_registration(args),
                        entry_window_seconds=getattr(args, "entry_window_seconds", 0),
                        **({"closed_mail_receipts": True} if getattr(args, "closed_mail_receipts", False) and channel == "direct" else {}),
                        **({"enforce_personal_limits": True} if getattr(args, "enforce_personal_limits", False) else {}),
                        **({k: getattr(args, k) for k in ("max_responses", "max_tools", "max_tokens") if getattr(args, k, None) is not None}),
                        **({"stream_responses": True} if getattr(args, "stream_responses", False) else {}),
                        replicate=rep,
                        model=args.model,
                        revision=args.revision,
                        base_url=args.base_url,
                        harness=getattr(args, "harness", "chat-completions"),
                        api_protocol=getattr(args, "api_protocol", "chat-completions"),
                        served_model=getattr(args, "served_model", None) or args.model,
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harness",
        choices=["auto", "codex", "claude-code", "pi-sdk", "chat-completions"],
        default=None,
    )
    parser.add_argument(
        "--api-protocol",
        choices=["chat-completions", "native", "subscription"],
        default="chat-completions",
    )
    parser.add_argument("--served-model")
    parser.add_argument("--model", default=defaults.MODELS[defaults.SWARMFORM_MODEL][0],
                        help="Model identity (default: SwarmForm Terra 6.1)")
    parser.add_argument(
        "--revision", help="Immutable checkpoint or deployment revision"
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API URL (prioritizes --base-url / OPENAI_BASE_URL / OpenRouter, then AxonHub)",
    )
    parser.add_argument(
        "--populations",
        nargs="+",
        type=int,
        default=list(defaults.POPULATIONS),
    )
    parser.add_argument(
        "--key-file", type=Path, default=os.environ.get("OPENAI_API_KEY_FILE")
    )
    add_task_selection(parser, list(defaults.TASKS))
    parser.add_argument("--channels", nargs="+", choices=CHANNELS, default=list(CHANNELS),
                        help="Limit collection to these communication conditions")
    parser.add_argument("--entry-window-seconds", type=int, default=0,
                        help="Spread starts evenly across this window")
    parser.add_argument("--stream-responses", action="store_true", help="Stream Chat Completions and record chunks")
    parser.add_argument("--closed-mail-receipts", action="store_true",
                        help="Mark directed sends to a permanently closed direct-mail session")
    parser.add_argument("--cohort-seconds", type=int, default=None)
    parser.add_argument("--review-interval-seconds", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--enforce-personal-limits", action="store_true")
    parser.add_argument("--max-responses", type=int, default=None)
    parser.add_argument("--max-tools", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--thinking-level", choices=("low", "medium", "high"),
                        help="Native reasoning effort; opt in for compatible Chat Completions endpoints")
    parser.add_argument("--service-tier", choices=("priority", "ultrafast"),
                        help="Request this tier only on an endpoint that supports it")
    parser.add_argument("--review-model", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--seconds", type=int, default=600, help="Per-request transport timeout")
    parser.add_argument("--repeats", type=int, default=defaults.REPEATS)
    parser.add_argument("--max-attempts", type=int, default=2,
                        help="Maximum new attempts per cohort on transient provider failures (default: 2)")
    parser.add_argument("--archive", action="store_true",
                        help="Verify, compress and remove raw directories for completed cohorts automatically")
    parser.add_argument(
        "--execute", action="store_true", help="Run planned rows sequentially"
    )
    parser.add_argument(
        "--out", type=Path, help="Parent directory outside the repository"
    )
    args = parser.parse_args()
    if 1 in args.populations and "filesystem" not in args.channels:
        parser.error("N=1 requires the filesystem condition")
    resolve_harness(args)
    if not (
        1 <= args.seconds <= 600 and args.repeats >= 1 and min(args.populations) >= 1
        and args.max_attempts >= 1
    ):
        parser.error(
            "Use N >= 1, repeats >= 1, max-attempts >= 1 and a request timeout of 1 to 600 seconds"
        )
    horizon_s = args.cohort_seconds or checkpoint.COHORT_SECONDS
    if not 0 <= args.entry_window_seconds < horizon_s:
        parser.error("Entry offsets must precede the common cohort deadline.")
    if args.api_protocol == "subscription" and args.harness != "codex":
        parser.error("Subscription transport requires --harness codex.")
    if args.service_tier and args.api_protocol != "subscription" and args.harness != "chat-completions":
        parser.error("--service-tier requires Codex subscription or direct Chat Completions")
    if args.stream_responses and args.harness != "chat-completions":
        parser.error("--stream-responses requires the Chat Completions harness")
    if 1 in args.populations and any(not key.endswith("-possible") for key in args.tasks):
        parser.error("For N=1 select possible-but-hard tasks.")
    if len(set(args.tasks)) != len(args.tasks) or len(set(args.populations)) != len(
        args.populations
    ):
        parser.error("Task names and populations must be unique")
    if args.execute and (
        args.out is None or args.out.resolve().is_relative_to(ROOT.parent)
    ):
        parser.error("--execute requires --out outside the repository")
    from swarmform.__main__ import validate_endpoint

    args.base_url = resolve_api_base(args.base_url, allow_axonhub_default=True)
    validate_endpoint(args.base_url)
    source = source_digest()
    from swarmform.workstation import IMAGE

    rows = [{**row, "source_sha256": source, "image": IMAGE} for row in cases(args)]
    if not args.execute:
        for row in rows:
            print(json.dumps(row, sort_keys=True))
        return 0
    if IMAGE is None:
        parser.error(
            "Set SWARMHARM_DOCKER_IMAGE to the built image ID before collection"
        )
    with batch_lock(args.out.resolve()):
        return execute_rows(args, rows, parser)


def execute_rows(args, rows, parser):
    root = args.out.resolve()
    if (root / "plan.json").exists() and json.loads(
        (root / "plan.json").read_text()
    ) != rows:
        parser.error("This output root contains a different plan; choose a fresh --out")
    write_json(root / "plan.json", rows)
    failures = 0
    records = []
    for row in rows:
        encoded = json.dumps(row, sort_keys=True)
        cohort_id = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        slug = re.sub(r"[^\w.-]+", "-", args.model).strip(".-") or "model"
        directory = (
            args.out.resolve()
            / slug
            / f"n{row['population']}"
            / (f"{row['task']}-{row['channel']}-r{row['replicate']}-{cohort_id}")
        )
        base = directory
        previous = []
        new_attempts = 0
        interrupted = None
        while True:
            if previous:
                directory = base.with_name(f"{base.name}-attempt-{len(previous) + 1:03d}")
            record = {**row, "output": str(directory)}
            if previous:
                record["prior_attempts"] = list(previous)
            log = directory.with_name(directory.name + ".log")
            archive_index = directory.with_name(directory.name + ".archive.json")
            if directory.exists():
                summary = finalized_summary(directory)
                complete = summary and summary.get("complete") and summary.get("physical_stop_verified")
                record.update(status="complete" if complete else "incomplete", **resume_details(summary))
            elif archive_index.exists():
                record.update(archived_evidence(archive_index))
            elif log.exists():
                record.update(status="incomplete", log=str(log))
            else:
                if previous:
                    delay = previous[-1]["retry_not_before"] - time.time()
                    if delay > 0:
                        time.sleep(delay)
                command = cohort_command(args, row, directory)
                new_attempts += 1
                write_json(root / "index.json",
                           {"study": "swarmform", "runs": [*records, {**record, "status": "running"}]})
                print("Starting", directory, flush=True)
                directory.parent.mkdir(parents=True, exist_ok=True)
                with log.open("x") as stream:
                    code, interrupted = run_process(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                summary = finalized_summary(directory)
                complete = summary and summary["complete"] and summary.get("physical_stop_verified")
                record.update(status="complete" if complete else "incomplete", returncode=code, log=str(log))
                record.update(resume_details(summary))
                if complete and getattr(args, "archive", False):
                    archived = subprocess.run(
                        [sys.executable, str(ROOT.parent / "scripts/archive-trajectories"),
                         str(directory), "--remove-source"],
                        cwd=ROOT.parent, capture_output=True, text=True,
                    )
                    if archived.returncode == 0:
                        record.update(archived_evidence(archive_index))
                    else:
                        record["archive_error"] = (archived.stderr or archived.stdout).strip()[-500:]
                if record.get("retry_reason") in ("operator_interrupt", "provider_rejected"):
                    break
            if interrupted or not record.get("retry_reason") or new_attempts >= getattr(args, "max_attempts", 2):
                break
            previous.append({key: value for key, value in record.items()
                             if key in ("output", "status", "retry_reason", "retry_not_before", "log", "archive")})
        failures += int(record["status"] not in ("complete", "archived"))
        records.append(record)
        write_json(root / "index.json", {"study": "swarmform", "runs": records})
        if interrupted or record.get("retry_reason") in ("operator_interrupt", "provider_rejected", "provider_unavailable"):
            break
    return int(failures != 0)


def cohort_command(args, row, directory):
    command = [
        sys.executable,
        "-m",
        "swarmform",
        "run",
        "--task",
        row["task"],
        "--channel",
        row["channel"],
        "--population",
        str(row["population"]),
        "--seconds",
        str(args.seconds),
        "--entry-window-seconds",
        str(row["entry_window_seconds"]),
        "--model",
        args.model,
        "--harness",
        args.harness,
        "--api-protocol",
        args.api_protocol,
        "--served-model",
        args.served_model or args.model,
        "--base-url",
        args.base_url,
        "--out",
        str(directory),
        "--expected-source-sha256",
        row["source_sha256"],
    ]
    if row.get("stream_responses"):
        command.append("--stream-responses")
    if row.get("closed_mail_receipts"):
        command.append("--closed-mail-receipts")
    if args.cohort_seconds:
        command.extend(["--cohort-seconds", str(args.cohort_seconds)])
    if row.get("enforce_personal_limits"):
        command.append("--enforce-personal-limits")
    for flag, key in (("--max-responses", "max_responses"), ("--max-tools", "max_tools"), ("--max-tokens", "max_tokens")):
        if row.get(key) is not None:
            command.extend([flag, str(row[key])])
    if getattr(args, "thinking_level", None) is not None:
        command.extend(["--thinking-level", args.thinking_level])
    if row.get("service_tier"):
        command.extend(["--service-tier", row["service_tier"]])
    if args.revision:
        command.extend(["--revision", args.revision])
    if args.key_file:
        command.extend(["--key-file", str(args.key_file.expanduser().resolve())])
    return command


if __name__ == "__main__":
    raise SystemExit(main())
