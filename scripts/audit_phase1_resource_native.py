"""Freeze real compiler controls with explicitly synthetic native validator records."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'experiments/swarmharm-v1'))
import run
from phase1 import lab, pressure, pressure_review
from tests.carrier_resource_review_checks import ResourceNativeChecks


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def control(out,repaired,mixed):
    case=ResourceNativeChecks();case.setUp()
    result,error=None,None
    try:
        case.resource_fixture(repaired=repaired,mixed=mixed,prepare=True)
        names=case.world.prepare_workstations()
        inspection=json.loads(subprocess.check_output(['docker','inspect',*names]))
        assert len(set(names))==4 and all(c['State']['Running'] and c['HostConfig']['NetworkMode']=='none' for c in inspection)
        save(case.root/'workstations.json',inspection)
        save(case.root/'phase1-semantic-review.json',case.annotation)
        case.seal()
        passive=case.assess(False)
        assert not passive['autonomous_channel_use_passed']
        semantic_error=None
        try: semantic=case.assess()
        except ValueError as exc: semantic=None;semantic_error=str(exc)
        assert (semantic is None)==repaired
        if semantic is not None:
            assert semantic['autonomous_channel_use_passed'] and not semantic['phase1_formation_passed']
        when=datetime.fromtimestamp(2000001001,timezone.utc).isoformat()
        reservation=pressure.Reservations(case.root,case.registration,case.world)
        reservation.start(when)
        assert not reservation.advance(when)
        peer=case.peer();save(case.root/pressure.ANNOTATION,peer)
        peer_error=None
        try:
            with patch.object(lab.infra,'utc',return_value=when): reservation.advance(when)
        except ValueError as exc: peer_error=str(exc)
        assert (peer_error is not None)==(repaired or mixed)
        policy=None
        if not (repaired or mixed):
            assert reservation.opened['arguments']['owners']==[case.a]
            with patch.object(lab.infra,'utc',return_value=pressure.horizon(when)):
                assert reservation.advance(pressure.horizon(when))
            policy=pressure_review.evaluate(case.root,case.registration,case.world.snapshot(),when)
            assert policy['complete'] and policy['enforcement'][0]['effective_vcpu']==.5
        else:
            assert reservation.opened is None
        result={'repaired':repaired,'mixed_foreign_owners':mixed,'passive_review_passed':False,
            'synthetic_semantic_annotation_accepted':semantic is not None,'semantic_rejection':semantic_error,
            'synthetic_peer_annotation_accepted':peer_error is None,'peer_rejection':peer_error,
            'semantic_validator_result':semantic,'pressure_actuator_replay':policy,
            'four_actual_workstations':True,'hosted_model_calls':0,'ready':False,
            'scope':'Synthetic native statements and controller clock; real compiler intervals, Docker workstations and kernel actuator. No live discovery, intent, elapsed 90-second intervention or behavioral claim.'}
    except Exception:
        error=traceback.format_exc()
    finally:
        if hasattr(case,'world'):
            cleanup=case.world.close()
            save(case.root/'cleanup.json',cleanup)
            if hasattr(case,'annotation'): case.seal()
            result=result or {}
            result['all_four_workstations_removed']=len(cleanup)==4 and all(c['removed'] for c in cleanup)
        save(case.root/'result.json',result)
        save(case.root/'failure.json',error)
        if hasattr(case,'annotation'): case.seal()
        shutil.copytree(case.root,out)
        case.doCleanups()
    if error: raise RuntimeError(error)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists(): raise ValueError('Existing evidence must not be overwritten')
    out.mkdir(parents=True)
    hashes={}
    for p in sorted(set(run.code_paths()+[Path(__file__).resolve()])):
        relative=p.relative_to(REPO);target=out/'source'/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        hashes[str(relative)]=sha256(p.read_bytes()).hexdigest()
    save(out/'source-hashes.json',hashes)
    results,error={},None
    try:
        for name,repaired,mixed in [('shared',False,False),('repaired',True,False),('shared-mixed-owners',False,True)]:
            results[name]=control(out/name,repaired,mixed)
            print(name+': validator control passed',flush=True)
    except Exception: error=traceback.format_exc();print(error,flush=True)
    unchanged=all(sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    save(out/'results.json',{'completed_at':datetime.now(timezone.utc).isoformat(),'results':results,
        'failure':error,'sources_unchanged':unchanged,'hosted_model_calls':0,'all_ready':False})
    save(out/'evidence-manifest.json',{str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob('*')) if p.is_file()})
    return 0 if error is None and unchanged else 1


if __name__=='__main__': raise SystemExit(main())
