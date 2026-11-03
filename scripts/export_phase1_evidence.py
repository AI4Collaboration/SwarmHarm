"""Create a portable, hash-preserving Engineering carrier evidence package.

Only terminal-manifest files and sealed review sidecars are included. The source
trees in those manifests are historical snapshots; original evidence is never
edited. No model calls, credentials or live service access are needed to verify.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

REPO=Path(__file__).resolve().parents[1]


def digest(path):return sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    value=(root/relative).resolve()
    if not value.is_relative_to(root.resolve()):raise ValueError('Manifest path escapes evidence root')
    return value


def export(out, roots, secrets=(), audit_roots=()):
    if out.exists():raise FileExistsError('Use a fresh export path')
    plans=[]
    for root in roots:
        terminal=json.loads((root/'evidence-manifest.json').read_text())
        review=json.loads((root/'review-manifest.json').read_text())
        if review.get('schema') == 'phase1-review-sidecars-v1':
            review_files=dict(review['files'])
            terminal_hash=review_files.pop('evidence-manifest.json')
        else:
            review_files=review['review_files']
            terminal_hash=review['terminal_manifest_sha256']
        if digest(root/'evidence-manifest.json')!=terminal_hash:
            raise ValueError('Review is not bound to terminal manifest: '+root.name)
        files={**terminal['files'],**review_files,
               'evidence-manifest.json':digest(root/'evidence-manifest.json'),
               'review-manifest.json':digest(root/'review-manifest.json')}
        plans.append((root,files,'rollouts'))
    for root in audit_roots:
        manifest_name = 'evidence-manifest.json' if (root/'evidence-manifest.json').is_file() else 'manifest.json'
        manifest = json.loads((root/manifest_name).read_text())
        files = dict(manifest.get('files',manifest))
        if not all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in files.values()):
            raise ValueError('Unsupported audit manifest: '+root.name)
        files[manifest_name] = digest(root/manifest_name)
        plans.append((root,files,'audits'))
    for root,files,role in plans:
        for relative,expected in files.items():
            source=safe_path(root,relative)
            data=source.read_bytes()
            if sha256(data).hexdigest()!=expected:raise ValueError('Evidence hash differs: '+str(source))
            if any(secret and secret in data for secret in secrets):
                raise ValueError('Credential detected; export aborted: '+relative)
            if re.search(rb'(?<![A-Za-z0-9_-])(?:Bearer\s+|sk-(?:proj-|ant-)?)[A-Za-z0-9_-]{24,}',data):
                raise ValueError('Credential-like text needs review: '+relative)
    out.mkdir(parents=True)
    mapping=[];audits=[]
    for root,files,role in plans:
        for relative in files:
            target=out/role/root.name/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(safe_path(root,relative),target)
        if role == 'audits':
            audits.append({'name':root.name,'original_root':str(root.resolve()),
                           'portable_root':'audits/'+root.name,'files':len(files)})
            continue
        mapping.append({'name':root.name,'original_root':str(root.resolve()),
            'portable_root':'rollouts/'+root.name,'terminal_manifest_sha256':files['evidence-manifest.json'],
            'review_manifest_sha256':files['review-manifest.json'],'original_hashes_preserved':True,
            'redactions':[],'files':len(files)})
    (out/'mapping.json').write_text(json.dumps({'schema':'phase1-portable-evidence-v1',
        'scope':'Engineering carrier evidence only','review_method':'AI review and programmatic verification; no independent human adjudication',
        'rollouts':mapping,'audits':audits},indent=2)+'\n')
    shutil.copyfile(REPO/'scripts/verify_phase1_export.py',out/'verify.py')
    (out/'README.txt').write_text(
        'Engineering carrier evidence package\n\n'
        'Run: python3 verify.py --replay\n'
        'This validates every terminal and review hash without network access.\n'
        'Each rollout retains its frozen code, inputs, native trace, original manifests and AI review.\n'
        'Absolute paths inside original records are provenance strings. Use mapping.json to locate portable roots.\n'
        'No files are redacted in this export; credential detection aborts before any export is created.\n'
        'A complete negative result does not demonstrate intentional communication.\n'
        'Replay uses the latest included frozen carrier validator, with historical revision parsing;\n'
        'later judgments must be stored separately from these immutable original outcomes.\n')
    manifest={str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'rollouts':len(mapping),'audits':len(audits),'files':len(manifest),'redactions':0,'model_calls':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--index',type=Path,default=REPO/'docs/research/phase1-carrier-registration-index.json')
    parser.add_argument('--additional-rollout',type=Path,action='append',default=[])
    parser.add_argument('--secret-file',type=Path,action='append',default=[])
    parser.add_argument('--audit-root',type=Path,action='append',default=[])
    args=parser.parse_args()
    roots=[(REPO/row['review_index']).resolve().parent for row in json.loads(args.index.read_text())['rows']]
    roots=list(dict.fromkeys(roots+[p.resolve() for p in args.additional_rollout]))
    secrets=[p.read_bytes().strip() for p in args.secret_file]
    print(json.dumps(export(args.output.resolve(),roots,secrets,[p.resolve() for p in args.audit_root])))
