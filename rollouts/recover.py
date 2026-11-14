"""Export retained Docker evidence after correcting a host storage/capture failure."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from atomic import atomic_json
from swarmform.__main__ import ROOT, seal_evidence
from swarmform.read_observer import ObservedFileStation, trace_blocks
from swarmform.service_workstation import ServiceWorkstation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Original incomplete cohort"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Fresh recovery folder outside Git"
    )
    args = parser.parse_args()
    run, out = args.run.resolve(), args.out.resolve()
    if out.is_relative_to(ROOT.parent) or out.is_relative_to(run):
        parser.error("Recovery output must be outside the repository and original run")
    stop = json.loads((run / "physical-stop.json").read_bytes())
    if not stop.get("research_stop_verified"):
        parser.error(
            "A verified participant stop is required before terminal evidence recovery"
        )
    bindings = json.loads((run / "recovery-bindings.json").read_bytes())
    out.mkdir(parents=True, exist_ok=False)
    failures = {}
    try:
        for actor, binding in bindings["participants"].items():
            try:
                station = ObservedFileStation.__new__(ObservedFileStation)
                station.configure_archive(out / actor / "reads")
                station.name = binding["container"]
                station.account_view = binding["account_view"]
                station.business_uid = binding["business_uid"]
                station.observation_roots = binding["observation_roots"]
                station.observation_settle_seconds = 2
                station.trace_commands = station.initialized = True
                station.closed = False
                station.prune_archived = False
                origins = run / binding["archive"] / "origins.json"
                if origins.exists():
                    station.trace_origins = json.loads(origins.read_bytes())
                    station.command_count = len(station.trace_origins)
                station.observation_sink = lambda phase, value, actor=actor: (
                    atomic_json(out / actor / (phase + ".json"), value)
                )
                # Original committed chunks remain in the original run. This export
                # captures any final logs that could not previously be committed.
                station.capture_terminal()
                for receipt in station.archive.glob("[0-9]*.json"):
                    for record in json.loads(receipt.read_bytes())["files"].values():
                        for _ in trace_blocks(station.archive, record):
                            pass
            except Exception as error:
                failures[actor] = f"{type(error).__name__}: {error}"
        if bindings.get("service"):
            try:
                service = ServiceWorkstation.__new__(ServiceWorkstation)
                service.name = bindings["service"]
                service.service_archive = out / "service"
                service.service_archive.mkdir()
                service.service_capture_count = 0
                service.observation_sink = None
                service.capture_frozen("recovered_terminal")
            except Exception as error:
                failures["service"] = f"{type(error).__name__}: {error}"
        if bindings.get("memory_anchor"):
            try:
                reply = subprocess.run(
                    [
                        "docker",
                        "exec",
                        bindings["memory_anchor"],
                        "cat",
                        "/dev/shm/project-work-cache",
                    ],
                    capture_output=True,
                    check=True,
                )
                (out / "memory-cache.gz").write_bytes(
                    gzip.compress(reply.stdout, mtime=0)
                )
            except subprocess.CalledProcessError as error:
                # An unused cache has no backing file.
                if b"No such file" not in error.stderr:
                    failures["memory"] = str(error)
    finally:
        atomic_json(
            out / "summary.json",
            {
                "original_run": str(run),
                "complete": not failures,
                "errors": failures,
                "scope": "Post-stop evidence recovery. Original scores and cutoff are unchanged.",
                "original_manifest_sha256": (
                    hashlib.sha256(
                        (run / "evidence-manifest.json").read_bytes()
                    ).hexdigest()
                    if (run / "evidence-manifest.json").exists()
                    else None
                ),
                "resources": bindings,
            },
        )
        seal_evidence(out)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
