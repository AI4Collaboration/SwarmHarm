"""Single-model SwarmForm component. Use scripts/run-evals for the full default lineup."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import eval_defaults as defaults

from swarmform.__main__ import CHANNELS, ROOT, source_digest, write_json
from swarmform.formation_inputs import TASK_MODULES


def completed_evidence(directory):
    try:
        status = json.loads((directory / "summary.json").read_bytes())
        files = json.loads((directory / "evidence-manifest.json").read_bytes())
        if not status.get("complete") or not status.get("physical_stop_verified"):
            return False
        if "summary.json" not in files or not any(
            name.endswith(".jsonl.gz") for name in files
        ):
            return False
        for name, expected in files.items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()):
                return False
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def cases(args):
    for population in args.populations:
        for rep in range(1, args.repeats + 1):
            for task in args.tasks:
                # Cycle the first condition across replicates.
                offset = (rep - 1) % len(CHANNELS)
                for channel in CHANNELS[offset:] + CHANNELS[:offset]:
                    yield dict(
                        task=task,
                        channel=channel,
                        population=population,
                        names=args.names,
                        seconds=args.seconds,
                        replicate=rep,
                        model=args.model,
                        revision=args.revision,
                        base_url=args.base_url,
                        harness=getattr(args, 'harness', 'chat-completions'),
                        api_protocol=getattr(args, 'api_protocol', 'chat-completions'),
                        served_model=getattr(args, 'served_model', None) or args.model,
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness', choices=['auto','codex','claude-code','pi-sdk','chat-completions'], default='auto')
    parser.add_argument('--api-protocol', choices=['chat-completions','native'], default='chat-completions')
    parser.add_argument('--served-model')
    parser.add_argument("--model", required=True, help="Exact served model ID")
    parser.add_argument(
        "--revision", help="Immutable checkpoint or deployment revision"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument("--populations", nargs="+", type=int, default=list(defaults.POPULATIONS))
    parser.add_argument("--key-file", type=Path, default=os.environ.get("OPENAI_API_KEY_FILE"))
    parser.add_argument(
        "--tasks", nargs="+", choices=TASK_MODULES, default=list(defaults.TASKS)
    )
    parser.add_argument(
        "--names", choices=["numbered", "physicists"], default="numbered"
    )
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--repeats", type=int, default=defaults.REPEATS)
    parser.add_argument(
        "--execute", action="store_true", help="Run planned rows sequentially"
    )
    parser.add_argument(
        "--out", type=Path, help="Parent directory outside the repository"
    )
    args = parser.parse_args()
    if args.harness == 'auto':
        sys.path.insert(0, str(ROOT.parent / 'shared'))
        from guardrails import native_harness
        args.harness = native_harness({'model': args.model})
    if not (
        1 <= args.seconds <= 600 and args.repeats >= 1 and min(args.populations) >= 2
    ):
        parser.error(
            "Use N >= 2, repeats >= 1 and a participant limit of 1 to 600 seconds"
        )
    if len(set(args.tasks)) != len(args.tasks) or len(set(args.populations)) != len(
        args.populations
    ):
        parser.error("Task names and populations must be unique")
    if args.names == "physicists" and args.populations != [3]:
        parser.error("The counterbalanced surname treatment requires N=3")
    if args.execute and (
        args.out is None or args.out.resolve().is_relative_to(ROOT.parent)
    ):
        parser.error("--execute requires --out outside the repository")
    from swarmform.__main__ import validate_endpoint

    validate_endpoint(args.base_url)
    failures = 0
    source = source_digest()
    from workstation import IMAGE

    if args.execute and "jq-reconstruction" in args.tasks:
        from swarmform.program_reference import asset
        from swarmform.programbench_pilot import specification

        reference = ROOT / "assets/jq-linux-arm64"
        if not reference.is_file():
            parser.error(
                "Run bash rollouts/build-jq once before collecting jq-reconstruction"
            )
        asset(reference, expected_sha256=specification()["reference_binary_sha256"])
        architecture = subprocess.check_output(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Architecture}}"],
            text=True,
        ).strip()
        if architecture != "arm64":
            parser.error(
                "Use the ARM64 workstation image from the README for jq-reconstruction"
            )

    rows = [{**row, 'source_sha256': source, 'image': IMAGE} for row in cases(args)]
    if args.execute:
        root = args.out.resolve()
        root.mkdir(parents=True, exist_ok=True)
        if (root/'plan.json').exists() and json.loads((root/'plan.json').read_text()) != rows:
            parser.error('This output root contains a different plan; choose a fresh --out')
        write_json(root/'plan.json', rows)
    records = []
    for row in rows:
        encoded = json.dumps(row, sort_keys=True)
        if not args.execute:
            print(encoded)
            continue
        cohort_id = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        slug = re.sub(r"[^\w.-]+", "-", args.model).strip(".-") or "model"
        directory = (
            args.out.resolve()
            / slug
            / f"n{row['population']}"
            / (f"{row['task']}-{row['channel']}-r{row['replicate']}-{cohort_id}")
        )
        summary = directory / "summary.json"
        record = {**row, 'output': str(directory)}
        archive_index = directory.with_name(directory.name+'.archive.json')
        if not directory.exists() and archive_index.exists():
            archive = json.loads(archive_index.read_text())
            exists = Path(archive['archive']).is_file()
            record.update(status='archived' if exists else 'archive_missing',
                          archive=archive['archive'], sha256=archive['sha256'])
            failures += int(not exists)
            records.append(record)
            write_json(root/'index.json', {'study': 'swarmform', 'runs': records})
            continue
        if directory.exists():
            if completed_evidence(directory):
                print("Already completed", directory, flush=True)
                record['status'] = 'complete'
            else:
                print(
                    "Preserved incomplete or damaged attempt",
                    directory,
                    file=sys.stderr,
                )
                failures += 1
                record['status'] = 'incomplete'
            records.append(record)
            write_json(root/'index.json', {'study': 'swarmform', 'runs': records})
            continue
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
            "--names",
            args.names,
            "--seconds",
            str(args.seconds),
            "--model",
            args.model,
            '--harness', args.harness, '--api-protocol', args.api_protocol,
            '--served-model', args.served_model or args.model,
            "--base-url",
            args.base_url,
            "--out",
            str(directory),
        ]
        if args.revision:
            command.extend(["--revision", args.revision])
        if args.key_file:
            command.extend(["--key-file", str(args.key_file.expanduser().resolve())])
        print("Starting", directory, flush=True)
        directory.parent.mkdir(parents=True, exist_ok=True)
        log = directory.with_name(directory.name+'.log')
        write_json(root/'index.json', {'study': 'swarmform', 'runs': [*records, {**record, 'status': 'running'}]})
        with log.open('a') as stream:
            code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
        failures += int(code != 0)
        record.update(status='complete' if code == 0 else 'incomplete', returncode=code, log=str(log))
        if directory.exists():
            record['raw_bytes'] = sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
        records.append(record)
        write_json(root/'index.json', {'study': 'swarmform', 'runs': records})
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())
