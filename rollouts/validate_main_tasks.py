"""Offline input and registration checks for the four current SwarmForm variants."""
import argparse
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from swarmform import formation_inputs
from swarmform.population import validate
from model_lineup import TASKS


def check_workstation(inputs, channel, archive):
    from swarmform.formation_common import CommonWorkspace
    from swarmform.formation_deployment import deployment

    visible, _, manifest = inputs
    startup = visible["startup"]
    reg = {"population": len(startup), "deployment": {"shared": True},
           "channel_family": manifest["channel_family"], "project_artifacts": visible["project_artifacts"],
           "freeform": True}
    constructor = CommonWorkspace if channel == "direct" else deployment
    station = constructor(startup, reg, observation_archive=archive)
    try:
        all_paths = set().union(*(files.keys() for files in startup.values()))
        for actor, files in startup.items():
            receipt = station.bindings[actor]
            if not receipt["initial_materials_verified"] or set(receipt["absent_foreign_opening_paths"]) != all_paths - files.keys():
                raise ValueError(f"Private opening failed for {actor}")
    finally:
        station.close()


def audit(population, workstations=False):
    validate(population, minimum=2)
    cells = []
    for task in TASKS:
        reference = None
        for channel in ("direct", *formation_inputs.CHANNELS):
            inputs = (formation_inputs.build_intended(task, population) if channel == "direct"
                      else formation_inputs.build(task, channel, population))
            proof = formation_inputs.witness(*inputs)["task"]
            manifest = inputs[2]
            fingerprints = (manifest["task_only_sha256"], manifest["truth_sha256"],
                            manifest["initial_project_sha256"])
            if reference is None:
                reference = fingerprints
            elif reference != fingerprints:
                raise ValueError(f"Communication setting changed the task inputs for {task}")
            if workstations:
                with tempfile.TemporaryDirectory() as folder:
                    check_workstation(inputs, channel, Path(folder))
                print(f"Offline workstation verified: {task} / {channel}", file=sys.stderr, flush=True)
            cells.append(dict(task=task, channel=channel, task_sha256=fingerprints[0],
                              conflicting_bookings=len(proof.get("incompatible_outputs", {})),
                              private_order_witnesses=len(proof.get("private_order_witnesses", {}))))
    return dict(population=population, model_calls=0, workstations_checked=workstations, cells=cells)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=int, default=3)
    parser.add_argument("--workstations", action="store_true", help="Deploy and verify private openings using SWARMHARM_DOCKER_IMAGE")
    args = parser.parse_args()
    print(json.dumps(audit(args.population, args.workstations), indent=2))
