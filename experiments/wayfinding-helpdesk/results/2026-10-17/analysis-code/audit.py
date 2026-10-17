#!/usr/bin/env python3
"""Replay targets, real helper histories, source views and service deliveries."""
import argparse
from collections import Counter
import json
from pathlib import Path

import run
import review
from scenario import TASKS, facts
from local_world import digest


def audit_world(root, cell, registration):
    folder=root/cell["id"];world=review.read(folder/"world.json");results=review.read(folder/"results.json")
    tasks=run.CONTROL_TASKS if cell["id"]=="service-control" else TASKS
    queues={}
    for actor in results:
        af=folder/actor["id"]
        queues[actor["id"]]=review.history(af,[{"role":"user","content":tasks[actor["id"]]}],run.TOOLS,run.base.INSTRUCTIONS,registration,actor)
        assert actor["final"]==(af/"final.txt").read_text()
    helper_results={}
    for request_id,request in world["requests"].items():
        if cell["available"]:
            helper_results[request_id]=review.verify_helper(root,cell,request_id,request,registration)
        else:
            assert not (folder/"helpers"/request_id).exists()
    replay=run.make_world(cell)
    for event in world["events"]:
        if event["actor"]=="data-desk":
            rid=event["request_id"]
            if cell["available"]:
                h=helper_results[rid]
                evidence={"model_invoked":True,"helper_status":h["status"],"helper_result_sha256":run.sha(folder/"helpers"/rid/"result.json"),"source_state_sha256":replay._source_hash}
                text=h["final"] if h["status"]=="completed" else "The data service could not produce a response."
                replay.complete(rid,text,200 if h["status"]=="completed" else 502,evidence)
            else:
                replay.complete(rid,"The workbook data service is temporarily unavailable.",503,{"model_invoked":False})
            assert replay._events[-1]==event
            continue
        queue=queues[event["actor"]]
        while queue:
            record=queue.pop(0);before=len(replay._events)
            returned=run.dispatch(replay,event["actor"],record["name"],record["arguments"])
            assert returned==record["result"]
            if len(replay._events)>before:
                assert replay._events[-1]==event
                break
        else:raise AssertionError("Event lacks a model tool call")
    for actor,queue in queues.items():
        for record in queue:
            before=len(replay._events)
            assert run.dispatch(replay,actor,record["name"],record["arguments"])==record["result"]
            assert len(replay._events)==before
    snapshot=replay.audit_snapshot();snapshot["provider_model_requests"]=snapshot.pop("model_requests")
    snapshot["target_model_request_attempts"]=sum(a["steps"] for a in results)
    assert snapshot==world
    derived=facts(world);assert derived==review.read(folder/"outcomes.json")
    events={e["id"]:e for e in world["events"]}
    for eid in derived["cross_actor_reads"]:
        e=events[eid];origin=events[e["origin_event"]]
        assert origin["actor"]==e["origin_actor"] and origin["text"]==e["response"]["text"] and origin["text_sha256"]==e["text_sha256"]
    return {"id":cell["id"],"replicate":cell.get("replicate"),"assigned":cell["assigned"],"available":cell["available"],
            "instructed_control":cell["id"]=="service-control","actors":[{k:a[k] for k in ("id","status","steps","tools")} for a in results],
            "helper_sessions":len(helper_results),"helper_requests":sum(h["steps"] for h in helper_results.values()),
            "helper_tools":sum(h["tools"] for h in helper_results.values()),"helper_statuses":dict(Counter(h["status"] for h in helper_results.values())),
            "facts":derived,"requests":world["requests"],
            "shared_writes":[e for e in world["events"] if e["operation"]=="cache_put" and e["accepted"] and e.get("scope")=="shared"],
            "cleanup":review.read(folder/"cleanup.json")}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True);p.add_argument("--output",type=Path);args=p.parse_args()
    root=args.run;r=run.frozen(root);review.references(root);assets=review.verify_assets(root)
    worlds=[audit_world(root,c,r) for c in [r["control"],r["baseline"],*r["blocked_worlds"]]]
    reqs=list(root.rglob("*.request.json"));responses=list(root.rglob("*.response.json"))
    for path in responses:
        v=review.read(path);assert v["status"]=="completed" and v["model"]==r["model"] and v["reasoning"]["effort"]==r["reasoning"]
    tokens=review.read(Path.home()/".codex/auth.json").get("tokens",{})
    needles=[v.encode() for k,v in tokens.items() if k in {"access_token","refresh_token","id_token","account_id"} and isinstance(v,str) and v]
    assert all(not any(n in f.read_bytes() for n in needles) for f in root.rglob("*") if f.is_file())
    counts={"preflight_requests":sum("preflight" in p.parts for p in reqs),
            "instructed_control_target_requests":sum("service-control" in p.parts and "helpers" not in p.parts for p in reqs),
            "instructed_control_helper_requests":sum("service-control" in p.parts and "helpers" in p.parts for p in reqs),
            "calibration_target_requests":sum("calibration" in p.parts and "helpers" not in p.parts for p in reqs),
            "calibration_helper_requests":sum("calibration" in p.parts and "helpers" in p.parts for p in reqs),
            "blocked_target_requests":sum("preflight" not in p.parts and "service-control" not in p.parts and "calibration" not in p.parts and "helpers" not in p.parts for p in reqs),
            "blocked_helper_requests":sum("service-control" not in p.parts and "calibration" not in p.parts and "helpers" in p.parts for p in reqs)}
    assert sum(counts.values())==len(reqs)
    cells=[]
    for assigned in (False,True):
        for available in (False,True):
            ws=[w for w in worlds if w["id"] not in {"calibration","service-control"} and w["assigned"]==assigned and w["available"]==available]
            cells.append({"assigned":assigned,"available":available,"worlds":len(ws),
                          "beta_catalog_exposure_worlds":sum("beta" in w["facts"]["registry_read_actors"] for w in ws),
                          "beta_service_initiation_worlds":sum("beta" in w["facts"]["service_request_actors"] for w in ws),
                          "beta_reply_exposure_worlds":sum("beta" in w["facts"]["service_reply_read_actors"] for w in ws),
                          "service_requests":sum(len(w["facts"]["service_request_events"]) for w in ws),
                          "unauthorized_service_requests":sum(len(w["facts"]["unauthorized_service_requests"]) for w in ws),
                          "successful_reply_reads":sum(len(w["facts"]["service_reply_read_events"]) for w in ws),
                          "unauthorized_reply_reads":sum(len(w["facts"]["unauthorized_reply_reads"]) for w in ws),
                          "protected_source_reads":sum(len(w["facts"]["successful_protected_reads"]) for w in ws),
                          "shared_writes":sum(len(w["shared_writes"]) for w in ws),"actual_peer_text_reads":sum(len(w["facts"]["cross_actor_reads"]) for w in ws)})
    result={"model":r["model"],"reasoning":r["reasoning"],"requests":len(reqs),"completed_responses":len(responses),**counts,"worlds":worlds,"cells":cells,
            "exact_separate_target_and_helper_histories":True,"all_dispatched_tool_results_and_global_states_replayed":True,
            "helper_views_match_independently_extracted_SQL_reference":True,"all_source_states_unchanged":all(w["facts"]["source_unchanged"] for w in worlds),
            "credential_values_absent":True,"source_asset_hashes":assets,"all_local_providers_ended":all(not w["cleanup"]["provider_live"] for w in worlds),
            "instructed_control_excluded_from_natural_counts":True,"pressure_effect_tested":False,"causal_propagation_established":False,
            "long_horizon_established":False,"independent_scientific_review_complete":False,
            "auditor_sha256":run.sha(Path(__file__)),"review_utility_sha256":run.sha(Path(review.__file__))}
    with (args.output or root/"trace-audit.json").open("x") as f:json.dump(result,f,indent=2,ensure_ascii=False)
    print(json.dumps({k:result[k] for k in ("requests","completed_responses",*counts,"cells")}))


if __name__=="__main__":main()
