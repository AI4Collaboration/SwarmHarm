#!/usr/bin/env python3
"""Revalidate one saved finance judge response in a new external directory.

This is an independent re-review; the original rollout and its score are never
modified. The response must be a preserved attempt and no model is called.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'swarmharm'))
sys.path.insert(0,str(REPO/'shared'))
from phase2 import claim_evidence


def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def paths(root):
    fixed=['registration.json','natural/world.json','independent-review.json',
           'mechanism-review.json','action-monitor.json','transcript-judge-input.json',
           'mechanism-verdict.json','transcript-judge.json','response-review.json','completion.json',
           'natural/operator/finance-closure-service/protected-events.jsonl',
           'natural/operator/finance-closure-service/original-orders.json',
           'natural/operator/finance-closure-service/first_window.json',
           'natural/operator/finance-closure-service/activate_replacements.json',
           'natural/operator/finance-closure-service/second_window.json']
    result={root/name for name in fixed}
    for pattern in ('natural/job-*/agent/trajectory.json','natural/job-*/trace/*-tool-*.json',
                    'natural/job-*/trace/*.request.json','natural/job-*/codex/native/*.json',
                    'natural/operator/tool-commits/*.json'):
        result.update(root.glob(pattern))
    return result


def separate_directory(root, destination):
    if destination==root or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('Review directory must be separate from the original rollout')
    if destination==REPO or destination.is_relative_to(REPO):
        raise ValueError('Review directory must be outside the source checkout')
    if destination.exists():
        raise FileExistsError('Review directory already exists')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path,help='Original rollout directory (read only)')
    parser.add_argument('--response-file',required=True,type=Path,help='Preserved judge attempt response')
    parser.add_argument('--review-dir',required=True,type=Path,help='New independent review directory')
    args=parser.parse_args(argv)
    root=args.output.resolve(strict=True);response=args.response_file.resolve(strict=True)
    destination=args.review_dir.resolve();separate_directory(root,destination)
    attempts=(root/'transcript-judge-attempts').resolve(strict=True)
    if response.parent!=attempts or not response.name.endswith('-response.json'):
        raise ValueError('Response must be an original saved judge attempt')
    request=response.with_name(response.name.removesuffix('-response.json')+'-request.json')
    packet_path=root/'transcript-judge-input.json';packet=json.loads(packet_path.read_text())
    mechanical=json.loads((root/'mechanism-review.json').read_text())
    if mechanical.get('input_variant')!='finance-account-retirement-v1':
        raise ValueError('Expected the registered account-retirement condition')
    original_request=json.loads(request.read_text());original_response=json.loads(response.read_text())
    model=original_request['model']
    if (original_response.get('model')!=model or original_request!=
            {**claim_evidence.judge_request(packet,model),'stream':True}):
        raise ValueError('Saved judge request or model does not match the original packet')
    status=subprocess.run(['git','status','--porcelain'],cwd=REPO,check=True,capture_output=True,text=True).stdout
    if status:raise ValueError('Re-review source checkout must be clean and committed')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,check=True,capture_output=True,text=True).stdout.strip()
    failure=response.with_name(response.name.removesuffix('-response.json')+'-validation-error.json')
    tracked=paths(root)|{request,response,failure}
    before={str(path.relative_to(root)):fingerprint(path) for path in sorted(tracked)}
    for required in ('registration.json','natural/world.json','independent-review.json',
                     'mechanism-review.json','action-monitor.json','transcript-judge-input.json'):
        if before[required] is None:raise FileNotFoundError('Missing original '+required)
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('independent-review.json','mechanism-review.json','action-monitor.json','transcript-judge-input.json'):
        shutil.copyfile(root/name,destination/name)
    command=[sys.executable,str(REPO/'swarmharm/scripts/judge_unified_transcript.py'),
             '--output',str(root),'--review-dir',str(destination),
             '--response-file',str(response),'--model',model]
    completed=subprocess.run(command,capture_output=True,text=True)
    after={str(path.relative_to(root)):fingerprint(path) for path in sorted(tracked)}
    unchanged=before==after
    source_files=('swarmharm/scripts/reprocess_finance_judgment.py',
                  'swarmharm/scripts/judge_unified_transcript.py',
                  'swarmharm/phase2/mechanism_review.py','swarmharm/phase2/claim_evidence.py',
                  'swarmharm/phase2/communication_evidence.py')
    generated={str(path.relative_to(destination)):fingerprint(path)
               for path in sorted(destination.rglob('*')) if path.is_file()}
    provenance={'schema':'swarmharm-finance-offline-rereview-v1',
        'created_at':datetime.now(timezone.utc).isoformat(),'original_output':str(root),
        'original_response':str(response),'original_inputs_sha256':before,
        'source_commit':commit,'source_files_sha256':{name:fingerprint(REPO/name) for name in source_files},
        'original_inputs_unchanged':unchanged,'model_called':False,'model':model,
        'exit_code':completed.returncode,'stdout':completed.stdout,'stderr':completed.stderr,
        'review_files_sha256':generated,
        'interpretation':'Independent corrected re-review; original score and frozen records remain unchanged.'}
    (destination/'reprocess-provenance.json').write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
    if completed.returncode or not unchanged:
        raise RuntimeError('Offline re-review failed or an original input changed; inspect provenance')
    print(json.dumps({'review_dir':str(destination),'source_commit':commit,'model_called':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
