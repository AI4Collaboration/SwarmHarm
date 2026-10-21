#!/usr/bin/env python3
"""Explicit mechanism-only registration after the retained capability-gate failure."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import run
import review
from scenario import ACTORS


def register(root):
    original=run.frozen(root)
    assert not (root/"natural-started.json").exists()
    assert not any((root/c["id"]).exists() for c in original["independent_worlds"])
    gate=review.read(root/"gate.json")
    assert gate["passed"] is False,"Use original all-correct protocol when its gate passes"
    refs=review.verify_references(root)
    control=review.audit_world(root,{"id":"control","split":True},original,refs)
    calibration=review.audit_world(root,original["calibration"],original,refs)
    world=review.read(root/"calibration/world.json")
    checks={"fresh_native_preflight":review.read(root/"preflight/summary.json")["passed"],
            "all_four_workflows_completed":calibration["progress"]=={a:4 for a in ACTORS},
            "no_calibration_or_control_errors":all(a["status"]=="completed" for w in (calibration,control) for a in w["actors"]),
            "source_unchanged":calibration["source_unchanged"] and control["source_unchanged"],
            "instructed_actual_model_exchange":len(review.control_chain(root))==4,
            "independent_source_SQL_agreement":True,
            "exact_calibration_control_histories_and_states_replayed":True}
    for a in ACTORS:
        for page in ("wayfinding-page-1","wayfinding-page-2"):
            checks[f"{a}-actual-{page}"]=any(e["actor"]==a and e["operation"]=="read" and e["target"]==page and e["accepted"] for e in world["events"])
    assert all(checks.values()),"Mechanism admission failed: "+", ".join(k for k,v in checks.items() if not v)
    files=[Path(__file__),run.ROOT/"mechanism-protocol.md"]
    snapshot=root/"mechanism-code";snapshot.mkdir(exist_ok=False)
    for p in files:(snapshot/p.name).write_bytes(p.read_bytes())
    record={"created_at":datetime.now(timezone.utc).isoformat(),"family":"swarmharm/wayfinding-live-peer-discovery-mechanism-v2",
            "authorization":"User requested launch; retains core genuine task-agent discovery and honeypot inspiration",
            "selected_after_calibration_before_natural_observation":True,
            "original_all_correct_gate_passed":False,"original_calibration_correct_records":gate["calibration_correct_records"],
            "original_calibration_total_records":gate["calibration_records"],
            "admission_checks":checks,"admission_passed":True,
            "accuracy_policy":"All task factual errors reported separately; no perfect-accuracy threshold in this mechanism-only pilot",
            "original_registration_sha256":run.sha(root/"registration.json"),"original_gate_sha256":run.sha(root/"gate.json"),
            "calibration_world_sha256":run.sha(root/"calibration/world.json"),"control_world_sha256":run.sha(root/"control/world.json"),
            "review_utility_at_admission_sha256":run.sha(Path(review.__file__)),
            "mechanism_code_hashes":{str(p.relative_to(run.REPO)):run.sha(p) for p in files},
            "natural_worlds":original["independent_worlds"],"model":original["model"],"reasoning":original["reasoning"],
            "endpoint":original["endpoint"],"primary_outcome":original["primary_outcome"],
            "frozen_subject_inputs_and_collector_unchanged":True,"no_retried_or_replaced_episodes":True,
            "confirmatory_collection":False,"pressure_or_causal_propagation_test":False}
    with (root/"mechanism-registration.json").open("x") as f:json.dump(record,f,indent=2)
    print(json.dumps({"mechanism_registered":True,"admission_checks":len(checks),"original_gate_passed":False,"calibration_correct":gate["calibration_correct_records"],"natural_worlds":len(original["independent_worlds"]),"natural_requests_so_far":0}),flush=True)


def natural(root):
    original=run.frozen(root);reg=review.read(root/"mechanism-registration.json")
    assert reg["admission_passed"]
    for p,h in reg["mechanism_code_hashes"].items():assert run.sha(run.REPO/p)==h
    for name,key in [("registration.json","original_registration_sha256"),("gate.json","original_gate_sha256"),
                     ("calibration/world.json","calibration_world_sha256"),("control/world.json","control_world_sha256")]:
        assert run.sha(root/name)==reg[key]
    assert reg["natural_worlds"]==original["independent_worlds"]
    with (root/"mechanism-started.json").open("x") as f:json.dump({"started_at":datetime.now(timezone.utc).isoformat(),"mechanism_registration_sha256":run.sha(root/"mechanism-registration.json")},f)
    started=time.monotonic()
    for cell in reg["natural_worlds"]:
        if run.MAX_BATCH-(time.monotonic()-started)<run.MAX_WORLD:
            run.save(root/"batch-stop.json",{"reason":"remaining batch budget cannot fit full world","unstarted_world":cell["id"]})
            break
        result=run.run_world(root,cell)
        if any(s in {"episode_error","empty_final"} for s in result.values()):
            run.save(root/"batch-stop.json",{"reason":"episode error","after_world":cell["id"]})
            break


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--phase",choices=["register","natural"],required=True);a=p.parse_args()
    (register if a.phase=="register" else natural)(a.output)
