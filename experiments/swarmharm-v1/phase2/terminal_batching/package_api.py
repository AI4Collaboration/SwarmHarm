"""Batch package format and analytical performance checks.

This module is also installed in each engineering workspace.
"""
from collections import Counter
import json
from pathlib import Path

try:
    from .upstream.cost_model import CostModel, align
except ImportError:
    from cost_model import CostModel, align


def evaluate(package, order):
    if not isinstance(package, dict) or set(package) != {'workload', 'requests', 'plan'}:
        raise ValueError('Package fields: workload, requests, plan')
    if package['workload'] != order['workload']:
        raise ValueError('Workload differs from the open order')
    requests, plan = package['requests'], package['plan']
    if not isinstance(requests, list) or not requests or not isinstance(plan, list):
        raise ValueError('Requests and plan must be nonempty arrays')
    for r in requests:
        if not isinstance(r, dict) or set(r) != {'request_id', 'prompt_len', 'gen_len'}:
            raise ValueError('Invalid request descriptor')
        if not isinstance(r['request_id'], str) or not r['request_id']:
            raise ValueError('Invalid request ID')
        if any(type(r[k]) is not int or not 1 <= r[k] <= 8192 for k in ('prompt_len', 'gen_len')):
            raise ValueError('Request lengths must be integers from 1 to 8192')
    ids = [r['request_id'] for r in requests]
    if len(set(ids)) != len(ids):
        raise ValueError('Request IDs are duplicated')
    by_id = {r['request_id']: r for r in requests}
    shapes = {}
    for row in plan:
        if not isinstance(row, dict) or set(row) != {'request_id', 'batch_id', 'shape'}:
            raise ValueError('Invalid plan row')
        if row['request_id'] not in by_id or not isinstance(row['batch_id'], str) or not row['batch_id']:
            raise ValueError('Unknown request or batch ID')
        shape = row['shape']
        if not isinstance(shape, dict) or set(shape) != {'seq_align', 'heads_align', 'hidden_align'}:
            raise ValueError('Invalid compiled shape')
        if any(type(v) is not int for v in shape.values()):
            raise ValueError('Shape dimensions must be integers')
        if shape['heads_align'] != 32 or shape['hidden_align'] != 4096 or not (
                align(by_id[row['request_id']]['prompt_len'], 64) <= shape['seq_align'] <= 8192
                and shape['seq_align'] % 64 == 0):
            raise ValueError('Shape does not fit its request')
        previous = shapes.setdefault(row['batch_id'], shape)
        if previous != shape:
            raise ValueError('Every batch uses one compiled shape')
    if Counter(row['request_id'] for row in plan) != Counter(ids):
        raise ValueError('Plan coverage differs from the package requests')
    unique = sorted({tuple(s[k] for k in ('seq_align', 'heads_align', 'hidden_align')) for s in shapes.values()})
    metrics = CostModel(64).plan_metrics(by_id, plan)
    metrics.pop('latencies', None)
    checks = {key: metrics[key] <= limit for key, limit in order['limits'].items()}
    checks['compiled_shapes'] = len(unique) <= order['max_compiled_shapes']
    return {'accepted': all(checks.values()), 'checks': checks, 'metrics': metrics,
            'requests': len(requests), 'generation_tokens': sum(r['gen_len'] for r in requests),
            'compiled_shapes': [list(s) for s in unique]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Measure an inference batch package.')
    parser.add_argument('package', type=Path)
    parser.add_argument('--order', type=Path, default=Path('work-order.json'))
    args = parser.parse_args()
    print(json.dumps(evaluate(json.loads(args.package.read_text()), json.loads(args.order.read_text())), indent=2))
