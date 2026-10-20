"""A separately registered Luna check on unchanged unfunded-payment inputs."""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


base = module('luna_liquidity_base', REPO/'experiments/payment-liquidity-v1/run.py')


def configure():
    base.configure('sol')
    base.core.MODEL = base.core.transport.MODEL = 'gpt-6-luna'
    base.core.EFFORT = 'xhigh'


def prepare(root, match):
    base.prepare(root, 'sol', match)
    reg = base.core.load(root/'registration.json')
    reg.update(provider='luna', adapter_family='payment-liquidity-luna-v1',
        protocol='experiments/payment-liquidity-luna-v1/README.md',
        activation='Collect after the already-registered Sol and DeepSeek liquidity studies exit; one inference globally.',
        model_extension='Same complete initial inputs, fixtures, tools, pressure, worker identities, arrival plan and budgets as the matched Sol/DeepSeek cash-shortfall study. Only model changes. No new permission warning, method or cooperation cue.',
        capability_source='https://developers.openai.com/api/docs/models/gpt-6-luna',
        capability_limit='Official OpenAI documentation supports xhigh and function calling through Responses; it does not establish this account or host-route availability. Fresh preflight and normal calibration are required.')
    assert reg['model'] == 'gpt-6-luna' and reg['reasoning'] == 'xhigh'
    assert reg['endpoint'] == 'https://chatgpt.com/backend-api/codex/responses'
    assert reg['native_request_settings'] == {}
    for path in (HERE/'run.py', HERE/'README.md'):
        target = root/'code'/path.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        reg['code_hashes'][str(path.relative_to(REPO))] = base.core.sha(path)
    base.core.save(root/'registration.json', reg)
    base.core.save(root/'registration-seal.json', {
        'sha256': base.core.sha(root/'registration.json'), 'model_calls': 0})
    print('Luna registered on exact matched business inputs; no model calls.', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['prepare', 'collect'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--match', type=Path)
    args = p.parse_args(); configure()
    if args.phase == 'prepare':
        if args.match is None:
            p.error('Preparation requires a frozen liquidity reference')
        prepare(args.output.resolve(), args.match.resolve())
    else:
        reg = base.core.load(args.output/'registration.json')
        assert reg['model'] == base.core.MODEL and reg['reasoning'] == base.core.EFFORT
        assert reg['budget'] == base.core.BUDGET
        base.core.collect(args.output.resolve())
