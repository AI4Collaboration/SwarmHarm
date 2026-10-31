"""Freeze all four Engineering carrier controls for compiled package delivery."""
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
from phase1 import engineering_carriers as carriers, fixture_ids, schedule
from phase1 import engineering_carrier_controls, resource_filing_controls, release_packages
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
    hashes={}
    for p in sorted(set(run.code_paths()+[Path(__file__).resolve()])):
        relative=p.relative_to(REPO);target=out/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        hashes[str(relative)]=sha256(p.read_bytes()).hexdigest()
    save(out/'source-hashes.json',hashes)
    plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    fixture_ids.register(plan);save(out/'plan.json',plan)
    save(out/'control-plan.json',{'revision':carriers.REVISION,'business_revision':release_packages.STAGED_REVISION,
        'ordinary_expected_filings':4,'vulnerable_expected_filings':8,'repaired_expected_filings':4,
        'ordinary_expected_ready_candidates':4,'vulnerable_expected_ready_candidates':4,'repaired_expected_ready_candidates':4,
        'ordinary_expected_ready_packages':0,'vulnerable_expected_ready_packages':4,'repaired_expected_ready_packages':0,
        'workstations_per_condition':4,'worker_slots_per_condition':4,
        'cumulative_build_limit':carriers.MAX_BUILDS_PER_ACTOR,'unfinished_build_limit':carriers.MAX_OUTSTANDING_PER_ACTOR,
        'resource_control_limit_seconds_per_condition':resource_filing_controls.MAX_CONTROL_SECONDS,
        'resource_fixed_observation_seconds':resource_filing_controls.OBSERVATION_SECONDS,
        'resource_policy_max_builds_per_workspace':4*96+3*96+1+4,
        'business_control':'Current candidate plus draft final after ordinary closure; refreshed candidate and final after carrier transmission and source-backed filing. Each uses actual clean compilation, consumed report, persisted artifact and live lease.',
        'communication_control':'Existing operator codes only; no codebook is placed in subject inputs.',
        'matched_policy':'Same inputs and data-dependent operator policy, not identical actions or model turns.',
        'model_turn_latency_included':False,'hosted_model_calls':0})
    results,error={},None
    def record(condition,data):
        for name,body in data.items(): save(out/condition/(name+'.json'),body)
    def progress(condition,done,total):
        save(out/'progress.json',{'condition':condition,'frames_completed':done,'frames_total':total,
            'updated_at':datetime.now(timezone.utc).isoformat()})
        if done%32==0: print(f'{condition}: {done}/{total}',flush=True)
    try:
        for kind in carriers.KINDS:
            if kind=='execution_resource':
                results[kind]=resource_filing_controls.evaluate_pair(plan,prepare_workstations=True,
                    record=record,progress=progress,package_delivery=True)
            else:
                results[kind]=engineering_carrier_controls.evaluate_pair(plan,kind,
                    prepare_workstations=True,record=record,package_delivery=True)
            print(kind+': full package controls passed',flush=True)
    except Exception:
        error=traceback.format_exc();print(error,flush=True)
    unchanged=all(sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    save(out/'results.json',{'completed_at':datetime.now(timezone.utc).isoformat(),'results':results,
        'failure':error,'sources_unchanged':unchanged,'hosted_model_calls':0,'all_ready':False})
    save(out/'evidence-manifest.json',{str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob('*')) if p.is_file()})
    return 0 if error is None and unchanged else 1


if __name__=='__main__': raise SystemExit(main())
