"""Fresh matched stock/fixed shell trials; frozen earlier runners stay unchanged."""
import argparse,functools,hashlib,importlib.util,itertools,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
spec=importlib.util.spec_from_file_location('window_adapter',HERE.parent/'swarm-discovery-window-v1/run.py');window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
base=window.base
sys.path.insert(0,str(HERE.parent/'swarm-discovery-parallel-v1'))
import allowance
sys.path.insert(0,str(HERE))
base.SOURCES+=sorted(HERE.rglob('*.py'))+[HERE/n for n in ('protocol.json','images.json','routes.json')]
base.SOURCES += [HERE.parent/'swarm-discovery-parallel-v1'/n for n in ('allowance.py','analyze.py')]


def gate():
    value=json.loads((HERE/'VALIDATION.json').read_text())
    assert value['status']=='passed' and value['source_sha256']==base.source_hashes(),'stale shell validation'
    images=json.loads((HERE/'images.json').read_text())
    for arm in images:
        assert images[arm]['shim_sha256']==hashlib.sha256((HERE/f'image/grep_{arm}.py').read_bytes()).hexdigest()
    return hashlib.sha256((HERE/'VALIDATION.json').read_bytes()).hexdigest()
window.validation_gate=gate;base.validation_gate=gate


def cells():
    return [{'model_name':m,'seconds':900,'repaired':False,'shell_arm':a} for m,a in itertools.product(('deepseek','glm'),('stock','fixed'))]


def prepare(root,backup,source):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert not root.exists() and not backup.exists();gate()
    routes=json.loads((HERE/'routes.json').read_text());images=json.loads((HERE/'images.json').read_text())
    queue=[]
    for block in range(2):
        rows=cells() if block==0 else list(reversed(cells()))
        for cell in rows:queue.append(dict(cell,block=block,id=f"b{block:02d}-{cell['model_name']}-{cell['shell_arm']}"))
    root.mkdir(mode=0o700);backup.mkdir(mode=0o700)
    ceiling=allowance.key_remaining();assert ceiling>0,'funded authorized credential required'
    deadline=datetime(2026,10,27,23,55,tzinfo=ZoneInfo('Asia/Kolkata')).timestamp()
    base.save(root/'allowance.json',{'ceiling':str(ceiling),'remaining':str(ceiling),'spent':'0','spent_at_snapshot':'0','checked_at':time.time(),'admission_deadline':deadline,'reservations':{}})
    base.save(root/'suite.json',{'study':'swarm-discovery-shell-v1','created_at':time.time(),'max_parallel_trials':2,'queue':queue,'rule':'Fresh contexts only. Never restart workers or replay requests; original suite/unknown holds untouched.'})
    publications=[];prior=base.preflight
    for cell in queue:
        route=routes[cell['model_name']];base.preflight=lambda route=route:dict(route,credential_available=True,key_disabled=False)
        out=root/'runs'/cell['id'];out.parent.mkdir(exist_ok=True);target=backup/'runs'/cell['id'];target.parent.mkdir(exist_ok=True)
        reg=window.prepare(out,target,source);image=images[cell['shell_arm']]['image']
        reg.update(study='swarm-discovery-shell-v1',model=route['model'],provider=route['provider'],cell=cell,image=image,
            publication_path=f"experiments/swarm-discovery-shell-v1/registrations/2026-10-27-matched-shell-r1/{cell['id']}/registration.json",
            intervention='Matched stock passthrough versus finite-root grep shim images; same initial inputs, 900-second actor/1200-second run windows, provider, tools, permissions, 30-second no-kill shell timeout and neutral feedback. No peer/channel hints.')
        for p in (out/'tasks').glob('*/task.toml'):
            text=p.read_text().replace('swarm-discovery-window-v1','swarm-discovery-shell-v1')
            text=text.replace('sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39',image);p.write_text(text)
        reg['task_sha256']=base.hashes(out/'tasks');base.save(out/'registration.json',reg);base.export(out,target)
        publications.append((REPO/reg['publication_path'],(out/'registration.json').read_bytes()))
    base.preflight=prior
    for p,data in publications:p.parent.mkdir(parents=True,exist_ok=False);base.atomic_bytes(p,data)
    base.save(root/'recovery-index.json',{'suite':'suite.json','allowance':'allowance.json','backup_locations':[str(backup)],'original_suite':'stage1-discovery-parallel-20261027-r1','rule':'Do not restart. Preserve original and new unknown requests, cost holds and late shell outputs.'})
    base.export(root,backup);return {'registered_trials':len(queue),'ceiling_usd':str(ceiling)}


def collect(out,root):
    import safe_runtime
    reg=json.loads((out/'registration.json').read_text());route=json.loads((HERE/'routes.json').read_text())[reg['cell']['model_name']]
    assert reg['model']==route['model'] and reg['provider']==route['provider']
    image=json.loads((HERE/'images.json').read_text())[reg['cell']['shell_arm']]['image'];assert reg['image']==image
    base.MODEL=reg['model'];base.PROVIDER=reg['provider'];safe_runtime.IMAGE=image
    base.World=functools.partial(base.World,repaired=False)
    base.transport.DurableChat=allowance.chat_class(base.transport.DurableChat,root,route['conservative_pricing'],route['context_length'])
    return base.collect(out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','collect']);p.add_argument('--root',type=Path,required=True);p.add_argument('--backup',type=Path);p.add_argument('--inputs-from',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
    print(json.dumps(prepare(a.root,a.backup,a.inputs_from) if a.action=='prepare' else collect(a.out,a.root),indent=2))
