"""Bind each candidate's exact startup, arrivals, packages and business outcome."""
import base64
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import io
import json
from pathlib import Path
import shlex
import zipfile
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'experiments/runtime'), str(ROOT/'experiments/swarmharm-v1')]
from swarmform.arrivals import IntakeSchedule
from swarmform.file_deployment import FileDeployment,EXPORTS
from swarmform.read_observer import observed_reads
from swarmform.inputs import digest
from swarmform.domain_inputs import build as build_domain, verify_business
from swarmform import engineering,knowledge,settlement
from swarmform_witness_solvers import SOLVERS

def exercise(domain,shared,output):
    visible,protected,manifest=build_domain('november',domain)
    module,source_file,release_file={
       'Engineering':(engineering,'types.jsonl','decoder.py'),
       'Financial Analysis':(settlement,'movements.csv','ledger.csv'),
       'Knowledge Work':(knowledge,'documents.jsonl','briefs.json')}[domain]
    offsets=manifest['effective_settings']['arrival_offsets'];actors=module.SITES
    schedule=IntakeSchedule(visible['private_arrivals'],offsets,activated_at=100)
    case=output.parent/(output.stem+('-shared' if shared else '-private'))
    if case.exists():raise FileExistsError('Preserve the previous bound witness')
    report={'domain':domain,'shared':shared,'model_calls':0,'input_manifest':manifest,
            'input_sha256':digest(manifest),'counterpart_delta':{} if shared else {'shared':False},'clock':'offline driver advancement','startup_sha256':{},'outcomes':[],'reads':[],'packages':[]}
    script=SOLVERS[domain]
    with FileDeployment(visible['startup'],shared=shared,observation_archive=case) as deployment:
        report['bindings']=deployment.bindings
        for actor in actors:
            snapshot=deployment.stations[actor].observe()
            report['startup_sha256'][actor]={}
            for path,text in visible['startup'][actor].items():
                actual=base64.b64decode(snapshot['/workspace'][path])
                assert actual==text.encode(),path
                report['startup_sha256'][actor][path]=sha256(actual).hexdigest()
        for stage,batch in enumerate(module.BATCHES):
            schedule.deliver_due(100+offsets[batch],deployment.deliver)
            def publish(actor):
                dest=f'{EXPORTS}/{actor}/{batch}'
                result,_=deployment.execute(actor,f'mkdir -p {shlex.quote(dest)}; cp /workspace/intake/{batch}/{source_file} {shlex.quote(dest)}/{source_file}')
                assert result['exit_code']==0,result
            with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(publish,actors))
            for actor in actors:
                result,snapshot=deployment.execute(actor,'python -c '+shlex.quote(script)+' '+shlex.quote(json.dumps(module.BATCHES[:stage+1])))
                assert result['exit_code']==0,result
                reads=json.loads(result['stdout'])['read_files'];station=deployment.stations[actor]
                observed=observed_reads(station.previous[f'{station.command_count:06d}.log'].decode())
                assert len(reads)==(stage+1)*(3 if shared else 1)
                for row in reads:
                    owner,version=Path(row['path']).parts[-3:-1]
                    expected=visible['private_arrivals'][owner][version][f'intake/{version}/{source_file}'].encode()
                    actual=b''.join(base64.b64decode(r['data_base64']) for r in observed if r['path']==row['path'])
                    assert actual==expected and row['sha256']==sha256(expected).hexdigest()
                files={p.removeprefix('/workspace/'):base64.b64decode(v).decode() for p,v in snapshot['/workspace'].items()}
                full=verify_business(domain,actor,snapshot,protected,visible)
                outcome=full[batch]
                if domain=='Financial Analysis' and stage==2 and shared:assert full['changes_complete'],full
                assert outcome['complete']==shared,outcome
                report['outcomes'].append({'actor':actor,'batch':batch,**outcome})
                report['reads'].append({'actor':actor,'batch':batch,'sources':reads})
                packed,after=deployment.execute(actor,'python tools/package_delivery.py '+batch)
                assert packed['exit_code']==0,packed
                path=json.loads(packed['stdout'])['package'];data=base64.b64decode(after[EXPORTS][path])
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    authored=files[f'releases/{batch}/{release_file}'].encode()
                    assert archive.read(release_file)==authored
                    assert json.loads(archive.read('manifest.json'))=={'office':actor,'batch':batch,'file':release_file,'sha256':sha256(authored).hexdigest()}
                report['packages'].append({'actor':actor,'batch':batch,'sha256':sha256(data).hexdigest(),'authored_bytes_match':True})
                notice=schedule.pending_notice(actor)
                if notice:schedule.acknowledge_notice(notice)
                assert schedule.pending_notice(actor) is None
        report['deliveries']=list(schedule.receipts.values())
    report['resources_closed']=deployment.closed
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',required=True,choices=list(SOLVERS))
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):raise ValueError('Choose a new external output file')
    output.parent.mkdir(parents=True,exist_ok=True)
    report={'kind':'bound_workload_witness','formation_assessed':False,'model_calls':0,
            'shared':exercise(args.domain,True,output),'private':exercise(args.domain,False,output)}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'domain':args.domain,'input_sha256':report['shared']['input_sha256'],
                      'shared_complete':sum(r['complete'] for r in report['shared']['outcomes']),
                      'private_incomplete':sum(not r['complete'] for r in report['private']['outcomes'])}),flush=True)
