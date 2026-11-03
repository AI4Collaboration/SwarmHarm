"""Verify a portable Phase 1 package without services, network or credentials."""
from hashlib import sha256
from contextlib import contextmanager
import json
from pathlib import Path
import argparse
import sys
import re


@contextmanager
def immutable_manifest_parse_cache(reviewer, root):
    """Reuse only JSON decoding; frozen read_file still hashes every native file."""
    path = root / 'evidence-manifest.json'
    raw = path.read_bytes()
    parsed = json.loads(raw)
    original = reviewer.json

    class JsonView:
        def loads(self, data, *args, **kwargs):
            if not args and not kwargs and isinstance(data, bytes) and data == raw:
                return parsed
            return original.loads(data, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(original, name)

    reviewer.json = JsonView()
    try:
        yield
    finally:
        reviewer.json = original
        if path.read_bytes() != raw or parsed != json.loads(raw):
            raise ValueError('Sealed manifest or decoded cache changed during replay')


def verify_claude_native(base, registration, reviewer):
    """Recheck SDK/projection correspondence, including negative trajectories."""
    from phase1 import claude_native_review
    read = lambda path: json.loads(path.read_text())
    annotation = read(base/'phase1-semantic-review.json')
    counts = {}
    for actor in registration['plan']['natural']:
        folder = base/'natural'/actor
        native = [(str(p.relative_to(folder/'claude')), read(p))
                  for p in sorted((folder/'claude/native').glob('*.json'))]
        responses = sorted((folder/'trace').glob('????.response.json'))
        ids = {read(p)['id'] for p in responses}
        if {m['message']['id'] for _, m in native if m['type']=='assistant'} != ids:
            raise ValueError('Unprojected or absent Claude response: '+actor)
        for p in responses:
            claude_native_review.response(base, registration, actor, int(p.name[:4]), sealed=True)
        tools = [p for p in (folder/'trace').glob('*-tool-*.json')
                 if re.fullmatch(r'\d+-tool-\d+\.json', p.name)]
        for p in tools:
            result = read(p)
            step = int(p.name[:4])
            before = read(folder/'trace'/f'{step:04d}.response.json')['native_record']
            next_path = folder/'trace'/f'{step+1:04d}.request.json'
            after = read(next_path)['native_record'] if next_path.exists() else None
            matches = []
            for relative, message in native:
                if not (relative > before and (after is None or relative < after)):
                    continue
                content = message.get('message', {}).get('content')
                if message['type']!='user' or not isinstance(content, list):
                    continue
                for block in content:
                    if block.get('type')=='tool_result' and block.get('tool_use_id')==result['call_id']:
                        value = block['content']
                        text = value if isinstance(value,str) else '\n'.join(x.get('text','') for x in value)
                        if json.loads(text) != result['result']:
                            raise ValueError('Claude SDK tool return differs: '+str(p))
                        matches.append(relative)
            if len(matches) != 1:
                raise ValueError('Missing or duplicate timely SDK tool delivery: '+str(p))
        counts[actor] = {'assistant':len(responses), 'toolResult':len(tools)}
    if counts != annotation['native_message_counts']:
        raise ValueError('Claude review coverage differs from native records')
    return {'responses':sum(v['assistant'] for v in counts.values()),
            'tool_returns':sum(v['toolResult'] for v in counts.values()),
            'atomic_input_rechecked':registration['harness'].get('input_delivery')=='atomic-sdk-replay-v1'}


def verify(root, replay=False):
    def read(path):return json.loads(path.read_text())
    def digest(path):return sha256(path.read_bytes()).hexdigest()
    def check(base,relative,expected):
        path=(base/relative).resolve()
        if not path.is_relative_to(base.resolve()):raise ValueError('Escaping manifest path')
        if digest(path)!=expected:raise ValueError('Hash mismatch: '+str(path))
    root=root.resolve()
    def portable(relative):
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Escaping portable mapping path')
        return path
    manifest=read(root/'manifest.json')
    for relative,expected in manifest.items():check(root,relative,expected)
    mapping=read(root/'mapping.json');total=0;replayed=[];audit_worlds=[]
    if replay:
        def version(item):
            reg=read(portable(item['portable_root'])/'registration.json')
            return (int(reg['phase1_carrier_condition']['runtime']['revision'].rsplit('v',1)[1]),
                    int(item['name'].rsplit('-r',1)[1]))
        explicit=mapping.get('replay_source')
        if explicit:
            snapshot=portable(explicit['portable_snapshot'])
            source_manifest=portable(explicit['source_hashes'])
            if str(source_manifest.relative_to(root)) not in manifest:
                raise ValueError('Replay-source manifest is not bound')
            hashes=read(source_manifest)
            if len(hashes)!=explicit['source_files']:raise ValueError('Replay-source count differs')
            for relative,expected in hashes.items():
                check(snapshot,relative,expected)
                if str((snapshot/relative).resolve().relative_to(root)) not in manifest:
                    raise ValueError('Replay-source file is not bound')
            evaluator=snapshot/'experiments/swarmharm-v1'
        else:
            latest=max(mapping['rollouts'],key=version)
            evaluator=portable(latest['portable_root'])/'code/experiments/swarmharm-v1'
        sys.path.insert(0,str(evaluator))
        from phase1 import carrier_evidence, carrier_trace_review, release_packages, pressure_review
    for item in mapping['rollouts']:
        base=portable(item['portable_root'])
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
            with immutable_manifest_parse_cache(carrier_trace_review, base):
                semantic=carrier_trace_review.assess(base,reg,world,read(base/'phase1-semantic-review.json'))
                native = (verify_claude_native(base, reg, carrier_trace_review)
                          if reg.get('harness',{}).get('kind')=='claude-code' else None)
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
                             'packages':packages,'pressure':pressure,'formation':semantic['phase1_formation_passed'],
                             'claude_native':native})
    if replay:
        for item in mapping.get('audits',[]):
            for path in sorted(portable(item['portable_root']).rglob('world.json')):
                world=read(path)
                if 'engineering_carrier_probe' not in world:continue
                physical=carrier_evidence.replay(world['plan'],world['events'],world['engineering_carrier_probe'])
                packages=release_packages.replay(world['plan'],world['events'],world['engineering_carrier_probe'],world['summary'])
                audit_worlds.append({'world':str(path.relative_to(root)),
                    'foreign_observations':len(physical['foreign_observations']),
                    'ready_packages':packages['ready_packages'],'operator_only':True})
    return {'rollouts':len(mapping['rollouts']),'bound_evidence_files':total,
            'portable_hash_verification':'passed','network_or_model_calls':0,'replayed':replayed,
            'audit_worlds':audit_worlds,'replay_source':mapping.get('replay_source')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',action='store_true',help='Reconstruct physical, package and annotated native results using included frozen code.')
    args=parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent,args.replay),indent=2))
