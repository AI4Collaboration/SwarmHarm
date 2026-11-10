"""Export one sealed, accepted input per matrix cell from Git and the reviewed ledger."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from swarmform_scope import selected_cells, role, communication_result


PACKAGE_README = '# SwarmForm inputs\n\nEach row of index.json is one accepted environment. Its directory contains the exact workstation inputs, protected business truth, three Harbor tasks, effective input manifest and sealed model registration. The source directory identifies the matching runtime. The trajectory link and SHA-256 identify the case reviewed for that input.\n\nAcceptance is labeled as sustained communication or a reviewed functional negative under its recorded acceptance rule. A negative is not a successful swarm. All included observations use three Sol 6.1 agents through Codex and AxonHub. The index reports sustained communication, bulk exchange and correct business deliveries separately. Recipients may challenge or decline to use received information; content adoption and business improvement are not communication requirements. Credentials and protected truth belong on the operator host. Use the project running guide and register a fresh identifier for a new collection.\n'


def read_json(path):
    return json.loads(path.read_bytes())


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def build_sealed_input(source, destination, registration, dataset_key):
    # Run each generator in a fresh interpreter, so cases can use different source revisions.
    entrypoint = source / "scripts"
    sys.path.insert(0, str(entrypoint))
    import run_swarmform as runner

    reg = read_json(registration)
    deployment, encoding, domain = reg["matrix_cell"].split("/")
    visible, truth, manifest = runner.build(dataset_key, domain, deployment=deployment, encoding=encoding)
    if runner.digest(manifest) != reg["input_sha256"]:
        raise ValueError("Generator differs from the registered input: " + reg["identifier"])
    runner.save(destination / "input.json", visible)
    runner.save(destination / "protected-truth.json", truth)
    runner.save(destination / "input-manifest.json", manifest)
    runner.write_tasks(destination, visible, reg["image"], domain, deployment, manifest)
    for name, expected in (reg["input_hashes"] | reg["task_hashes"]).items():
        if hash_file(destination / name) != expected:
            raise ValueError("Generated file differs from its registered bytes: " + name)


def is_final(cell):
    result = cell.get("current_model_result", {})
    if result.get("status") != "reviewed" or result.get("runtime_failure"):
        return False
    communication = communication_result(result)
    if communication.get("three_agent_swarm") and communication.get("sustained_substantive_exchange"):
        return True
    if cell.get("final_disposition") != "accepted_negative":
        return False
    review = cell.get("negative_delivery_review", {})
    return (cell.get("status") == "admitted"
            and bool(result.get("identifier")) and bool(result.get("input_sha256"))
            and review.get("identifier") == result["identifier"]
            and review.get("input_sha256") == result["input_sha256"]
            and review.get("environment_functional") is True
            and review.get("unresolved_environment_defects") == []
            and isinstance(review.get("finding"), str) and bool(review["finding"].strip())
            and isinstance(review.get("evidence"), str) and bool(review["evidence"].strip()))


def export_accepted(repo, output, dataset_key="november", *, all_retained=False):
    ledger = read_json(repo / "docs/live-rollout-status.json")
    selected = {'/'.join(cell) for cell in selected_cells(ledger, all_retained=all_retained)}
    required = {'/'.join(cell) for cell in selected_cells(ledger)}
    missing = sorted(cell for cell in required if not is_final(ledger["matrix"]["cells"].get(cell, {})))
    if missing:
        raise ValueError("Delivery inputs still lack acceptance: " + ", ".join(missing))
    rows = []
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "inputs"
        stage.mkdir()
        for cell, item in sorted(ledger["matrix"]["cells"].items()):
            result = item.get("current_model_result", {})
            if cell not in selected or not is_final(item):
                continue
            reg_dir = repo / "experiments/swarmharm-v1/registrations" / result["identifier"]
            reg_path = reg_dir / "registration.json"
            reg, seal = read_json(reg_path), read_json(reg_dir / "registration-seal.json")
            admission = read_json(repo / item["evidence"])
            if (hash_file(reg_path) != seal["sha256"] or reg["matrix_cell"] != cell
                    or reg["input_sha256"] != result["input_sha256"]
                    or admission["input_sha256"] != result["input_sha256"]
                    or not result.get("trajectory_url") or not result.get("archive_sha256")):
                raise ValueError("Incomplete delivery evidence: " + cell)
            commit = reg["source_commit"]
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("Invalid source commit")
            source = stage / "sources" / commit
            if not source.exists():
                source.mkdir(parents=True)
                paths = list(reg["code_hashes"])
                # A local archive contains only the files sealed by this registration.
                archive = subprocess.Popen(["git", "-C", str(repo), "archive", commit, "--", *paths],
                                           stdout=subprocess.PIPE)
                with archive.stdout:
                    unpack = subprocess.run(["tar", "-xf", "-", "-C", str(source)], stdin=archive.stdout)
                if archive.wait() or unpack.returncode:
                    raise RuntimeError("Fetch the registered source commit before exporting: " + commit)
            if any(hash_file(source / name) != expected for name, expected in reg["code_hashes"].items()):
                raise ValueError("Source differs from the sealed registration: " + commit)
            deployment, encoding, domain = cell.split("/")
            package = stage / deployment / encoding / domain.lower().replace(" ", "-")
            package.mkdir(parents=True)
            for name in ("registration.json", "registration-seal.json"):
                (package / name).write_bytes((reg_dir / name).read_bytes())
            subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--build",
                            str(source), str(package), str(package / "registration.json"), dataset_key], check=True)
            rows.append({"cell": cell, "role": role(ledger, cell), "directory": package.relative_to(stage).as_posix(),
                         "source": source.relative_to(stage).as_posix(), "input_sha256": reg["input_sha256"],
                         "registration_sha256": seal["sha256"], "rollout": reg["identifier"],
                         "workload_variant": read_json(package / "input-manifest.json")["effective_settings"].get("workload_variant", "baseline"),
                         "registered_encoding_opportunity": encoding, "observed_encoding": result.get("observed_encoding"),
                         "acceptance": "sustained_communication" if communication_result(result).get("three_agent_swarm") and communication_result(result).get("sustained_substantive_exchange") else "reviewed_negative",
                         "refinement_rounds": result.get("substantive_refinement_rounds", 0),
                         "negative_delivery_review": item.get("negative_delivery_review"),
                         "sustained_three_agent_exchange": bool(communication_result(result).get("three_agent_swarm") and communication_result(result).get("sustained_substantive_exchange")),
                         "communication_criteria": communication_result(result).get("criteria_version", reg.get("criteria", {}).get("version", "original_registered_criteria")),
                         "communication_review": result.get("communication_review"),
                         "bulk_exchange": result.get("bulk_group"), "correct_deliveries_of_nine": result["fully_correct_intake_deliveries"],
                         "trajectory_url": result["trajectory_url"], "trajectory_sha256": result["archive_sha256"]})
        index = {"population": ledger["population"], "model": ledger["current_models"], "environments": len(rows),
                 "scope": "all_retained" if all_retained else ledger['delivery_scope'], "cells": rows}
        (stage / "index.json").write_text(json.dumps(index, indent=2) + "\n")
        (stage / "README.md").write_text(PACKAGE_README)
        if output.exists():
            raise FileExistsError(output)
        stage.rename(output)
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", nargs=4, required=True)
    source, output, registration, key = parser.parse_args().build
    build_sealed_input(Path(source), Path(output), Path(registration), key)
