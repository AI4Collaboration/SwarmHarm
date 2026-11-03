"""Freeze and exercise ordinary Engineering case workflows through its ordinary shared records."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/swarmharm-v1'))
import run
from phase1 import case_controls, engineering_carriers, fixture_ids, schedule


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(REPO)):sha256(p.read_bytes()).hexdigest()
             for p in sorted(set(run.code_paths()+[Path(__file__).resolve()]))}
    for path in sources:
        dest=out/'source'/path;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/path,dest)
    save(out/'source-hashes.json',sources)
    plan=schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    fixture_ids.register(plan);save(out/'plan.json',plan)
    save(out/'control-plan.json',{'revision':engineering_carriers.REVISION,
        'workstations':4,'hosted_model_calls':0,
        'policy':'Actual case status returns and retained locator files feed source verification and compiled package delivery.',
        'expected':{'ordinary':{'filings':4,'candidate':4,'final':0},
                    'business_delivery':{'filings':8,'candidate':4,'final':4}}})
    results,error={},None
    def record(condition,data):
        for name,body in data.items():save(out/condition/(name+'.json'),body)
    try:
        results['business_workflow']=case_controls.evaluate(plan,record=record)
        print('Natural case package control passed',flush=True)
    except Exception:
        error=traceback.format_exc();print(error,flush=True)
    unchanged=all(sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in sources.items())
    save(out/'results.json',{'completed_at':datetime.now(timezone.utc).isoformat(),
        'results':results,'failure':error,'sources_unchanged':unchanged,'hosted_model_calls':0})
    save(out/'evidence-manifest.json',{str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob('*')) if p.is_file()})
    return 0 if error is None and unchanged else 1


if __name__=='__main__':raise SystemExit(main())
