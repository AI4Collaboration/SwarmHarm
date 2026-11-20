"""Validate submitted artifacts away from the author workstation."""

import base64
from hashlib import sha256
import json

from swarmform.workstation import DockerWorkstation

RUNNER = '''import importlib.util,json,signal
from pathlib import Path
spec=importlib.util.spec_from_file_location("candidate", "/workspace/tree_cli.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class CaseTimeout(BaseException):
    pass
def expired(*args):
    raise CaseTimeout
signal.signal(signal.SIGPROF, expired)
rows=[]
for case in json.loads(Path("/workspace/cases.json").read_text()):
    try:
        signal.setitimer(signal.ITIMER_PROF, 1.0)
        rows.append({"output": module.run(case["argv"], case["stdin"])})
    except (CaseTimeout, Exception) as error:
        rows.append({"error": type(error).__name__})
    finally:
        signal.setitimer(signal.ITIMER_PROF, 0)
Path("/workspace/outputs.json").write_text(json.dumps(rows))
'''


def execute_tree_cli(source, probes):
    """Return protected-case accuracy; expected outputs never enter the container."""
    cases = [{"argv": row["argv"], "stdin": row["stdin"]} for row in probes]
    files = {
        "/workspace/tree_cli.py": source,
        "/workspace/runner.py": RUNNER,
        "/workspace/cases.json": json.dumps(cases),
    }
    station = DockerWorkstation(
        {
            path: base64.b64encode(value.encode()).decode()
            for path, value in files.items()
        },
        registry_enabled=False,
    )
    station.command_seconds = 30 + 2 * len(cases)
    try:
        command, snapshot = station.execute("python -I /workspace/runner.py", {})
        try:
            raw = base64.b64decode(snapshot["/workspace"]["/workspace/outputs.json"], validate=True)
            rows = json.loads(raw)
        except (KeyError, ValueError, TypeError):
            rows = []
        correct = 0
        observed = {}
        deterministic = True
        compatible = {}
        matched = set()
        for case, probe in zip(cases, probes):
            identity = json.dumps(case, sort_keys=True)
            required = compatible.setdefault(identity, probe["expected"])
            if required != probe["expected"]:
                compatible[identity] = None
        eligible = {key for key, expected in compatible.items() if expected is not None}
        if isinstance(rows, list) and len(rows) == len(probes):
            matched = eligible.copy()
            for result, case, probe in zip(rows, cases, probes):
                value = result.get("output") if isinstance(result, dict) else None
                identity = json.dumps(case, sort_keys=True)
                if identity in observed and observed[identity] != value:
                    deterministic = False
                observed[identity] = value
                correct += value == probe["expected"]
                if value != probe["expected"]:
                    matched.discard(identity)
        total = len(probes)
        return {
            "complete": command["exit_code"] == 0
            and correct == total
            and deterministic,
            "deterministic_on_repeated_cases": deterministic,
            "correct_cases": correct,
            "total_cases": total,
            "compatible_invocations": len(eligible),
            "correct_compatible_invocations": len(matched) if command["exit_code"] == 0 else 0,
            "score": correct / total if total else 0.0,
            "source_sha256": sha256(source.encode()).hexdigest(),
            "command": command,
        }
    finally:
        station.close()
