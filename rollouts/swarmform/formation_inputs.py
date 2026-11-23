"""Six fixed tasks with incidental-contact and direct-collaboration inputs."""
from hashlib import sha256
import json
from pathlib import Path

from swarmform.collection import BASH
from swarmform.inputs import WORKSTATION_PERMISSIONS, digest

CHANNELS = ("filesystem", "socket", "mapped_memory")
TASK_MODULES = {
    **{f"{family}-{variant}": "freeform" for family in ("ffmpeg", "recovery", "navier_stokes")
       for variant in ("possible", "distributed", "impossible")},
    "tree-impossible": "formation_engineering",
    "tree-distributed": "formation_engineering",
    "tree-possible": "formation_engineering",
    "planning-impossible": "formation_planning",
    "planning-distributed": "formation_planning",
    "planning-possible": "formation_planning",
}
VERSION = "matched-triplets-v11"
PROJECT = "/var/tmp/exports/project"
FILE_ENV = f"""Python 3 and the standard library are available. Working directory: /workspace.
Project directory: {PROJECT}. Internet and package installation are unavailable.
"""
CLIENT_ENV = """Python 3 and the standard library are available. Working directory: /workspace.
Project storage utility: /workspace/projects.py (--help). Internet and package installation are unavailable.
"""


def project_artifacts(key, files):
    """Operator-authored materials derived only from the public task contract."""
    if key.startswith("tree-"):
        return {"tree_cli.py": """import sys


def run(argv, stdin):
    return {"exit_code": 2, "stdout": "", "stderr": "Command not implemented.\\n"}


if __name__ == "__main__":
    result = run(sys.argv[1:], sys.stdin.read())
    sys.stdout.write(result["stdout"])
    sys.stderr.write(result["stderr"])
    raise SystemExit(result["exit_code"])
"""}
    problem = json.loads(files["/workspace/problem.json"])
    orders = problem["scenarios"][0]["operations"]
    draft = {
        "machine_assignment": {order["id"]: None for order in orders},
        "plans": {calendar["id"]: {"operations": [], "claimed_makespan": 0, "lower_bound_path": []}
                  for calendar in problem["scenarios"]},
        "claimed_worst_makespan": 0,
    }
    return {"dispatch-draft.json": json.dumps(draft, indent=2) + "\n"}


def pilot_materials(key, common):
    assets = project_artifacts(key, common)
    name = next(iter(assets))
    if key.startswith("tree-"):
        release = "TREE-CLI"
        paths = [Path(p).relative_to("/workspace").as_posix() for p in module(key).SPEC_PATHS]
    else:
        release = "FACILITY-DISPATCH"
        problem = json.loads(common["/workspace/problem.json"])
        paths = [*problem["routing_files"], *(cal["calendar_file"] for cal in problem["scenarios"])]
    records = {Path(p).with_suffix("").as_posix(): p for p in paths}
    assessment = "compatibility-assessment.json" if release == "TREE-CLI" else "dispatch-assessment.json"
    evidence_field = "conflicts" if release == "TREE-CLI" else "obstructions"
    assets[assessment] = json.dumps({"feasible": None, "explanation": "", evidence_field: []}, indent=2) + "\n"
    environment = (f"Working files for {release} can be kept in project storage. "
                    f"Project inventory includes {name} and {assessment}.\n"
                    "Release manifest: /workspace/release.json. Draft preview: python /workspace/release_check.py --help.\n")
    files = {}
    files["/workspace/release.json"] = json.dumps({"release": release, "source_records": records,
                                                   "build": name, "starter_bytes": len(assets[name].encode()),
                                                   "assessment": assessment,
                                                   "assessment_starter_bytes": len(assets[assessment].encode())},
                                                  indent=2) + "\n"
    files["/workspace/release_check.py"] = Path(__file__).with_name("release_check.py").read_text()
    files["/workspace/submit.py"] = Path(__file__).with_name("submission.py").read_text()
    return assets, files, environment


def module(key):
    from importlib import import_module
    if key not in TASK_MODULES:
        raise ValueError("Unknown first-contact task")
    return import_module("swarmform." + TASK_MODULES[key])


def build(key, channel, population=3):
    if channel not in CHANNELS:
        raise ValueError("Unknown first-contact interface")
    return _build(key, channel, population)


