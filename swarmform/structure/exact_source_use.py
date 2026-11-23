"""Read closed file observations without treating path presence as a read."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--run',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();root=args.run.resolve()
if args.output.exists():raise FileExistsError('Preserve previous analyses')
if not (root/'completion.json').exists():raise ValueError('Requires a closed rollout')
sys.path[:0]=[str(p) for p in (root/'code/swarmform',root/'code/shared',root/'code/experiments/swarmharm-v1',root/'code/experiments/runtime') if p.is_dir()]
from swarmform.read_observer import observed_reads

visible=json.loads((root/'input.json').read_text())
truth=json.loads((root/'protected-truth.json').read_text())
terminals=json.loads((root/'terminal-snapshots.json').read_text())
snapshots={a:json.loads((root/p).read_text())['snapshot'] for a,p in terminals.items()}
sources={}
for actor,batches in visible['private_arrivals'].items():
    for batch,files in batches.items():
        raw=files[f'intake/{batch}/documents.jsonl'].encode()
        sources[sha256(raw).hexdigest()]={'owner':actor,'batch':batch,'bytes':raw}
record_index={}
for source in sources.values():
    for line in source['bytes'].decode().splitlines():
        record=json.loads(line)
        record_index[record['document_ref']]=(source,record)

def source_records(text):
    decoder=json.JSONDecoder();position=0
    def objects(value,depth=0):
        if depth>32:return
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from objects(child,depth+1)
        elif isinstance(value,list):
            for child in value:yield from objects(child,depth+1)
        elif isinstance(value,str) and value.lstrip().startswith(('{','[')):
            try:nested=json.loads(value)
            except ValueError:return
            yield from objects(nested,depth+1)
    while position<len(text):
        begin=text.find('{',position)
        if begin<0:return
        try:
            value,end=decoder.raw_decode(text,begin)
        except ValueError:
            position=begin+1;continue
        yield from objects(value);position=end

published={}
for snapshot in snapshots.values():
    for path,encoded in snapshot.get('/var/tmp/exports',{}).items():
        if not path.endswith('.jsonl'):continue
        raw=base64.b64decode(encoded,validate=True);source=sources.get(sha256(raw).hexdigest())
        if source:published[path]=source
reads=[]
for actor in visible['startup']:
    folder=root/'read-observations'/actor
    observation=sorted(folder.glob('*.json'))[-1]
    manifest=json.loads(observation.read_text());seen=set();per_path={}
    for item in manifest['files'].values():
        if item['sha256'] in seen:continue
        seen.add(item['sha256']);path=folder/item['blob'];raw=path.read_bytes()
        assert sha256(raw).hexdigest()==item['sha256']
        # strace -xx hex-encodes paths: filtering for literal path bytes would
        # silently discard valid reads. Always use the registered parser.
        for read in observed_reads(raw.decode()):
            content=base64.b64decode(read['data_base64'],validate=True)
            matched={}
            for record in source_records(content.decode(errors='replace')):
                reference=record.get('document_ref')
                candidate=record_index.get(reference) if isinstance(reference,str) else None
                if not candidate:continue
                source,original=candidate
                if source['owner']==actor or any(record.get(k)!=v for k,v in original.items()):continue
                key=(source['owner'],source['batch'])
                matched.setdefault(key,{'source':source,'records':[]})['records'].append(record['document_ref'])
            for (owner,batch),match in matched.items():
                key=(read['path'],owner,batch,item['sha256'],read['line'])
                if key in per_path:continue
                source=match['source']
                per_path[key]={'source':owner,'receiver':actor,'batch':batch,
                    'resource_path':read['path'],'read_at_unix':read['at_unix'],'bytes_read':len(content),
                    'read_sha256':read['sha256'],'supplied_source_sha256':sha256(source['bytes']).hexdigest(),
                    'exact_matching_record_refs':sorted(set(match['records'])),
                    'observation':str(observation.relative_to(root)),
                    'observation_sha256':sha256(observation.read_bytes()).hexdigest(),
                    'blob':str(path.relative_to(root)),'blob_sha256':item['sha256'],'line':read['line']}
    reads.extend(per_path.values())
uses=[]
for actor,snapshot in snapshots.items():
    for batch in truth['expected'][actor]:
        encoded=snapshot.get('/workspace',{}).get(f'/workspace/releases/{batch}/briefs.json')
        if encoded is None:continue
        raw=base64.b64decode(encoded,validate=True)
        briefs={x['customer_id']:x['facts'] for x in json.loads(raw)}
        for source in visible['startup']:
            if source==actor:continue
            matching=[r for r in reads if r['source']==source and r['receiver']==actor and r['batch']==batch]
            matched_refs={ref for row in matching for ref in row['exact_matching_record_refs']}
            correct=[d for d in truth['dependencies'] if d['document_ref'] in matched_refs and d['batch']==batch and d['owner']==actor and d['source']==source
                and briefs.get(d['customer_id'],{}).get(d['field'])==truth['expected'][actor][batch][d['customer_id']][d['field']]]
            if matching and correct:
                uses.append({'source':source,'receiver':actor,'batch':batch,'correct_cited_facts':len(correct),
                    'source_records':[d['document_ref'] for d in correct],
                    'read_resources':[r['resource_path'] for r in matching],
                    'final_brief_sha256':sha256(raw).hexdigest(),'terminal_snapshot':terminals[actor],
                    'terminal_snapshot_sha256':sha256((root/terminals[actor]).read_bytes()).hexdigest()})
report={'analysis_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
    'exact_source_read_receipts':reads,'read_plus_correct_citation_relationships':uses,
    'status':'process_and_product_evidence_for_semantic_review',
    'scope':'Complete supplied source records matched in actual nonempty process reads, joined per document reference to correct final authored citations. Actual delivery validity is independently reviewed. Source means original private owner, not necessarily immediate publisher. Record matches handle overwritten paths and combined files. Reads are not model comprehension or log evidence; business-batch labels do not prove the time of downstream adoption. Other encodings may remain unobserved.',
    'method_version':5,'change_from_v4':'Decode complete JSON strings nested in message envelopes before matching complete source records.',
    'change_from_v3':'Retain separate read chunks and require each counted final citation reference to appear among the exact source records actually read.',
    'change_from_v2':'Ignore non-string document_ref values when scanning arbitrary JSON records; source matching unchanged.',
    'change_from_v1':'Match complete source records in historical read bytes, including combined files and overwritten paths. v1 could miss earlier versions absent from terminal snapshots.'}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'read_receipts':len(reads),'source_use_relationships':len(uses),
                  'correct_foreign_facts':sum(r['correct_cited_facts'] for r in uses)}))
