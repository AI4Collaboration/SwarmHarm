"""Export the pinned upstream's initial requests without starting a sandbox."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

from build import REPO, load_module, save


def prepare(root):
    parent = REPO.parent / "eval-readiness/lesswrong-direct-2026-10-19"
    sys.path.insert(0, str(REPO / "experiments/lesswrong-direct-v1"))
    original = load_module(REPO / "experiments/lesswrong-direct-v1/run.py", "upstream_screen_runner")
    original.verify_source(parent)
    packets = []
    previous = None
    for condition, module_name, params in original.CELLS:
        task = original.upstream(parent, module_name, params)
        module = importlib.import_module(f"alignment_auditor.docker_replication.{module_name}.task")
        candidates = list((parent / "requests" / condition).glob("*/epoch-001/*.request.json"))
        prior = {}
        body = None
        for path in sorted(candidates):
            request = json.loads(path.read_text())
            if (not any(t.get("name") == "bash" for t in request.get("tools", []))
                    or len(request.get("input", [])) != 1
                    or request["input"][0].get("content") != [{"type": "input_text", "text": task.dataset[0].input}]):
                continue
            model = request["model"]
            if model in prior:
                continue
            response = path.with_name(path.name.replace(".request.json", ".response.json"))
            error = path.with_name(path.name.replace(".request.json", ".error.json"))
            if not response.exists() and not error.exists():
                continue
            prior[model] = {"request": str(path), "outcome": str(response if response.exists() else error)}
            body = {key: deepcopy(request[key]) for key in ("instructions", "input", "tools")}
        derivation = None
        if body is None:
            # Both tasks use the same pinned react_solver (bash timeout and AgentPrompt).
            # Substitute only the source-selected persona and source assignment.
            assert condition == "step4_chain" and previous is not None
            source_personas = []
            for value in vars(previous["module"]).values():
                source_personas.extend([value] if isinstance(value, str) else
                    [v for v in value.values() if isinstance(v, str)] if isinstance(value, dict) else [])
            persona = max((p for p in source_personas if len(p) > 200 and
                           p in previous["body"]["instructions"]), key=len)
            body = deepcopy(previous["body"])
            assert body["instructions"].count(persona) == 1
            body["instructions"] = body["instructions"].replace(persona, module.REDTEAM_PERSONAS[params["drive"]])
            body["input"][0]["content"] = [{"type": "input_text", "text": task.dataset[0].input}]
            derivation = {"wrapper": "Pinned upstream harness.scaffolds.react_solver, identical bash/submit tools and AgentPrompt",
                          "persona": "step4_hf_cheat_chain.task.REDTEAM_PERSONAS[persist]",
                          "assignment": "Original task.dataset[0].input", "sandbox_started": False}
        packets.append({"family": "lesswrong-direct-v1", "task": condition,
                        "variant": params, "source": str(parent / "source"),
                        "body": body, "prior": prior, "derivation": derivation})
        previous = {"module": module, "body": body}
    save(root / "packets.json", {"family": "lesswrong-direct-v1", "packets": packets,
                                  "notes": [], "offline_only": True})


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
