"""A separately registered GLM route for unchanged payment-routing inputs."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


base = module('glm_routing_base', REPO/'experiments/payment-route-transfer-v1/run.py')


def configure(key_file=None):
    base.configure('deepseek')
    base.core.MODEL, base.core.EFFORT = 'glm-5.3-flash', 'high'
    base.core.transport = module('glm_routing_transport', HERE/'glm_transport.py')
    base.core.transport.configure('glm-5.3-flash', 'https://lmportal.iefbr14.xyz/v1',
                                  key_file=key_file, max_output_tokens=65536)


def prepare(root, match):
    checks = module('glm_routing_checks', HERE/'checks.py')
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(checks))
    if not result.wasSuccessful():
        raise RuntimeError(log.getvalue())
    base.prepare(root, 'glm', match)
    reg = base.core.load(root/'registration.json')
    reg.update(
        family='swarmharm/payment-route-transfer-v1',
        adapter_family='payment-route-glm-v1',
        model_extension='Exploratory GLM follow-up; identical fixtures, tools and full initial subject inputs to the matched DeepSeek/Sol routing study. Separate model and provider settings, not a pressure intervention or a population estimate.',
        activation='Collect only after the already-running Sol routing study exits. One inference globally; do not replace or restart earlier trajectories.',
        protocol='experiments/payment-route-glm-v1/README.md',
        capability_source='https://z.ai/blog/glm-5.3-flash',
        capability_limit='Official evaluations report 64K output and high-effort use; the project catalog lists this exact Responses model ID. Live preflight must establish actual route/tool compatibility; relay translation and equal compute remain unverified.')
    base.core.save(root/'adapter-controls.json', {
        'passed': True, 'model_calls': 0, 'test_methods': result.testsRun,
        'log': log.getvalue(), 'scope': 'Exact model selection and request construction; no live model calls.'})
    reg['input_hashes']['adapter-controls.json'] = base.core.sha(root/'adapter-controls.json')
    for path in sorted(HERE.glob('*')):
        if path.suffix not in ('.py', '.md'):
            continue
        rel = path.relative_to(REPO)
        target = root/'code'/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        reg['code_hashes'][str(rel)] = base.core.sha(path)
    base.core.save(root/'registration.json', reg)
    base.core.save(root/'registration-seal.json', {
        'sha256': base.core.sha(root/'registration.json'), 'model_calls': 0})
    print(json.dumps({'glm_prepared': True, 'model_calls': 0,
                      'exact_matched_inputs': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'collect'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--match', type=Path)
    parser.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    configure(args.key_file)
    if args.phase == 'prepare':
        if args.match is None:
            parser.error('Preparation requires the frozen routing reference')
        prepare(args.output.resolve(), args.match.resolve())
    else:
        reg = base.core.load(args.output/'registration.json')
        assert reg['model'] == base.core.MODEL and reg['reasoning'] == base.core.EFFORT
        assert reg['budget'] == base.core.BUDGET
        base.core.collect(args.output.resolve())
