"""Read-only cohort integrity checks; outputs stay outside sealed archives."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote


def load(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def check(repo,archive,report):
    manifest=load(archive/'archive-manifest.json');live=Path(manifest['source_export'])
    expected={entry['path'] for entry in manifest['files']}
    actual={str(p.relative_to(archive)) for p in archive.rglob('*') if p.is_file()}
    assert actual==expected|{'archive-manifest.json'},'Archive file set differs'
    assert expected=={str(p.relative_to(live)) for p in live.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for entry in manifest['files']:
        for root in [archive,live]:
            path=root/entry['path']
            assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],entry['path']
    reg=load(archive/'registration.json')
    assert sha(archive/'registration.json')==load(archive/'registration-seal.json')['sha256']
    for relative,digest in reg['code_hashes'].items():
        assert sha(repo/relative)==sha(archive/'code'/relative)==digest,relative
    for relative,digest in reg['input_hashes'].items():assert sha(archive/relative)==digest,relative
    independent=load(archive/'independent-review.json');semantic=load(archive/'semantic-review.json')
    assert independent['passed'] and independent['all_natural_workers_completed']
    assert semantic['independent_review_sha256']==sha(archive/'independent-review.json')
    assert load(archive/'gate.json')['passed'] and load(archive/'output-quality.json')['passed']
    assert load(archive/'analysis-controls.json')['passed']
    assert load(archive/'cleanup-summary.json')['owned_provider_futures_complete']
    spec=importlib.util.spec_from_file_location('release_credentials',repo/'experiments/hf-campaign-v1/review.py')
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    credentials=core.credential_findings(archive);assert credentials['passed'],credentials['findings']
    patterns=[re.compile(p) for p in [r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
        r'(?:AWS_SECRET_ACCESS_KEY|aws_secret_access_key)[\s\"\x27:=]+[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+])',
        r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}',r'\bBearer\s+[A-Za-z0-9_.-]{32,}',
        r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']]
    code_paths=[p for p in (archive/'code').rglob('*') if p.is_file() and p.suffix in {'.py','.md','.json'}]
    roots=[repo/'experiments/sol-handoff-v1',repo/'experiments/sol-transfer-v1',repo/'experiments/hf-method-analysis']
    code_paths += [p for root in roots for p in root.iterdir() if p.is_file() and p.suffix in {'.py','.md','.json'}]
    docs=[repo/'README.md',repo/'docs/working-context.md',repo/'docs/running-evals.md',repo/'docs/history-index.md',archive.parent/'README.md']
    code_paths+=docs
    for path in set(code_paths):
        assert not any(pattern.search(path.read_text()) for pattern in patterns),'Recognizable code/doc credential format: '+str(path)
    link_count=0
    for path in docs:
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',target) or target.startswith('#'):continue
            target=unquote(target.split('#')[0].strip('<>'))
            if target:
                assert (path.parent/target).resolve().exists(),(path,target)
                link_count+=1
    changed=subprocess.run(['git','diff','HEAD','--name-only'],cwd=repo,text=True,capture_output=True,check=True).stdout.splitlines()
    maintained={'README.md','docs/working-context.md','docs/running-evals.md','docs/history-index.md'}
    allowed=('experiments/sol-handoff-v1/','experiments/sol-transfer-v1/','experiments/hf-method-analysis/')
    assert all(path in maintained or path.startswith(allowed) for path in changed),changed
    report.parent.mkdir(parents=True,exist_ok=True)
    copy=report.parent/'release-code.py';shutil.copy2(Path(__file__),copy)
    result={'passed':True,'date':'2026-10-18','model_calls':0,'archive_files_verified_against_live':len(expected),
        'archive_exact_file_set':True,'registered_code_matches_worktree_and_archive':len(reg['code_hashes']),
        'registration_and_input_hashes_passed':True,'original_and_independent_gate_passed':True,
        'provider_verified_responses':sum(c.get('verified_responses',0) for c in independent['provider_counts'].values()),
        'all_cohort_workers_completed':True,'all_cohort_owned_futures_ended':True,
        'output_quality_passed':True,'analysis_controls':load(archive/'analysis-controls.json')['test_methods'],
        'credential_format_scan':credentials,'additional_code_and_docs_format_scan_files':len(set(code_paths)),
        'maintained_local_links_checked':link_count,'earlier_runtime_and_archives_unchanged':True,
        'semantic_counts':semantic['counts'],
        'analysis_code':{'path':copy.name,'sha256':sha(copy)},
        'scope':'Exact frozen/source/archive/dispatch integrity and recorded behavioral observations; no reliable incidence, intrinsic motive, causal learning or full HF reproduction claim.'}
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'archive_files':len(expected),'links':link_count,'provider_responses':result['provider_verified_responses']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args();archive=args.archive.resolve()
    check(Path.cwd().resolve(),archive,archive.parent/'release-checks.json')
