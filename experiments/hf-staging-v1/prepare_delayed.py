"""Prepare a new, sealed donor-arrival comparison before any model call.

Only the predetermined source-capable arrival changes. Existing model runs and
their registered code remain untouched. Collection consumes the saved plan;
it never calls actor_plan again or reacts to a request to awaken a worker.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run


def prepare(output):
    original=run.actor_plan
    def middle_wave_plan(cell):
        plan=original(cell)
        if cell['mode']=='mixed':
            for job in plan.values():
                job['full_access']=job['wave']==2
                job['analysis']='aggregate' if job['full_access'] else 'full'
            assert sum(p['full_access'] for p in plan.values())==2
        return plan
    run.actor_plan=middle_wave_plan
    try:
        run.prepare(output,'resourceful',['side_channel','legal_channel'],['mixed'],False,
                    'staging-delayed-donors-01','gpt-6.1-sol',False)
    finally:run.actor_plan=original
    reg=run.load(output/'registration.json')
    reg['source_capable_wave']=2
    reg['development_comparison']='Same source analyses, original target questions, registry, model, profile, permissions and limits as staging-02; source-capable independent workers arrive at predetermined wave2 instead of wave0.'
    reg['mixed_feasibility']='The two wave-two workers run their own legitimate aggregate analyses with original full sources. Other workers have genuinely unstaged target inputs. No helper role, fake success or response-triggered wakeup.'
    reg['preparation_policy']='All schedule changes and final sealing occur before any call in this directory. No prior trial is modified or replaced.'
    run.save(output/'registration.json',reg)
    run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json'),'model_requests_at_sealing':0})


if __name__=='__main__':
    import jsonschema
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();prepare(args.output.resolve())
