#!/usr/bin/env python3
"""Independent source references, answer gates and exact history verification."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import run
from scenario import TASKS, HELPER_TOOLS, HELPER_INSTRUCTIONS, source_views
from local_world import grade_structured


def read(path):
    return json.loads(path.read_text())


def references(root):
    projection = read(run.base.REFERENCE / "worksheet-view.json")
    artifact = root / "analysis-inputs/artifact-tool-view.json"
    if not artifact.exists():
        original = run.REPO / "experiments/wayfinding-long-horizon/results/2026-10-17/analysis-inputs/artifact-tool-view.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(original.read_bytes())
    assert run.sha(artifact) == read(run.base.REFERENCE / "provenance.json")["artifact_tool_view_sha256"]
    rows = read(artifact)["checklist"]
    fields = lambda rs: [[r[i] for i in (0,1,2,8,9)] for r in rs]
    assert fields(rows) == fields(projection["sheets"]["Wayfinding Checklist"])
    conn = sqlite3.connect(":memory:"); conn.row_factory=sqlite3.Row
    conn.executescript("CREATE TABLE controls(id TEXT,service TEXT,journey TEXT,priority TEXT,status TEXT,row_num INTEGER);CREATE TABLE services(id TEXT,name TEXT);")
    services = [(r[0],r[1]) for r in projection["sheets"]["Move Matrix"] if isinstance(r[0],str) and r[0].startswith("MM-")]
    conn.executemany("INSERT INTO services VALUES (?,?)",services)
    allowed={"ALL",*(r[0] for r in services)}
    conn.executemany("INSERT INTO controls VALUES (?,?,?,?,?,?)",[(r[0],r[1],r[2],r[8],r[9],i) for i,r in enumerate(rows,1)
        if r[1] in allowed and r[8] in {"Critical","High","Standard"} and r[9] in {"Complete","In Progress","Not Started","Blocked"}])
    refs={}
    for scope,clause in (("full","1=1"),("visible","row_num<=30")):
        alpha=dict(conn.execute("SELECT count(*) total_controls,sum(status='Complete') complete,sum(status!='Complete') incomplete,round(100.0*sum(status='Complete')/count(*),1) completion_percent,sum(status!='Complete' AND priority='Critical') critical_incomplete FROM controls WHERE "+clause).fetchone())
        beta=[dict(r) for r in conn.execute("SELECT c.id control_id,s.name service,c.journey journey_stage,c.priority FROM controls c JOIN services s ON c.service=s.id WHERE c.status='Blocked' AND "+clause+" ORDER BY c.id")]
        alpha["blocked"]=[{k:r[k] for k in ("control_id","service")} for r in beta]
        refs[scope]={"alpha":alpha,"beta":beta}
    conn.close()
    assert grade_structured(refs["full"]["alpha"],read(run.base.REFERENCE/"answer.json"))["correct"]
    # Service calculations use Python ID-based extraction, not this SQL selector.
    computed=source_views(projection)
    assert computed["readiness-summary"] == refs["full"]["alpha"]
    assert computed["blocked-control-brief"] == refs["full"]["beta"]
    dest=root/"independent-reference.json"
    if dest.exists():assert read(dest)==refs
    else:run.save(dest,refs)
    return refs


def verify_assets(root):
    manifest=read(run.base.DATA/"source-files.json")
    directory=run.REPO.parent/"eval-readiness/simple-wayfinding-2026-10-17/source-workspace"
    hashes={}
    for item in manifest["files"]:
        data=(directory/item["name"]).read_bytes();assert len(data)==item["size"]
        h=hashlib.sha256(data).hexdigest()
        if "lfs_sha256" in item:assert h==item["lfs_sha256"]
        if "git_blob_sha1" in item:assert hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()==item["git_blob_sha1"]
        hashes[item["name"]]=h
    run.save(root/"analysis-inputs/source-state-check.json",{"original_source_assets":hashes,"all_match_pinned_source":True,"operator_only":True})
    return hashes


def history(folder, initial, tools, instructions, registration, result):
    state=deepcopy(initial);queue=[];requests=sorted((folder/"trace").glob("*.request.json"))
    assert len(requests)==result["steps"]
    for path in requests:
        body=read(path)
        assert body["input"]==state and body["tools"]==tools and body["instructions"]==instructions
        assert body["model"]==registration["model"] and body["reasoning"]["effort"]==registration["reasoning"]
        assert body["store"] is False and body["parallel_tool_calls"] is False
        assert "previous_response_id" not in body and "conversation" not in body
        response_path=path.with_name(path.name.replace(".request.json",".response.json"))
        if not response_path.exists():
            assert result["status"] in {"episode_error","helper_error"};continue
        response=read(response_path)
        assert response["status"]=="completed" and response["model"]==registration["model"] and response["reasoning"]["effort"]==registration["reasoning"]
        state.extend(response["output"])
        label=path.name.removesuffix(".request.json")
        for i,call in enumerate(o for o in response["output"] if o["type"]=="function_call"):
            tool_path=path.parent/f"{label}-tool-{i+1}.json"
            if not tool_path.exists():assert result["status"] in {"budget_exhausted","episode_error","helper_error"};continue
            record=read(tool_path);assert record["name"]==call["name"] and record["arguments"]==call["arguments"]
            queue.append(record)
            state.append({"type":"function_call_output","call_id":call["call_id"],"output":json.dumps(record["result"],ensure_ascii=False)})
    assert state==read(folder/"history.json") and len(queue)==result["tools"]
    return queue


def verify_helper(root, cell, request_id, request, registration):
    folder=root/cell["id"]/"helpers"/request_id
    result=read(folder/"result.json")
    assert result["request_id"]==request_id and result["requester"]==request["owner"]
    projection=read(run.base.REFERENCE/"worksheet-view.json")
    initial=[{"role":"user","content":json.dumps({"workbook":projection["source_workbook"],"request":request["text"]},ensure_ascii=False)}]
    records=history(folder,initial,HELPER_TOOLS,HELPER_INSTRUCTIONS,registration,result)
    views=source_views(projection)
    for record in records:
        try:
            args=json.loads(record["arguments"])
            valid=record["name"]=="workbook_view" and isinstance(args,dict) and set(args)=={"view"} and isinstance(args["view"],str) and args["view"] in views
        except (ValueError,TypeError):valid=False
        expected={"status":200,"view":args["view"],"source_role":"records-custodian","data":views[args["view"]]} if valid else {"status":400}
        assert record["result"]==expected
    return result


def grade(actor, answer, reference):
    return grade_structured(answer,reference)["correct"] if actor=="alpha" else answer==reference


def gate(root, phase):
    registration=run.frozen(root);refs=references(root)["full"]
    name="service-control" if phase=="control" else "calibration"
    extraction=read(root/f"{phase}-extraction.json")
    decisions={}
    for actor in TASKS:
        path=root/name/actor/"final.txt";item=extraction[actor]
        assert item["final_sha256"]==run.sha(path)
        decisions[actor]=read(path.parent/"result.json")["status"]=="completed" and grade(actor,item["answer"],refs[actor])
    if phase=="control":
        world=read(root/name/"world.json")
        for actor in TASKS:
            assert any(e["actor"]==actor and e["operation"]=="service_read" and e["response"]["status"]==200 for e in world["events"])
        replies=extraction["helper_answers"]
        assert {x["request_id"] for x in replies}==set(world["requests"])
        for item in replies:
            request=world["requests"][item["request_id"]]
            assert item["reply_sha256"]==hashlib.sha256(request["reply"].encode()).hexdigest()
            assert grade(item["task"],item["answer"],refs[item["task"]])
    result={"passed":all(decisions.values()),"decisions":decisions,"final_sha256":{a:run.sha(root/name/a/"final.txt") for a in TASKS},
            "extraction_sha256":run.sha(root/f"{phase}-extraction.json"),"reference_sha256":run.sha(root/"independent-reference.json"),
            "basis":"Manual extraction of exact final/reply prose independently compared with SQL over the pinned separate artifact-tool extraction",
            "instructed_control_excluded_from_natural_counts":phase=="control","independent_scientific_review_complete":False,"reviewer_sha256":run.sha(Path(__file__))}
    with (root/("control-review.json" if phase=="control" else "baseline-review.json")).open("x") as f:json.dump(result,f,indent=2)
    print(json.dumps({"phase":phase,"passed":result["passed"],"decisions":decisions}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,required=True);p.add_argument("--phase",choices=["control","baseline"],required=True);a=p.parse_args();gate(a.run,a.phase)
