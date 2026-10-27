"""Fresh longer-window condition using the unchanged v3 collector and saved inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'swarm-discovery-v3'))
spec=importlib.util.spec_from_file_location('business_collector',HERE.parent/'swarm-discovery-v3/run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.SOURCES += sorted(HERE.glob('*.py'))+[HERE/'protocol.json']
base.SOURCES += [HERE.parent/'swarm-discovery-audit-v1'/n for n in ('audit.py','test_audit.py')]
ADMISSION_SECONDS=900
PUBLICATION='experiments/swarm-discovery-window-v1/registrations/2026-10-27-long-window-r1/registration.json'


def validation_gate():
    data=json.loads((HERE/'VALIDATION.json').read_text())
    assert data['status']=='passed' and data['source_sha256']==base.source_hashes(),'missing or stale window validation'
    inherited=json.loads((HERE.parent/'swarm-discovery-v3/VALIDATION.json').read_text())
    assert all(base.source_hashes().get(p)==h for p,h in inherited['source_sha256'].items()),'inherited runtime changed'
    return hashlib.sha256((HERE/'VALIDATION.json').read_bytes()).hexdigest()


# Only the source-validation hook changes; the live collector is reused verbatim.
base.validation_gate=validation_gate


def frozen_inputs(source):
    reg=json.loads((source/'registration.json').read_text())
    assert reg['study']=='swarm-discovery-v3' and reg['budget']['actor_admission_seconds']==300
    assert not base.pending(source),'reconcile source requests before a fresh condition'
    for name,digest in reg['input_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
    assert base.hashes(source/'tasks')==reg['task_sha256']
    return reg


def prepare(out,backup,source):
    out=out.resolve();backup=backup.resolve();source=source.resolve()
    assert not out.exists() and not backup.exists(),'new output directories required'
    assert out!=backup and out not in backup.parents and backup not in out.parents
    assert not subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']).strip(),'commit source first'
    gate=validation_gate();original=frozen_inputs(source);route=base.preflight();assert not route['key_disabled']
    out.mkdir(mode=0o700)
    for name in original['input_sha256']:base.atomic_bytes(out/name,(source/name).read_bytes())
    shutil.copytree(source/'tasks',out/'tasks')
    from harbor.models.task.config import TaskConfig
    import tomllib
    for path in (out/'tasks').glob('*/task.toml'):
        text=path.read_text().replace('timeout_sec = 300','timeout_sec = 900')
        text=text.replace('family = "swarm-discovery-v3"','family = "swarm-discovery-window-v1"')
        text=text.replace('execution_adapter = "experiments/swarm-discovery-v3/run.py"','execution_adapter = "experiments/swarm-discovery-window-v1/run.py"')
        TaskConfig.model_validate(tomllib.loads(text))
        path.write_text(text)
    reg=dict(original,study='swarm-discovery-window-v1',created_at=time.time(),route=route,
        code_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        source_sha256=base.source_hashes(),validation_sha256=gate,
        budget=dict(original['budget'],actor_admission_seconds=ADMISSION_SECONDS,campaign_admission_seconds=1200),
        input_sha256=dict(original['input_sha256']),task_sha256=base.hashes(out/'tasks'),
        publication_path=PUBLICATION,
        publication_branch=subprocess.check_output(['git','-C',str(REPO),'branch','--show-current'],text=True).strip(),
        input_origin={'study':original['study'],'code_commit':original['code_commit'],
            'registration_sha256':hashlib.sha256((source/'registration.json').read_bytes()).hexdigest(),
            'rule':'Fresh contexts from exact initial inputs; no responses, notes or histories are resumed.'},
        intervention='Only admission windows change: 300 to 900 seconds per actor, 600 to 1200 per run. New expiring user-supplied credential; same model and provider. No peer/channel hints or pressure.')
    base.save(out/'registration.json',reg)
    for rel,digest in reg['source_sha256'].items():
        data=(REPO/rel).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        base.atomic_bytes(out/'code'/rel,data)
    plan=json.loads((out/'plan.json').read_text())
    base.save(out/'recovery-index.json',{'episodes':[{'id':a,'dir':'trial/agents/'+a,'status':'registered'} for a in plan],
        'backup_locations':[str(backup)],'unresolved_requests':[],
        'rule':'No replay/restart. Preserve all unknown requests; actor clocks only end new-call admission.'})
    base.export(out,backup)
    return reg


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','collect']);p.add_argument('--out',type=Path,required=True);p.add_argument('--backup',type=Path);p.add_argument('--inputs-from',type=Path);args=p.parse_args()
    if args.action=='prepare':
        assert args.backup and args.inputs_from
        result=prepare(args.out,args.backup,args.inputs_from)
    else:result=base.collect(args.out)
    print(json.dumps(result,indent=2))
