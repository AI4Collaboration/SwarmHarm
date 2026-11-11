"""Reconstruct when correct foreign citations first appear in authored artifacts.

Observation times bound visibility of artifact state; they are not exact writing
times, message comprehension, or causal effects of a particular communication.
"""
import argparse
import base64
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path


def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def earliest_read_index(reads):
    index={}
    for row in reads:
        for reference in row['exact_matching_record_refs']:
            key=(row['source'],row['receiver'],reference)
            if key not in index or float(row['read_at_unix'])<float(index[key]['read_at_unix']):index[key]=row
    return index


def facts(raw,expected,dependencies,reads,at):
    try:
        parsed=json.loads(raw)
        if not isinstance(parsed,list):raise ValueError('Not a list')
        rows={r['customer_id']:r['facts'] for r in parsed}
    except (ValueError,TypeError,KeyError):return {'parseable':False,'correct_facts':0,'foreign_uses':[]}
    correct=[];foreign={};index=reads if isinstance(reads,dict) else earliest_read_index(reads)
    for dep in dependencies:
        customer,field=dep['customer_id'],dep['field']
        actual=rows.get(customer,{})
        if not isinstance(actual,dict) or actual.get(field)!=expected[customer][field]:continue
        correct.append(dep['document_ref'])
        if dep['source']==dep['owner']:continue
        first=index.get((dep['source'],dep['owner'],dep['document_ref']))
        if first is None or float(first['read_at_unix'])>at:continue
        foreign.setdefault(dep['source'],[]).append({'document_ref':dep['document_ref'],
            'customer_id':customer,'field':field,'read_at_unix':first['read_at_unix'],
            'read_blob':first['blob'],'read_blob_sha256':first['blob_sha256'],'read_line':first['line']})
    return {'parseable':True,'correct_facts':len(correct),'correct_refs':sorted(correct),
            'foreign_uses':[{'source':source,'count':len(refs),'facts':refs} for source,refs in sorted(foreign.items())]}


def review(root,read_report):
    root=Path(root).resolve();read_report=Path(read_report).resolve()
    if not read_report.is_relative_to(root):raise ValueError('Read report must belong to run')
    if not (root/'completion.json').exists():raise ValueError('Closed runs only')
    report=json.loads(read_report.read_text())
    if report['method_version']<4:raise ValueError('Requires per-reference read matching')
    truth=json.loads((root/'protected-truth.json').read_text())
    reg=json.loads((root/'registration.json').read_text())
    refs={str(read_report.relative_to(root)):sha256(read_report.read_bytes()).hexdigest()}
    transitions=[];inventory={};eligible={(x['actor'],x['batch']) for x in json.loads((root/'source-deliveries.json').read_text())}
    read_index=earliest_read_index(report['exact_source_read_receipts'])
    for actor in reg['plan']['natural']:
        previous={};counts=0
        for path in sorted((root/'natural'/actor/'observations').glob('*.json')):
            raw=path.read_bytes();state=json.loads(raw);counts+=1
            relative=str(path.relative_to(root));refs[relative]=sha256(raw).hexdigest()
            workspace=state['snapshot'].get('/workspace',{})
            for batch,expected in truth['expected'][actor].items():
                if (actor,batch) not in eligible:continue
                encoded=workspace.get(f'/workspace/releases/{batch}/briefs.json')
                if encoded is None:
                    if previous.get(batch) is not None:
                        transitions.append({'actor':actor,'batch':batch,'kind':'authored_artifact_absent',
                            'at':state['at'],'observation':relative,'observation_sha256':refs[relative],
                            'scope':'Current authored artifact missing; this does not establish a social role ending.'})
                        previous[batch]=None
                    continue
                content=base64.b64decode(encoded,validate=True);digest=sha256(content).hexdigest()
                if previous.get(batch)==digest:continue
                evaluation=facts(content,expected,[d for d in truth['dependencies'] if d['owner']==actor and d['batch']==batch],
                    read_index,timestamp(state['at']))
                transitions.append({'actor':actor,'batch':batch,'kind':'authored_artifact_observed',
                    'at':state['at'],'phase':state['phase'],'observation':relative,'observation_sha256':refs[relative],
                    'artifact_sha256':digest,'previous_artifact_sha256':previous.get(batch),**evaluation})
                previous[batch]=digest
        inventory[actor]=counts
    transitions.sort(key=lambda row:(row['at'],row['actor'],row['batch']))
    first=[];seen=set()
    for row in transitions:
        for edge in row.get('foreign_uses',[]):
            key=(edge['source'],row['actor'],row['batch'])
            if key in seen:continue
            seen.add(key)
            first.append({'source':key[0],'receiver':key[1],'batch':key[2],
                'first_observed_at':row['at'],'correct_foreign_facts_at_first_observation':edge['count'],
                'observation':row['observation'],'observation_sha256':row['observation_sha256'],
                'artifact_sha256':row['artifact_sha256'],'facts':edge['facts']})
    return {'registration_id':reg['identifier'],'analysis_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'method_version':2,'snapshot_counts':inventory,'transitions':transitions,'first_observed_source_use':first,
        'change_from_v1':'Index the same earliest read by source, recipient and exact reference; evidence criteria and output events are unchanged.',
        'source_hashes':refs,'scope':'Actual private authored artifacts over observation time, independently matched to protected truth and earlier complete process reads for each cited foreign record. Observation is an upper bound on artifact creation time. Shared delivery correctness is separately reviewed. No message adoption, organizational authority or causal effect is inferred.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--reads',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError('Preserve prior analyses')
    report=review(args.run,args.reads);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'registration_id':report['registration_id'],'transitions':len(report['transitions']),
                      'first_use_relationships':len(report['first_observed_source_use'])}))


if __name__=='__main__':main()