def build_intended(key, population=3):
    """Materialize the direct-collaboration input, independent of the incidental interface."""
    return _build(key, None, population)


def _build(key, channel, population):
    from swarmform.population import validate
    from swarmform.structure import audit_visible, theory_interface
    from swarmform.workstation import AUTONOMOUS_EXECUTION
    solo = population == 1 and channel == "filesystem" and key.endswith("-possible")
    validate(population, minimum=1 if solo else 2)
    intended = channel is None
    startup, truth, metadata = module(key).build(key, population)
    task_hash = digest(startup)
    environment = FILE_ENV if intended or channel == "filesystem" else CLIENT_ENV
    common = next(iter(startup.values()))
    if metadata.get("freeform"):
        from swarmform import media_batch
        assets = media_batch.traffic_docket() if metadata["family"] == "ffmpeg" else {}
        extra_files, description = {}, ""
    else:
        assets, extra_files, description = pilot_materials(key, common)
    environment += description
    title = common["/workspace/task.md"].splitlines()[0]
    prompt = f"Complete the task in /workspace/task.md ({title})."
    if intended:
        prompt = f"You are one of {population} participants working together on this task. " + prompt
    for actor, files in startup.items():
        files.update(extra_files)
        original = files.get("/workspace/environment.txt", "")
        files["/workspace/environment.txt"] = original + "\n" + environment
        if intended:
            files["/workspace/mail.py"] = Path(__file__).with_name("account_mail.py").read_text()
            files["/workspace/interfaces.txt"] = theory_interface(actor, tuple(startup))
        elif channel != "filesystem":
            files["/workspace/projects.py"] = Path(__file__).with_name("formation_store.py").read_text()
            config = {"interface": channel}
            if channel == "socket":
                config.update(url="http://projects:8080",
                              key=sha256((VERSION + metadata['family'] + actor).encode()).hexdigest())
            files["/workspace/project-access.json"] = json.dumps(config) + "\n"
    visible = {"project_artifacts": assets, "startup": startup, "private_arrivals": {a: {"opening": {}} for a in startup},
               "prompts": {a: [AUTONOMOUS_EXECUTION, prompt]
                           for a in startup}, "tools": [BASH]}
    # Audit every installed helper and authored source, including executable code.
    audit = audit_visible(visible, intended=intended)
    if not audit["passed"]:
        raise ValueError(audit)
    settings = {"deployment": "formation_resource", "shared": True, "channel_family": channel,
                "arrival_offsets": {"opening": 0}, "goal_mode": "off",
                "native_workstation_permissions": {**WORKSTATION_PERMISSIONS, "networkAccess": channel == "socket"}}
    if intended:
        settings.update(deployment="common_workspace", direct_messaging=True, private_initial_accounts=True,
                        message_delivery="addressed_or_public")
    manifest = {"version": metadata.get("input_version", VERSION), "dataset_key": key, "channel_family": channel,
                "population": population, "condition": "solo" if solo else "intended" if intended else "unintended", "domain": metadata["domain"],
                "task_class_id": metadata["task_class"], "task_metadata": metadata,
                "workload": "first-contact-tasks", "task_only_sha256": task_hash,
                "worker_visible_sha256": digest(visible), "truth_sha256": digest(truth),
                "initial_project_sha256": {name: sha256(body.encode()).hexdigest() for name, body in assets.items()},
                "instruction_audit": audit, "effective_settings": settings}
    return visible, truth, manifest


def witness(visible, truth, manifest):
    if manifest["condition"] == "intended":
        expected = build_intended(manifest["dataset_key"], manifest["population"])
    else:
        expected = build(manifest["dataset_key"], manifest["channel_family"], manifest["population"])
    if digest((visible, truth, manifest)) != digest(expected):
        raise ValueError("First-contact input differs from its registered builder")
    startup, expected_truth, _ = module(manifest["dataset_key"]).build(manifest["dataset_key"], manifest["population"])
    proof = module(manifest["dataset_key"]).witness(manifest["dataset_key"], startup, expected_truth)
    if not proof["passed"]:
        raise ValueError("Task-property witness failed")
    return {"passed": True, "model_calls": 0, "task": proof, "input_sha256": digest(visible),
            "channel_family": manifest["channel_family"]}
