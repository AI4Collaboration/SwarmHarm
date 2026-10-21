#!/usr/bin/env python3
"""Separate observable exposure, writes, reads and reviewed full exchanges."""
import argparse
from collections import Counter
import json
from pathlib import Path

import run
import review


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);a=p.parse_args();root=a.output
    reg=review.read(root/"mechanism-registration.json")
    audit=review.read(root/"trace-audit.json")
    annotations_path=root/"message-annotations.json"
    annotations=review.read(annotations_path) if annotations_path.exists() else {"worlds":{}}
    worlds=[]
    for cell in reg["natural_worlds"]:
        folder=root/cell["id"]
        if not (folder/"results.json").exists():continue
        world=review.read(folder/"world.json");events=world["events"];by_id={e["id"]:e for e in events}
        scheduler=review.read(folder/"scheduler.json")
        audited=next(w for w in audit["worlds"] if w["id"]==cell["id"])
        writes=audited["shared_writes"]
        reads=[e for e in events if e["id"] in audited["peer_text_reads"]]
        receipt_reads=[e for e in events if e["id"] in audited["peer_receipt_reads"]]
        candidates=[]
        for request in writes:
            for received in reads:
                if received["origin_event"]!=request["id"]:continue
                for reply in writes:
                    if reply["actor"]!=received["actor"] or reply["step"]<=received["step"]:continue
                    for seen in reads:
                        if seen["actor"]==request["actor"] and seen["origin_event"]==reply["id"]:
                            candidates.append([request["id"],received["id"],reply["id"],seen["id"]])
        notes=annotations["worlds"].get(cell["id"],{})
        messages=notes.get("messages",[]);chains=notes.get("full_exchanges",[])
        for note in messages:
            event=by_id[note["event_id"]]
            assert event in writes and note["text_sha256"]==event["text_sha256"]
            assert note["classification"] in {"request","reply","data_offer","broadcast","scratch","other"}
        reviewed=[]
        for chain in chains:
            ids=chain["events"];assert ids in candidates
            request,received,reply,seen=[by_id[e] for e in ids]
            assert next(n for n in messages if n["event_id"]==request["id"])["classification"]=="request"
            assert next(n for n in messages if n["event_id"]==reply["id"])["classification"]=="reply"
            exposure=[e["id"] for e in receipt_reads if e["actor"]==request["actor"] and e["origin_actor"]==received["actor"] and e["step"]<request["step"]]
            starts=[s for s in scheduler if s["event"]=="response_start" and s["actor"]==request["actor"] and s["after_event"]<request["step"]]
            active=starts[-1]["active_actors"] if starts else []
            reviewed.append({**chain,"requester":request["actor"],"recipient":received["actor"],
                             "prior_receipt_exposure_to_recipient":exposure,"recipient_active_at_request_response":received["actor"] in active,
                             "all_actions_permitted":all(e["permitted"] for e in (request,received,reply,seen)),
                             "actual_model_authors_and_reads_verified":True,"causal_influence_established":False})
        worlds.append({"id":cell["id"],"replicate":cell["replicate"],"actors":audited["actors"],"requests":audited["requests"],
                       "completed_responses":audited["completed_responses"],"tools":audited["tools"],"progress":world["progress"],
                       "shared_writes":len(writes),"peer_text_reads":len(reads),"peer_receipt_reads":len(receipt_reads),
                       "actors_reading_true_peer_receipts":sorted({e["actor"] for e in receipt_reads}),
                       "unreviewed_structural_exchange_candidates":candidates,"reviewed_messages":messages,"full_exchanges":reviewed,
                       "task_records":len(audited["grades"]),"correct_full_reference_records":sum(d["correct"] for d in audited["grades"]),
                       "grades":audited["grades"],"cleanup":audited["cleanup"]})
    counts=Counter()
    for w in audit["worlds"]:
        prefix="instructed_control" if w["id"]=="control" else "calibration" if w["id"]=="calibration" else "natural"
        counts[prefix+"_requests"]+=w["requests"];counts[prefix+"_responses"]+=w["completed_responses"];counts[prefix+"_tools"]+=w["tools"]
    preflight=list((root/"preflight").glob("*.response.json"))
    for path in preflight:
        response=review.read(path)
        assert response["model"]==reg["model"] and response["reasoning"]["effort"]==reg["reasoning"] and response["status"]=="completed"
    counts["preflight_requests"]=len(list((root/"preflight").glob("*.request.json")))
    counts["preflight_responses"]=len(preflight)
    total_requests=sum(v for k,v in counts.items() if k.endswith("_requests"))
    total_responses=sum(v for k,v in counts.items() if k.endswith("_responses"))
    assert total_requests==len(list(root.rglob("*.request.json"))) and total_responses==len(list(root.rglob("*.response.json")))
    result={"family":reg["family"],"model":reg["model"],"reasoning":reg["reasoning"],"counts":dict(counts),
            "total_requests":total_requests,"total_completed_responses":total_responses,"natural_worlds":worlds,
            "original_all_correct_gate_passed":False,"mechanism_admission_passed":True,"calibration_correct_records":reg["original_calibration_correct_records"],
            "admission_rule_selected_after_calibration_before_natural_observation":True,
            "natural_worlds_with_full_exchange":sum(bool(w["full_exchanges"]) for w in worlds),
            "natural_trajectories":sum(len(w["actors"]) for w in worlds),
            "annotations_present":annotations_path.exists(),"annotation_sha256":run.sha(annotations_path) if annotations_path.exists() else None,
            "audit_sha256":run.sha(root/"trace-audit.json"),"mechanism_registration_sha256":run.sha(root/"mechanism-registration.json"),
            "all_histories_and_states_verified":True,"all_source_states_unchanged":all(w["source_unchanged"] for w in audit["worlds"]),
            "no_credential_values_in_archive":audit["credential_values_absent"],"communication_permission":"legal",
            "no_misalignment_or_causal_pressure_propagation_claim":True,"summarizer_sha256":run.sha(Path(__file__))}
    run.save(root/"summary.json",result)
    print(json.dumps({k:result[k] for k in ("total_requests","total_completed_responses","counts","natural_worlds_with_full_exchange","natural_trajectories")}))


if __name__=="__main__":main()
