"""Same conflicting-acceptance tasks on an explicitly configured DeepSeek route."""
import argparse
from copy import deepcopy
import os
from pathlib import Path

import conflicting
import deepseek_transport
import run

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'registrations/2026-10-20-sol-conflicting'


def configure(model, base_url, key_env='DEEPSEEK_API_KEY', key_file=None):
    deepseek_transport.configure(model, base_url, key_env, key_file)
    deepseek_transport.key()
    conflicting.configure()
    run.MODEL, run.EFFORT, run.transport = model, 'high', deepseek_transport


def prepare(root):
    conflicting.prepare(root)
    registration = run.load(root / 'registration.json')
    reference = run.load(REFERENCE / 'registration.json')
    assert run.load(root / 'fixtures.json') == run.load(REFERENCE / 'fixtures.json')
    assert run.load(root / 'tools.json') == run.load(REFERENCE / 'tools.json')
    # Identical IDs and fresh state allow exact opening-input matching.
    registration['worlds'] = deepcopy(reference['worlds'])
    (root / 'initial-input-audit.json').write_bytes((REFERENCE / 'initial-input-audit.json').read_bytes())
    for cell in registration['worlds']:
        world = run.PayablesWorld(run.load(root / 'fixtures.json'), cell['world_id'],
                                 cell['plan'], cell['weakness_open'], cell['channel'])
        for actor in cell['plan']:
            assert not world.work and not world.ledger
            world.add_actor(actor)
    registration.update(model=run.MODEL, reasoning=run.EFFORT,
        endpoint=deepseek_transport.ENDPOINT,
        credential_source='Explicit host-only API environment or key file; no credential value in study files.',
        study='DeepSeek follow-up using the exact registered Sol business tasks, tools, world plans and opening inputs.',
        matched_reference=str(REFERENCE.relative_to(run.REPO)),
        provider_compatibility={
            'api': 'Responses; preserve actual returned model IDs, reasoning content and native errors.',
            'effort': 'Request high; does not establish compute equivalence to Sol/xhigh.',
            'official_deepseek_notes': 'Developer role is treated as user; parallel_tool_calls and include are ignored. Full returned reasoning content is retained in subsequent inputs.',
            'source': 'https://api-docs.deepseek.com/guides/responses_api/',
            'verification': 'Provider transport and exact model pairing require the live preflight and normal-task gate.'})
    registration['limits'] += ['Provider semantics and reasoning settings differ; a single follow-up is descriptive, not a controlled model ranking.']
    for name in ('deepseek.py', 'deepseek_transport.py', 'deepseek_checks.py', 'DEEPSEEK.md'):
        path = HERE / name
        relative = path.relative_to(run.REPO)
        target = root / 'code' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        registration['code_hashes'][str(relative)] = run.sha(path)
    registration['input_hashes']['initial-input-audit.json'] = run.sha(root / 'initial-input-audit.json')
    run.save(root / 'registration.json', registration)
    run.save(root / 'registration-seal.json', {'sha256': run.sha(root / 'registration.json'), 'model_calls': 0})
    print('DeepSeek tasks frozen; existing Sol task inputs matched exactly, zero model calls.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['prepare', 'collect'], required=True)
    parser.add_argument('--model', default=os.environ.get('SWH_DEEPSEEK_MODEL'))
    parser.add_argument('--base-url', default=os.environ.get('SWH_DEEPSEEK_BASE_URL', 'https://api.deepseek.com'))
    parser.add_argument('--key-env', default='DEEPSEEK_API_KEY')
    parser.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    if not args.model:
        parser.error('Provide the exact provider model ID with --model or SWH_DEEPSEEK_MODEL')
    configure(args.model, args.base_url, args.key_env, args.key_file)
    root = args.output.resolve()
    if args.phase == 'prepare':
        prepare(root)
    else:
        registration = run.load(root / 'registration.json')
        assert registration['model'] == run.MODEL and registration['reasoning'] == run.EFFORT
        assert registration['endpoint'] == deepseek_transport.ENDPOINT
        run.collect(root)
