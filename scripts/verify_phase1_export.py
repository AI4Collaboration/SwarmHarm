"""Verify a portable Phase 1 package without services, network or credentials."""
from hashlib import sha256
import json
from pathlib import Path
import argparse
import sys


def verify(root, replay=False):
    def read(path):return json.loads(path.read_text())
    def digest(path):return sha256(path.read_bytes()).hexdigest()
    def check(base,relative,expected):
        path=(base/relative).resolve()
        if not path.is_relative_to(base.resolve()):raise ValueError('Escaping manifest path')
        if digest(path)!=expected:raise ValueError('Hash mismatch: '+str(path))
    manifest=read(root/'manifest.json')
    for relative,expected in manifest.items():check(root,relative,expected)
    mapping=read(root/'mapping.json');total=0;replayed=[];audit_worlds=[]
    if replay:
        def version(item):
            reg=read(root/item['portable_root']/'registration.json')
            return (int(reg['phase1_carrier_condition']['runtime']['revision'].rsplit('v',1)[1]),
                    int(item['name'].rsplit('-r',1)[1]))
        latest=max(mapping['rollouts'],key=version)
        sys.path.insert(0,str(root/latest['portable_root']/'code/experiments/swarmharm-v1'))
        from phase1 import carrier_evidence, carrier_trace_review, release_packages, pressure_review
    for item in mapping['rollouts']:
        base=root/item['portable_root']
        check(base,'evidence-manifest.json',item['terminal_manifest_sha256'])
        check(base,'review-manifest.json',item['review_manifest_sha256'])
        terminal=read(base/'evidence-manifest.json');review=read(base/'review-manifest.json')
        if review.get('schema') == 'phase1-review-sidecars-v1':
            review_files=dict(review['files'])
            terminal_hash=review_files.pop('evidence-manifest.json')
        else:
            review_files=review['review_files']
            terminal_hash=review['terminal_manifest_sha256']
        if terminal_hash!=item['terminal_manifest_sha256']:
            raise ValueError('Unbound review')
        for relative,expected in {**terminal['files'],**review_files}.items():
            check(base,relative,expected);total+=1
        if replay:
            world=read(base/'natural/world.json');reg=read(base/'registration.json')
            physical=carrier_evidence.replay(world['plan'],world['events'],world['engineering_carrier_probe'])
            packages=release_packages.replay(world['plan'],world['events'],world['engineering_carrier_probe'],world['summary'])
            semantic=carrier_trace_review.assess(base,reg,world,read(base/'phase1-semantic-review.json'))
            original=read(base/'independent-review.json')['phase1']
            for field in ('autonomous_channel_use_passed','phase1_formation_passed'):
                if semantic[field]!=original[field]:raise ValueError('Semantic result differs: '+item['name'])
            pressure = None
            if reg.get('phase1_resource_policy'):
                pressure = pressure_review.evaluate(base,reg,world,read(base/'natural/activation.json')['activated_at'])
                if pressure != original.get('resource_intervention'):
                    raise ValueError('Pressure reconstruction differs: '+item['name'])
            # V11's frozen common report omits the package aggregate. Its sealed
            # terminal audit independently carries that result; replay the bytes
            # here rather than inheriting either report's conclusion.
            if (base/'terminal-audit.json').is_file():
                terminal_audit=read(base/'terminal-audit.json')
                if 'business' in terminal_audit:
                    business={'filings':len(packages['verified_filing_events']),'finals':packages['ready_packages']}
                    if 'ready_candidates' in packages:business['candidates']=packages['ready_candidates']
                    expected=terminal_audit['business']
                    if 'filed' in expected:
                        if 'ready_candidates' in expected:
                            expected={'filings':expected['filed'],'candidates':expected['ready_candidates'],
                                      'finals':expected['ready_final_packages']}
                        else:
                            # V8 predates qualification candidates. Compare only
                            # the historical endpoints, without inventing one.
                            expected={'filings':expected['filed'],'finals':expected['ready_packages']}
                            business.pop('candidates',None)
                    if business != expected:
                        raise ValueError('Business reconstruction differs: '+item['name'])
            replayed.append({'name':item['name'],'foreign_observations':len(physical['foreign_observations']),
                             'packages':packages,'pressure':pressure,'formation':semantic['phase1_formation_passed']})
    if replay:
        for item in mapping.get('audits',[]):
            for path in sorted((root/item['portable_root']).rglob('world.json')):
                world=read(path)
                if 'engineering_carrier_probe' not in world:continue
                physical=carrier_evidence.replay(world['plan'],world['events'],world['engineering_carrier_probe'])
                packages=release_packages.replay(world['plan'],world['events'],world['engineering_carrier_probe'],world['summary'])
                audit_worlds.append({'world':str(path.relative_to(root)),
                    'foreign_observations':len(physical['foreign_observations']),
                    'ready_packages':packages['ready_packages'],'operator_only':True})
    return {'rollouts':len(mapping['rollouts']),'bound_evidence_files':total,
            'portable_hash_verification':'passed','network_or_model_calls':0,'replayed':replayed,
            'audit_worlds':audit_worlds}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',action='store_true',help='Reconstruct physical, package and annotated native results using included frozen code.')
    args=parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent,args.replay),indent=2))
