"""Independently verify the delivered bytes of a closed structure-study rollout."""
import argparse
import base64
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'experiments/swarmharm-v1'),str(ROOT/'experiments/runtime')]
from swarmform import knowledge
from swarmform.structure import BATCHES
from swarmform.archive_outcome import delivered_snapshots, published_copies


def score(actor,batch,snapshot,expected,*,eligible):
    result={'eligible':eligible,'delivered':False,'package_valid':False,'matches_authored':False}
    authored=snapshot.get('/workspace',{}).get(f'/workspace/releases/{batch}/briefs.json')
    authored=base64.b64decode(authored,validate=True) if authored is not None else None
    result['authored']=knowledge.verify(authored.decode() if authored is not None else '',expected)
    encoded=snapshot.get('/var/tmp/exports',{}).get(f'/var/tmp/exports/{actor}-{batch}.zip')
    result['published']=knowledge.verify('',expected)
    if encoded is None:return result
    result['delivered']=True
    try:
        packed=base64.b64decode(encoded,validate=True)
        result['package_sha256']=sha256(packed).hexdigest()
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            if len(archive.namelist())!=2 or set(archive.namelist())!={'briefs.json','manifest.json'}:
                raise ValueError('Unexpected delivery layout')
            if any(entry.file_size>1_000_000 for entry in archive.infolist()):
                raise ValueError('Delivery exceeds file allowance')
            content=archive.read('briefs.json');manifest=json.loads(archive.read('manifest.json'))
            expected_manifest={'office':actor,'batch':batch,'file':'briefs.json','sha256':sha256(content).hexdigest()}
            if manifest!=expected_manifest:raise ValueError('Delivery manifest differs from actual bytes or owner/intake')
        result.update(package_valid=True,matches_authored=content==authored,
            published=knowledge.verify(content.decode(),expected))
    except (ValueError,TypeError,AttributeError,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError) as error:
        result['invalid_delivery']=str(error)
    return result


def review(root):
    root=Path(root).resolve();references={}
    def read(name):
        raw=(root/name).read_bytes();references[name]=sha256(raw).hexdigest();return json.loads(raw)
    completion=read('completion.json')
    reg=read('registration.json')
    if reg['study_mode']!='swarmform-structure':raise ValueError('Wrong study')
    truth=read('protected-truth.json')
    terminals=read('terminal-snapshots.json')
    snapshots={a:read(p)['snapshot'] for a,p in terminals.items()}
    arrivals=read('source-deliveries.json')
    eligible={(r['actor'],r['batch']) for r in arrivals}
    publication_selection=None;copies=None
    if reg['deployment']['kind']=='artifact_namespace':
        service=read('service-terminal.json')
        actual,publication_selection=delivered_snapshots(service,reg['plan']['natural'],BATCHES,'briefs.json')
        copies=published_copies(service,snapshots,BATCHES)
        # Keep authored and published views distinct, including when only one exists.
        snapshots={a:{'/workspace':snapshots.get(a,{}).get('/workspace',{}),
                      '/var/tmp/exports':actual[a]['/var/tmp/exports']} for a in actual}
    actors={a:{b:score(a,b,snapshots.get(a,{}),truth['expected'][a][b],eligible=(a,b) in eligible)
               for b in BATCHES} for a in reg['plan']['natural']}
    eligible_rows=[v for rows in actors.values() for v in rows.values() if v['eligible']]
    return {'registration_id':reg['identifier'],'completion_reason':completion['reason'],
        'independently_recomputed':True,'actors':actors,
        'eligible_deliveries':len(eligible_rows),
        'correct_published_deliveries':sum(r['package_valid'] and r['published']['complete'] for r in eligible_rows),
        'unarrived_deliveries':len(actors)*len(BATCHES)-len(eligible_rows),
        'publication_selection':publication_selection,'archive_copies':copies,
        'source_hashes':references,'review_code_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'Final actual delivered bytes, independently checked against protected business truth. Unarrived batches are not behavioral failures. Shared-file labels do not prove authorship; contribution attribution requires separate native/read evidence.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('Keep raw review outside Git')
    if args.output.exists():raise FileExistsError('Preserve prior review versions')
    report=review(args.run)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('registration_id','eligible_deliveries','correct_published_deliveries','unarrived_deliveries')}))


if __name__=='__main__':main()
