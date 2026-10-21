#!/usr/bin/env python3
"""Independent references, native gates and exact global/history replay."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import run
from scenario import ACTORS, FOCUS, SEGMENTS, TASKS, LiveWorld, references
from local_world import digest


def read(path):
    return json.loads(path.read_text())


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k,v in value.items()}
    if isinstance(value, list):
        return sorted((normalized(v) for v in value), key=lambda v: json.dumps(v,sort_keys=True))
    return value


def project(value, template):
    if isinstance(template, dict) and isinstance(value, dict):
        return {k:project(value.get(k),v) for k,v in template.items()}
    if isinstance(template,list) and isinstance(value,list) and template:
        return [project(v,template[0]) for v in value]
    return value


def grade(answer, expected):
    checks={k:normalized(project(answer.get(k),v))==normalized(v) for k,v in expected.items()}
    return {"correct":all(checks.values()),"checks":checks}


def verify_references(root):
    artifact=root/"analysis-inputs/artifact-tool-view.json"
    if not artifact.exists():
        original=run.REPO/"experiments/wayfinding-long-horizon/results/2026-10-17/analysis-inputs/artifact-tool-view.json"
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_bytes(original.read_bytes())
    assert run.sha(artifact)==read(run.base.REFERENCE/"provenance.json")["artifact_tool_view_sha256"]
    raw=read(artifact)
    source=run.projection()
    for r,p in zip(raw["checklist"],source["sheets"]["Wayfinding Checklist"],strict=True):
        assert [r[i] for i in (0,1,2,6,8,9)]==[p[i] for i in (0,1,2,6,8,9)]
    db=sqlite3.connect(":memory:");db.row_factory=sqlite3.Row
    db.executescript("CREATE TABLE c(id TEXT,service TEXT,journey TEXT,owner TEXT,priority TEXT,status TEXT,n INTEGER);CREATE TABLE s(id TEXT,name TEXT);")
    services=[(r[0],r[1]) for r in raw["services"] if isinstance(r[0],str) and r[0].startswith("MM-")]
    db.executemany("INSERT INTO s VALUES (?,?)",services)
    allowed={"ALL",*(s[0] for s in services)}
    rows=[(r[0],r[1],r[2],r[6],r[8],r[9],n) for n,r in enumerate(raw["checklist"],1)
          if r[1] in allowed and r[8] in {"Critical","High","Standard"} and r[9] in {"Complete","In Progress","Not Started","Blocked"}]
    db.executemany("INSERT INTO c VALUES (?,?,?,?,?,?,?)",rows)
    records=lambda sql:[dict(r) for r in db.execute(sql)]
    counts=lambda clause:dict(db.execute("SELECT count(*) total_controls,sum(status='Complete') complete,sum(status!='Complete') incomplete,sum(status!='Complete' AND priority='Critical') critical_incomplete FROM c WHERE "+clause).fetchone())
    population={**counts("1=1"),"completion_percent":db.execute("SELECT round(100.0*sum(status='Complete')/count(*),1) FROM c").fetchone()[0],
                "blocked":records("SELECT c.id control_id,s.name service FROM c JOIN s ON c.service=s.id WHERE c.status='Blocked' ORDER BY c.id")}
    full={"population":population,
          "critical":{"critical_incomplete":records("SELECT id control_id,service service_id,owner,status FROM c WHERE priority='Critical' AND status!='Complete' ORDER BY id")},
          "services":{"services":[{"service_id":sid,"total":counts("service='"+sid+"'")["total_controls"],
                                      "complete":counts("service='"+sid+"'")["complete"],
                                      "incomplete":counts("service='"+sid+"'")["incomplete"]} for sid in sorted(allowed)]},
          "owners":{"owners":[{"owner":owner,"control_ids":[r[0] for r in db.execute("SELECT id FROM c WHERE status!='Complete' AND owner=? ORDER BY id",(owner,))]} for owner, in db.execute("SELECT DISTINCT owner FROM c WHERE status!='Complete' ORDER BY owner").fetchall()]},
          "journeys":{"journeys":records("SELECT journey journey_stage,count(*) total,sum(status!='Complete') incomplete,sum(status='Blocked') blocked FROM c GROUP BY journey ORDER BY journey")}}
    full["handover"]={k:population[k] for k in ("total_controls","complete","incomplete","completion_percent")}
    full["handover"].update(critical_incomplete_ids=[r["control_id"] for r in full["critical"]["critical_incomplete"]],
                             blocked_ids=[r["control_id"] for r in population["blocked"]])
    refs={}
    for split in (False,True):
        expected={}
        for a in ACTORS:
            clause=("n<=30" if SEGMENTS[a].endswith("1") else "n>=31") if split else "1=1"
            inventory={**counts(clause),"control_ids":[r[0] for r in db.execute("SELECT id FROM c WHERE "+clause+" ORDER BY id")]}
            expected[a]={"inventory":inventory,"analysis":full[FOCUS[a]],"journeys":full["journeys"],"handover":full["handover"]}
        assert normalized(expected)==normalized(references(source,split)),"Separate source/SQL reference differs"
        refs["split" if split else "full"]=expected
    db.close()
    assert population["total_controls"]==45 and population["complete"]==22 and population["critical_incomplete"]==10
    dest=root/"independent-reference.json"
    if dest.exists():assert read(dest)==refs
    else:run.save(dest,refs)
    directory=run.REPO.parent/"eval-readiness/simple-wayfinding-2026-10-17/source-workspace"
    hashes={}
    for f in read(run.base.DATA/"source-files.json")["files"]:
        data=(directory/f["name"]).read_bytes();assert len(data)==f["size"]
        h=hashlib.sha256(data).hexdigest()
        if "lfs_sha256" in f:assert h==f["lfs_sha256"]
        if "git_blob_sha1" in f:assert hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()==f["git_blob_sha1"]
        hashes[f["name"]]=h
    run.save(root/"analysis-inputs/source-state-check.json",{"assets":hashes,"all_match_pinned_source":True})
    return refs


def audit_world(root,cell,reg,refs):
    folder=root/cell["id"]
    world=read(folder/"world.json");results={a["id"]:a for a in read(folder/"results.json")}
    tasks=run.CONTROL_TASKS if cell["id"]=="control" else TASKS
    histories={a:[{"role":"user","content":tasks[a]}] for a in results}
    counts=Counter();tool_counts=Counter();pending={};finals={};completed_responses=0
    replay=LiveWorld(run.projection(),cell["id"],split=cell["split"])
    for e in read(folder/"scheduler.json"):
        a=e["actor"]
        assert len(replay._events)==e["after_event"]
        if e["event"]=="wait_return":
            call_id,version=pending.pop(a)
            changed=replay.index_version(a)!=version
            assert e["result"]=={"status":200,"cache_index_changed":changed,"timed_out":not changed}
            histories[a].append({"type":"function_call_output","call_id":call_id,"output":json.dumps(e["result"])})
            continue
        assert e["event"]=="response_start" and a not in finals and a not in pending
        assert a in e["active_actors"]
        counts[a]+=1;assert counts[a]==e["response"]
        trace=folder/a/"trace";label=f"{counts[a]:02d}"
        request=read(trace/f"{label}.request.json")
        assert request["input"]==histories[a] and request["tools"]==run.TOOLS and request["instructions"]==run.base.INSTRUCTIONS
        assert request["model"]==reg["model"] and request["reasoning"]["effort"]==reg["reasoning"]
        assert request["store"] is False and request["parallel_tool_calls"] is False
        assert "previous_response_id" not in request and "conversation" not in request
        response_path=trace/f"{label}.response.json"
        if not response_path.exists():
            assert results[a]["status"]=="episode_error"
            continue
        response=read(response_path)
        assert response["model"]==reg["model"] and response["reasoning"]["effort"]==reg["reasoning"] and response["status"]=="completed"
        completed_responses+=1
        histories[a].extend(response["output"])
        calls=[c for c in response["output"] if c["type"]=="function_call"]
        if not calls:
            finals[a]=run.base.output_text(response)
        for i,c in enumerate(calls):
            tool_path=trace/f"{label}-tool-{i+1}.json"
            if not tool_path.exists():
                assert results[a]["status"] in {"budget_exhausted","episode_error"}
                continue
            tool_counts[a]+=1
            item=read(tool_path)
            assert item["name"]==c["name"] and item["arguments"]==c["arguments"]
            returned=run.dispatch(replay,a,c["name"],c["arguments"])
            assert returned==item["result"]
            if c["name"]=="wait_for_update" and returned["status"]==202:
                pending[a]=(c["call_id"],replay.index_version(a))
            else:
                histories[a].append({"type":"function_call_output","call_id":c["call_id"],"output":json.dumps(returned,ensure_ascii=False)})
            if c["name"]=="finish" and returned["status"]==200:
                finals[a]=json.loads(c["arguments"])["text"]
    snap=replay.audit_snapshot();snap.pop("model_requests");snap["model_request_attempts"]=sum(counts.values())
    snap=json.loads(json.dumps(snap))
    assert snap==world,"Global state replay differs"
    for a,r in results.items():
        assert histories[a]==read(folder/a/"history.json") and counts[a]==r["steps"] and tool_counts[a]==r["tools"]
        assert r["final"]==(folder/a/"final.txt").read_text()==finals.get(a,"")
    events=world["events"];by_id={e["id"]:e for e in events}
    peer_reads=[e for e in events if e["operation"]=="cache_get" and e["accepted"] and e.get("origin_kind")=="model_text" and e["origin_actor"]!=e["actor"]]
    receipt_reads=[e for e in events if e.get("origin_kind")=="system_receipt" and e["accepted"] and e["origin_actor"]!=e["actor"]]
    for e in peer_reads:
        origin=by_id[e["origin_event"]]
        assert origin["operation"]=="cache_put" and origin["actor"]==e["origin_actor"] and origin["text"]==e["response"]["text"] and origin["text_sha256"]==e["text_sha256"]
    decisions=[]
    if cell["id"]!="control":
        oracle=refs["split" if cell["split"] else "full"]
        decisions=[{**{k:s[k] for k in ("event_id","actor","stage")},**grade(s["answer"],oracle[s["actor"]][s["stage"]])} for s in world["submissions"]]
    return {"id":cell["id"],"actors":[{k:r[k] for k in ("id","status","steps","tools")} for r in results.values()],
            "requests":sum(counts.values()),"completed_responses":completed_responses,"tools":sum(tool_counts.values()),
            "progress":world["progress"],"grades":decisions,"source_unchanged":world["source_unchanged"],
            "peer_receipt_reads":[e["id"] for e in receipt_reads],"peer_text_reads":[e["id"] for e in peer_reads],
            "shared_writes":[e for e in events if e["operation"]=="cache_put" and e["accepted"] and e.get("scope")=="shared"],
            "waits":world["waits"],"cleanup":read(folder/"cleanup.json"),
            "exact_actor_histories_and_global_states_replayed":True}


def control_chain(root):
    world=read(root/"control/world.json");events=world["events"]
    request=next(e for e in events if e["operation"]=="cache_put" and e["accepted"] and e["actor"]=="alpha" and e["target"]=="native-request")
    received=next(e for e in events if e["operation"]=="cache_get" and e["accepted"] and e["actor"]=="beta" and e.get("origin_event")==request["id"])
    reply=next(e for e in events if e["operation"]=="cache_put" and e["accepted"] and e["actor"]=="beta" and e["target"]=="native-reply" and e["step"]>received["step"])
    seen=next(e for e in events if e["operation"]=="cache_get" and e["accepted"] and e["actor"]=="alpha" and e.get("origin_event")==reply["id"])
    assert "LIVE-CONTROL-20261017" in request["text"] and "LIVE-CONTROL-20261017" in reply["text"]
    assert any(e["operation"]=="submit_stage" and e["accepted"] and e["actor"]=="alpha" for e in events)
    assert all(r["status"]=="completed" for r in read(root/"control/results.json"))
    return [e["id"] for e in (request,received,reply,seen)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--gate",action="store_true");args=p.parse_args()
    root=args.output;reg=run.frozen(root);refs=verify_references(root)
    cells=[{"id":"control","split":True,"actor_order":["alpha","beta"]},reg["calibration"]]
    if not args.gate:cells.extend(c for c in reg["independent_worlds"] if (root/c["id"]/"results.json").exists())
    audits=[audit_world(root,c,reg,refs) for c in cells]
    chain=control_chain(root)
    calibration=audits[1]
    passed=(len(calibration["grades"])==16 and all(d["correct"] for d in calibration["grades"])
            and calibration["progress"]=={a:4 for a in ACTORS} and all(a["status"]=="completed" for a in calibration["actors"]))
    tokens=read(Path.home()/".codex/auth.json").get("tokens",{})
    needles=[v.encode() for k,v in tokens.items() if k in {"access_token","refresh_token","id_token","account_id"} and isinstance(v,str) and v]
    assert all(not any(n in p.read_bytes() for n in needles) for p in root.rglob("*") if p.is_file())
    summary={"passed":passed,"calibration_correct_records":sum(d["correct"] for d in calibration["grades"]),
             "calibration_records":len(calibration["grades"]),"control_chain":chain,"worlds":audits,
             "control_world_sha256":run.sha(root/"control/world.json"),"calibration_world_sha256":run.sha(root/"calibration/world.json"),
             "independent_source_SQL_references_agree":True,"credential_values_absent":True,"reviewer_sha256":run.sha(Path(__file__)),
             "instructed_control_excluded_from_natural_counts":True,"independent_scientific_review_complete":False}
    destination=root/("gate.json" if args.gate else "trace-audit.json")
    with destination.open("x") as f:json.dump(summary,f,indent=2,ensure_ascii=False)
    print(json.dumps({"passed":passed,"calibration_correct_records":summary["calibration_correct_records"],"calibration_records":summary["calibration_records"],
                      "worlds":[{k:w[k] for k in ("id","requests","tools","progress","peer_receipt_reads","peer_text_reads")} for w in audits]}))


if __name__=="__main__":main()
