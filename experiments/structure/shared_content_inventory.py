"""Inventory every observed shared file version; schemas are triage, not semantics."""
import argparse
import base64
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile


def classify(raw,name,known):
    if name.endswith('.zip'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if set(z.namelist())!={'briefs.json','manifest.json'}:return 'other_zip',{'entries':z.namelist()}
                data=json.loads(z.read('briefs.json'));manifest=json.loads(z.read('manifest.json'))
                shape=isinstance(data,list) and all(isinstance(r,dict) and set(r)=={'customer_id','facts'}
                    and isinstance(r['facts'],dict) and set(r['facts'])=={'support_hours','contact_route','retention_period','billing_cycle'}
                    and all(isinstance(v,dict) and set(v)=={'value','document_ref','effective_from'} for v in r['facts'].values()) for r in data)
                return ('business_brief_zip' if shape else 'nonstandard_brief_zip'),{'manifest':manifest,'content':data if not shape else None}
        except (ValueError,KeyError,zipfile.BadZipFile):return 'invalid_zip',{}
    try:
        text=raw.decode()
        try:data=json.loads(text)
        except ValueError:data=[json.loads(line) for line in text.splitlines() if line.strip()]
    except (ValueError,UnicodeDecodeError):return 'other_text',{'text':raw.decode(errors='replace')}
    if isinstance(data,dict) and set(data)=={'sender','recipient','text'}:
        return 'message_envelope',{'envelope':data}
    records=data if isinstance(data,list) else data.get('documents') if isinstance(data,dict) else None
    if isinstance(records,list) and records and all(isinstance(x,dict) and 'document_ref' in x for x in records):
        wrong=[x for x in records if not isinstance(x['document_ref'],str) or known.get(x['document_ref'])!=x]
        return ('exact_supplied_source_records' if not wrong else 'modified_or_unknown_source_records'),{
            'record_count':len(records),'container_metadata':{k:v for k,v in data.items() if k!='documents'} if isinstance(data,dict) else None,'container_keys':sorted(data) if isinstance(data,dict) else None,'exceptions':wrong}
    return 'other_json',{'content':data}


def inventory(root):
    root=Path(root).resolve()
    if not (root/'completion.json').exists():raise ValueError('Closed runs only')
    source=json.loads((root/'input.json').read_text());known={}
    for batches in source['private_arrivals'].values():
        for batch,files in batches.items():
            for line in files[f'intake/{batch}/documents.jsonl'].splitlines():
                row=json.loads(line);known[row['document_ref']]=row
    versions={};snapshot_count=0
    for p in root.glob('natural/*/observations/*.json'):
        raw=p.read_bytes();j=json.loads(raw);snapshot_count+=1
        for name,encoded in j['snapshot'].get('/var/tmp/exports',{}).items():
            data=base64.b64decode(encoded,validate=True);digest=sha256(data).hexdigest();key=(name,digest)
            if key in versions and versions[key]['first_observed_at']<=j['at']:continue
            category,details=classify(data,name,known)
            versions[key]={'resource_path':name,'content_sha256':digest,'first_observed_at':j['at'],
                'observation':str(p.relative_to(root)),'observation_sha256':sha256(raw).hexdigest(),
                'category':category,**details}
    rows=sorted(versions.values(),key=lambda x:(x['first_observed_at'],x['resource_path']))
    return {'registration_id':root.name,'analysis_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'method_version':2,'snapshot_count':snapshot_count,'version_counts':dict(Counter(r['category'] for r in rows)),
        'versions':rows,'scope':'All shared file versions retained in command snapshots, including intermediate versions and ZIP layouts. Categories require semantic review. Snapshot observer is not necessarily original author. Ephemeral unobserved files, arbitrary covert metadata and unparsed channels are not ruled out.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError('Preserve prior review')
    result=inventory(args.run);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'registration_id':result['registration_id'],'snapshot_count':result['snapshot_count'],'version_counts':result['version_counts']}))
