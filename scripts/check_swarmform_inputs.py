#!/usr/bin/env python3
"""Check the active SwarmForm matrix, registration provenance and offline workload tests."""

import argparse
from hashlib import sha256
from importlib import import_module
from itertools import product
import json
from pathlib import Path
import sys
import unittest
from swarmform_scope import selected_cells


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/live-rollout-status.json"
PACKAGE = ROOT / "experiments/swarmharm-v1"
sys.path.insert(0, str(ROOT / "experiments/runtime"))
from codex_gateway import AXONHUB_BASE, digest as json_digest


EXPECTED_AXES = {
    "deployments": {"shared_files", "shared_ipc", "worker_endpoint", "artifact_namespace", "job_namespace"},
    "encoding_opportunities": {"payload_content", "identifiers_metadata", "operational_state", "event_pattern", "timing"},
    "domains": {"Engineering", "Data Analysis", "Financial Analysis", "Knowledge Work"},
}
KNOWN_MODELS = ("openai/gpt-5.6-sol", "openai/gpt-6.1-sol")


def fail(message):
    raise SystemExit("SwarmForm input check failed: " + message)


def repository_file(relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        fail(f"expected a repository-relative file: {relative}")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        fail(f"missing repository file: {relative}")
    return path


def read_record(path, *, seal=None):
    data = path.read_bytes()
    if seal is not None and sha256(data).hexdigest() != seal.get("sha256"):
        fail(f"digest mismatch for {path.name}")
    try:
        record = json.loads(data)
    except (UnicodeError, ValueError) as error:
        fail(f"invalid JSON in {path.name}: {error}")
    if not isinstance(record, dict):
        fail(f"expected a JSON object in {path.name}")
    return record


def check_dispositions(status, keys):
    cells = status["matrix"]["cells"]
    manifests = {}
    admitted = {}
    for key, entry in cells.items():
        disposition = entry.get("status")
        if key not in keys or disposition not in {"admitted", "equivalent", "unsupported"}:
            fail(f"invalid matrix disposition: {key}")
        report = read_record(repository_file(entry.get("evidence")))
        if (report.get("research_study") != status["research_study"] or report.get("population") != status["population"]
                or report.get("matrix_cell") != key or report.get("status") != disposition):
            fail(f"disposition evidence belongs to a different study, population, cell or status: {key}")
        if disposition == "unsupported":
            if not isinstance(report.get("reason"), str) or not report["reason"].strip():
                fail(f"unsupported cell lacks a stated scope or observation limit: {key}")
            continue
        # Hash the effective input itself; two equal labels are not an equivalence witness.
        manifest = read_record(repository_file(report.get("input_manifest")))
        digest = json_digest(manifest)
        if digest != report.get("input_sha256"):
            fail(f"effective input digest mismatch: {key}")
        if (manifest.get("research_study") != status["research_study"] or manifest.get("population") != status["population"]
                or manifest.get("domain") != key.rsplit("/", 1)[-1]):
            fail(f"effective input belongs to a different study, population or domain: {key}")
        if disposition == "admitted":
            if digest in admitted:
                fail(f"same effective input admitted twice: {admitted[digest]} and {key}")
            admitted[digest] = key
        manifests[key] = digest

    for key, entry in cells.items():
        if entry["status"] == "equivalent":
            canonical = entry.get("canonical", "")
            if (cells.get(canonical, {}).get("status") != "admitted"
                    or key.rsplit("/", 1)[-1] != canonical.rsplit("/", 1)[-1]
                    or manifests[key] != manifests[canonical]):
                fail(f"equivalence requires an admitted cell with identical effective input in the same domain: {key}")
    return manifests


def validate_active_matrix(status):
    matrix = status["matrix"]
    for axis, expected in EXPECTED_AXES.items():
        values = matrix[axis]
        if len(values) != len(expected) or set(values) != expected:
            fail(f"SwarmForm {axis} differ from the approved matrix")
    if status["research_study"] != "SwarmForm":
        fail("active study must be SwarmForm")
    repository_file(status["decision_record"])
    models = status["current_models"]
    if (status["population"] != 3 or status["current_harness"] != "codex"
            or not isinstance(models, list) or not models
            or any(model not in KNOWN_MODELS for model in models) or len(models) != len(set(models))):
        fail("SwarmForm needs three agents per rollout and a nonempty selection of known Sol models")
    if matrix["unlisted_cell_status"] != "open":
        fail("unreviewed matrix cells must remain open")
    keys = {"/".join(cell) for cell in product(matrix["deployments"], matrix["encoding_opportunities"], matrix["domains"])}
    try:
        selected = {'/'.join(cell) for cell in selected_cells(status)}
    except (KeyError, ValueError) as error:
        fail(str(error))
    if status["next_checkpoint"] is not None and status["next_checkpoint"] not in selected:
        fail("next checkpoint is outside the delivery scope")
    manifests = check_dispositions(status, keys)
    print(f"SwarmForm delivery: {len(selected)} inputs; {len(selected - matrix['cells'].keys())} awaiting admission. Retained catalog: {len(keys)}.")
    return manifests


def check_registrations(status, manifests):
    registrations = status["maintained_registrations"]
    if len(registrations) != len(set(registrations)):
        fail("duplicate registration in active ledger")
    for name in registrations:
        folder = (ROOT / name).resolve()
        if folder.parent != PACKAGE / "registrations" or name != str(folder.relative_to(ROOT)):
            fail(f"registration is outside the retained input directory: {name}")
        path = repository_file(name + "/registration.json")
        seal = read_record(repository_file(name + "/registration-seal.json"))
        reg = read_record(path, seal=seal)
        actors = reg.get("plan", {}).get("natural", {})
        harness = reg.get("harness", {})
        models = reg.get("models", {})
        key = reg.get("matrix_cell")
        if (reg.get("research_study") != status["research_study"] or not isinstance(actors, dict)
                or len(actors) != status["population"]
                or reg.get("budget", {}).get("active_contexts_natural") != status["population"]):
            fail(f"registration does not match the three-agent SwarmForm study: {name}")
        if (status["matrix"]["cells"].get(key, {}).get("status") != "admitted"
                or reg.get("input_sha256") != manifests[key]):
            fail(f"registration is not bound to an admitted input: {name}")
        if (harness.get("kind") != status["current_harness"] or harness.get("authentication") != "axonhub"
                or reg.get("inference_gateway") != "axonhub" or harness.get("goal_mode") != "off"
                or reg.get("api_base") != AXONHUB_BASE or harness.get("gateway") != AXONHUB_BASE
                or reg.get("reasoning") != "high" or len(set(models.values())) != 1
                or not set(models.values()).issubset(KNOWN_MODELS)
                or any(actor.get("provider") not in models for actor in actors.values())):
            fail(f"model route or runtime settings differ from the active plan: {name}")
    for rollout in status["active_rollouts"]:
        if rollout.get("registration") not in registrations:
            fail("active rollout has no matching SwarmForm registration")


def check_workloads(matrix, *, run_tests=True):
    checks = matrix["offline_workload_checks"]
    if str(PACKAGE) not in sys.path:
        sys.path.insert(0, str(PACKAGE))
    for domain, relative in checks.items():
        path = repository_file(relative)
        if domain not in matrix["domains"] or path.parent != PACKAGE / "tests" or not path.name.endswith("_checks.py"):
            fail(f"invalid workload check for {domain}: {relative}")
        module = import_module("tests." + path.stem)
        if Path(module.__file__).resolve() != path or getattr(module, "SWARMFORM_DOMAIN", None) != domain:
            fail(f"workload checks do not identify the SwarmForm domain {domain}: {relative}")
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        if not suite.countTestCases() or (run_tests and not unittest.TextTestRunner().run(suite).wasSuccessful()):
            fail(f"offline workload checks failed for {domain}")
    action = 'checked' if run_tests else 'bound to test modules'
    print(f"Offline workloads {action}: {len(checks)} of {len(matrix['domains'])}. Model calls: 0.")


def print_status(status):
    matrix = status["matrix"]
    selected = {'/'.join(cell) for cell in selected_cells(status)}
    cells = [cell for key, cell in matrix['cells'].items() if key in selected]
    total = len(selected)
    admitted = sum(cell["status"] == "admitted" for cell in cells)
    results = [cell.get("current_model_result", {}) for cell in cells]
    reviewed = [result for result in results if result.get("status") == "reviewed"]
    sustained = sum(bool(result.get("three_agent_swarm") and result.get("sustained_substantive_exchange"))
                    for result in reviewed)
    smaller = sum(bool(result.get("established_channel")) for result in reviewed) - sustained
    sys.path.insert(0, str(PACKAGE))
    from swarmform.input_catalog import build
    from swarmform.inputs import digest
    from_main = 0
    for key, cell in matrix["cells"].items():
        if key in selected and cell["status"] == "admitted":
            deployment, encoding, domain = key.split("/")
            manifest = build("november", domain, deployment=deployment, encoding=encoding)[2]
            from_main += digest(manifest) == read_record(repository_file(cell["evidence"]))["input_sha256"]
    scope = status['delivery_scope']
    print(f"Delivery: {scope['primary_input_count']} {scope['primary_domain']} inputs + {scope['generalization_input_count']} {scope['generalization_domain']} inputs.")
    print(f"Inputs: {admitted}/{total} have an admitted version, {from_main}/{total} match the current generator.")
    print(f"Latest reviewed versions: {len(reviewed)}. Sustained three-agent exchange: {sustained}. "
          f"Other observed channels: {smaller}. No observed channel: {len(reviewed) - sustained - smaller}.")
    print(f"Supplemental records retained: {len(matrix['cells']) - len(cells)}. These do not increase the delivery count.")
    for run in status["active_rollouts"] + status.get("active_input_checks", []):
        print(f"Active: {run.get('identifier') or run['matrix_cell']} (last recorded PID {run.get('pid')}).")
    print("Next:", status["next_action"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory-only', action='store_true',
                        help='Check input and registration records; the full suite runs workload tests separately')
    parser.add_argument('--status', action='store_true', help='Print current progress without running checks')
    args = parser.parse_args(argv)
    status = read_record(STATUS)
    if args.status:
        print_status(status)
        return
    manifests = validate_active_matrix(status)
    check_registrations(status, manifests)
    check_workloads(status["matrix"], run_tests=not args.inventory_only)


if __name__ == "__main__":
    main()
