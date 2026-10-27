"""Registered parallel repetitions with unchanged business inputs and scoped allowance."""
import argparse,functools,hashlib,importlib.util,itertools,json,os,shutil,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('window_adapter',HERE.parent/'swarm-discovery-window-v1/run.py');window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
base=window.base
sys.path.insert(0,str(HERE))
import allowance
base.SOURCES += sorted(HERE.glob('*.py'))+[HERE/'protocol.json',HERE/'routes.json']
BASE_COLLECT=base.collect


def gate():
    value=json.loads((HERE/'VALIDATION.json').read_text())
    assert value['status']=='passed' and value['source_sha256']==base.source_hashes(),'stale parallel validation'
    inherited=json.loads((HERE.parent/'swarm-discovery-v3/VALIDATION.json').read_text())
    assert all(base.source_hashes().get(k)==v for k,v in inherited['source_sha256'].items())
    return hashlib.sha256((HERE/'VALIDATION.json').read_bytes()).hexdigest()
window.validation_gate=gate;base.validation_gate=gate


def cells():
    return [{'model_name':m,'seconds':s,'repaired':r} for m,s,r in itertools.product(('deepseek','glm'),(300,900),(False,True))]


def prepare(root,backup,source):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert not root.exists() and not backup.exists()
    routes=json.loads((HERE/'routes.json').read_text());gate()
    protocol=json.loads((HERE/'protocol.json').read_text());queue=[]
    # Stable shuffled blocks keep model/window/visibility cells interleaved.
    for block in range(protocol['max_blocks']):
        block_cells=sorted(cells(),key=lambda c:hashlib.sha256((str(block)+json.dumps(c,sort_keys=True)).encode()).hexdigest())
        for cell in block_cells:queue.append(dict(cell,block=block,id=f"b{block:02d}-{cell['model_name']}-{cell['seconds']}-{'repaired' if cell['repaired'] else 'natural'}"))
    root.mkdir(mode=0o700);backup.mkdir(mode=0o700)
    initial=allowance.key_remaining();deadline=datetime(2026,10,27,23,55,tzinfo=ZoneInfo('Asia/Kolkata')).timestamp()
    base.save(root/'allowance.json',{'ceiling':str(initial),'remaining':str(initial),'spent':'0','spent_at_snapshot':'0','checked_at':time.time(),'admission_deadline':deadline,'reservations':{}})
    base.save(root/'suite.json',{'study':'swarm-discovery-parallel-v1','created_at':time.time(),'max_parallel_trials':4,'queue':queue,'rule':'All launched trials count. Never restart workers or replay requests. Incomplete budget/time blocks remain reported.'})
    publications=[]
    original_preflight=base.preflight
    for cell in queue:
        route=routes[cell['model_name']];base.preflight=lambda route=route:dict(route,credential_available=True,key_disabled=False)
        out=root/'runs'/cell['id'];out.parent.mkdir(exist_ok=True)
        target=backup/'runs'/cell['id'];target.parent.mkdir(exist_ok=True)
        reg=window.prepare(out,target,source)
        reg.update(study='swarm-discovery-parallel-v1',model=route['model'],provider=route['provider'],cell=cell,
            budget=dict(reg['budget'],actor_admission_seconds=cell['seconds'],campaign_admission_seconds=cell['seconds']+300),
            publication_path=f"experiments/swarm-discovery-parallel-v1/registrations/2026-10-27-parallel-r1/{cell['id']}/registration.json",
            intervention='Factorial repeated model/provider, admission-window and repaired-visibility comparison. Exact initial inputs. Shared suite allowance admission applies before every request; censored trials stay unscored.')
        for p in (out/'tasks').glob('*/task.toml'):
            text=p.read_text().replace('timeout_sec = 900',f"timeout_sec = {cell['seconds']}").replace('swarm-discovery-window-v1','swarm-discovery-parallel-v1');p.write_text(text)
        reg['task_sha256']=base.hashes(out/'tasks');base.save(out/'registration.json',reg);base.export(out,target)
        publications.append((REPO/reg['publication_path'],(out/'registration.json').read_bytes()))
    base.preflight=original_preflight
    for public,data in publications:
        public.parent.mkdir(parents=True,exist_ok=False);base.atomic_bytes(public,data)
    base.save(root/'recovery-index.json',{'suite':'suite.json','allowance':'allowance.json','backup_locations':[str(backup)],'rule':'Do not restart. All trial journals and unknown reservations retained.'})
    base.export(root,backup)
    return {'registered_trials':len(queue),'initial_allowance_usd':str(initial)}


def collect(out,root):
    reg=json.loads((out/'registration.json').read_text());route=json.loads((HERE/'routes.json').read_text())[reg['cell']['model_name']]
    assert reg['model']==route['model'] and reg['provider']==route['provider']
    base.MODEL=reg['model'];base.PROVIDER=reg['provider']
    base.World=functools.partial(base.World,repaired=reg['cell']['repaired'])
    base.transport.DurableChat=allowance.chat_class(base.transport.DurableChat,root,route['conservative_pricing'],route['context_length'])
    return BASE_COLLECT(out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','collect']);p.add_argument('--root',type=Path,required=True);p.add_argument('--backup',type=Path);p.add_argument('--inputs-from',type=Path);p.add_argument('--out',type=Path);args=p.parse_args()
    result=prepare(args.root,args.backup,args.inputs_from) if args.action=='prepare' else collect(args.out,args.root)
    print(json.dumps(result,indent=2))
