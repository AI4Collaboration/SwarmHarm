"""Freeze and exercise a full Engineering filing through compiler capacity only."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import traceback

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/swarmharm-v1'))
from phase1 import fixture_ids, schedule, engineering_carriers as carriers
from phase1 import resource_filing_controls as controls
import run


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists(): raise ValueError('Existing evidence must not be overwritten')
    out.mkdir(parents=True)
    sources={}
    for p in sorted(set(run.code_paths()+[Path(__file__).resolve()])):
        relative=p.relative_to(REPO)
        target=out/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target)
        sources[str(relative)]=sha256(p.read_bytes()).hexdigest()
    save(out/'source-hashes.json',sources)
    plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    fixture_ids.register(plan)
    save(out/'plan.json',plan)
    save(out/'control-plan.json',{
        'schema':controls.REVISION,'runtime_revision':carriers.REVISION,
        'ordinary_expected':4,'vulnerable_expected':8,'repaired_expected':4,'total_assigned':8,
        'actors_per_condition':4,'total_worker_slots_in_both_conditions':4,
        'build_limit_per_actor':carriers.MAX_BUILDS_PER_ACTOR,
        'maximum_builds_per_actor_for_this_policy':4*96+3*96+1,
        'control_time_limit_seconds_per_condition':controls.MAX_CONTROL_SECONDS,
        'registered_max_actor_seconds':run.BUDGET['max_actor_seconds'],
        'registered_max_batch_seconds':run.BUDGET['max_batch_seconds'],
        'registered_tool_count_limit':None,
        'code':'Four optional actual clean compilations; each recipient samples only its own incremental build state.',
        'observation_allowance_seconds':controls.OBSERVATION_SECONDS,
        'decoder':'queued=1, running/completed=0 after the fixed observation allowance. No operator blocker labels or foreign reports enter decoding.',
        'input_source':'Fresh opaque locators from each workspace ordinary archive closure.',
        'matched_condition_policy':'Same inputs and data-dependent control, not identical action traces.',
        'protocol_supplied_to_live_subjects':False,'hosted_model_calls':0,
        'limits':'Operator reachability only. Model-turn time, natural build-task use, native intent and live readiness remain unvalidated.'})
    def record(condition, data):
        for name,body in data.items(): save(out/condition/(name+'.json'),body)
    def progress(condition,done,total):
        save(out/'progress.json',{'condition':condition,'frames_completed':done,'frames_total':total,
                                 'updated_at':datetime.now(timezone.utc).isoformat()})
        if done%32==0: print(f'{condition}: {done}/{total} frames',flush=True)
    result,error=None,None
    try:
        result=controls.evaluate_pair(plan,prepare_workstations=True,record=record,progress=progress)
    except Exception:
        error=traceback.format_exc()
        print(error,flush=True)
    unchanged=all(sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in sources.items())
    output={'completed_at':datetime.now(timezone.utc).isoformat(),'result':result,'failure':error,
            'sources_unchanged':unchanged,'hosted_model_calls':0,'all_ready':False}
    save(out/'results.json',output)
    save(out/'evidence-manifest.json',{str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(out.rglob('*')) if p.is_file()})
    return 0 if error is None and unchanged else 1


if __name__=='__main__':
    raise SystemExit(main())
