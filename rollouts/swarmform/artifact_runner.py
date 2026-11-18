"""Validate submitted artifacts away from the author workstation."""

import base64
from hashlib import sha256
import json

from swarmform.workstation import DockerWorkstation

RUNNER = '''import importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location("candidate", "/workspace/tree_cli.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows=[]
for case in json.loads(Path("/workspace/cases.json").read_text()):
    try:
        rows.append({"output": module.run(case["argv"], case["stdin"])})
    except Exception as error:
        rows.append({"error": type(error).__name__})
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
    try:
        command, snapshot = station.execute("python -I /workspace/runner.py", {})
        try:
            raw = base64.b64decode(
                snapshot["/workspace"]["/workspace/outputs.json"], validate=True
            )
            rows = json.loads(raw)
        except (KeyError, ValueError, TypeError):
            rows = []
        correct = 0
        observed = {}
        deterministic = True
        if isinstance(rows, list) and len(rows) == len(probes):
            for result, case, probe in zip(rows, cases, probes):
                value = result.get("output") if isinstance(result, dict) else None
                identity = json.dumps(case, sort_keys=True)
                if identity in observed and observed[identity] != value:
                    deterministic = False
                observed[identity] = value
                correct += value == probe["expected"]
        total = len(probes)
        return {
            "complete": command["exit_code"] == 0
            and correct == total
            and deterministic,
            "deterministic_on_repeated_cases": deterministic,
            "correct_cases": correct,
            "total_cases": total,
            "score": correct / total if total else 0.0,
            "source_sha256": sha256(source.encode()).hexdigest(),
            "command": command,
        }
    finally:
        station.close()
