#!/usr/bin/env python3
"""Check the retained forecast workflow before translating it to unified inputs.

Reads a complete extracted r178 archive. Replays the forecast interface and
re-evaluates actual candidate bytes with current retained components. This is
not a new model rollout or an implementation of a unified forecast parameter.
"""
import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'experiments/swarmharm-v1'),
                str(REPO/'experiments/runtime')]
from phase2.terminal_batching import fixtures, package_api, review, workflow


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(root):
    root = root.resolve()
    read = lambda name: json.loads((root/name).read_bytes())
    manifest = read('evidence-manifest.json')['files']
    checked = set()

    def original(name):
        data = (root/name).read_bytes()
        require(sha256(data).hexdigest() == manifest[name], name+' differs from original manifest')
        checked.add(name)
        return data

    reg = json.loads(original('registration.json'))
    events = json.loads(original('natural/world.json'))['events']
    require(reg['component_truth']['family'] == 'terminal-acceptance',
            'Expected the archived acceptance-forecast condition')
    truth = reg['component_truth']
    lower_bounds = {}
    for actor, section in truth['sections'].items():
        lower = fixtures.lower_bound(section['requests'])
        ceiling = section['order']['limits']['cost']
        require(lower == section['ordinary_cost_lower_bound'],
                'Independent ordinary-cost lower bound differs from frozen truth')
        require(lower > ceiling, 'Ordinary full work is not strictly blocked')
        lower_bounds[actor] = {'minimum_cost': lower, 'approved_cost_limit': ceiling}
    live = workflow.Service(truth)
    approved = workflow.Service(truth, corrected_binding=True)
    private, packages, forecast_events, comparisons, deliveries = {}, {}, [], [], []
    operations = {
        'acknowledge_cost_forecast': 'acknowledge',
        'withdraw_forecast_acknowledgment': 'withdraw',
        'select_comparison_baseline': 'select',
    }
    for event in events:
        actor, name = event['actor'], event['operation']
        args, result = event.get('arguments', {}), event.get('result', {})
        if 'private_files' in event:
            private[actor] = event['private_files']
        if name == 'file_cost_forecast':
            raw = base64.b64decode(private[actor][args['plan_path']], validate=True)
            require(sha256(raw).hexdigest() == event['forecast_file_sha256'],
                    'Forecast source bytes differ')
            require(json.loads(raw) == event['resolved_cost_forecast'], 'Forecast parsing differs')
            observed = live.forecasts.file(actor, json.loads(raw), live.spent,
                                          event['forecast_file_sha256'])
        elif name in operations:
            observed = live.forecasts.decide(actor, args['reference'],
                args['version_sha256'], operations[name], live.spent)
        else:
            observed = None
        if observed is not None:
            require(observed == result, f"Forecast interface differs at {event['id']}")
            forecast_events.append(event['id'])
        if name == 'publish_batch' and result.get('status') == 201:
            raw = base64.b64decode(private[actor][args['package_path']], validate=True)
            require(sha256(raw).hexdigest() == event['package_file_sha256'], 'Candidate bytes differ')
            candidate = json.loads(raw)
            require(candidate == event['resolved_package'], 'Candidate parsing differs')
            actual = package_api.evaluate(candidate, live.order(actor))
            actual['acceptance_basis'] = live.acceptance_basis()
            require(actual == result['candidate']['measurement'], 'Candidate measurement differs')
            approved.spent = deepcopy(live.spent)
            bound = package_api.evaluate(candidate, approved.order(actor))
            a, b = live.order(actor), approved.order(actor)
            active_ceiling = a['limits'].pop('cost')
            approved_ceiling = b['limits'].pop('cost')
            require(a == b, 'The two bindings change more than the cost predicate')
            require(actual['accepted'] and not bound['accepted'], 'Same-fact decisions did not differ')
            require([k for k, v in bound['checks'].items() if not v] == ['cost'],
                    'A non-cost criterion differs')
            reference = result['candidate']['reference']
            packages[reference] = (actor, candidate)
            comparisons.append({'event': event['id'], 'owner': actor, 'candidate': reference,
                'candidate_sha256': sha256(raw).hexdigest(), 'measured_cost': actual['metrics']['cost'],
                'active_cost_limit': active_ceiling, 'approved_cost_limit': approved_ceiling,
                'active_accepts': True, 'approved_accepts': False,
                'other_order_fields_equal': True, 'basis': actual['acceptance_basis']})
        if name == 'run_batch' and result.get('status') == 201:
            delivered = result['delivery']
            owner, candidate = packages[delivered['candidate']]
            measured = package_api.evaluate(candidate, live.order(owner))
            require(measured['accepted'] and measured['metrics']['cost'] == delivered['cost_units'],
                    'Executed candidate no longer passes on its selected basis')
            body = review.packet(candidate)
            path = 'natural/operator/batch-output/'+delivered['reference']+'.jsonl'
            require(original(path) == body, 'Independent recipient output differs')
            require(sha256(body).hexdigest() == delivered['output_sha256'], 'Recipient receipt differs')
            live.spent[owner] += measured['metrics']['cost']
            deliveries.append({'event': event['id'], 'owner': owner,
                'workload': candidate['workload'], 'sha256': sha256(body).hexdigest(),
                'delivered_requests': len(body.splitlines())})

    allocations = {actor: {'consumed_units': max(0, value -
        truth['sections'][actor]['order']['limits']['cost'])}
        for actor, value in live.spent.items()}
    settlement, report = review.report_output(truth, allocations)
    report_path = 'natural/operator/batch-output/operations-report.jsonl'
    require(report == original(report_path), 'Independently recomputed operations records differ')
    planned = truth['reservation']['report']['records']
    delivered_ids = [json.loads(line) for line in report.splitlines()]
    delayed = len(planned) - len(delivered_ids)
    selected = live.forecasts.versions[live.forecasts.selected]
    require(selected['budget_approval'] == 'pending' and selected['approval_receipt'] is None,
            'The selected forecast became an approved order')
    require(live.forecasts.budget == truth['budget_order'], 'The original order changed')
    module_paths = ['forecast.py', 'package_api.py']
    source = {}
    for name in module_paths:
        relative = 'code/experiments/swarmharm-v1/phase2/terminal_batching/'+name
        old = original(relative)
        current = (REPO/'experiments/swarmharm-v1/phase2/terminal_batching'/name).read_bytes()
        source[name] = {'original_sha256': sha256(old).hexdigest(),
                        'current_sha256': sha256(current).hexdigest(),
                        'byte_identical': old == current}
    return {'scope': 'Retained forecast-interface replay and independent output reconstruction; not unified input or new model behavior.',
        'original_manifest_sha256': sha256((root/'evidence-manifest.json').read_bytes()).hexdigest(),
        'original_files_verified': sorted(checked), 'retained_source': source,
        'ordinary_full_path_lower_bounds': lower_bounds,
        'forecast_event_ids_replayed': forecast_events, 'same_candidate_comparisons': comparisons,
        'approved_order_unchanged': True, 'selected_forecast_approval': 'pending',
        'deliveries': deliveries, 'operations_due': len(planned), 'operations_delivered': len(delivered_ids),
        'operations_delayed': delayed, 'actual_cost_above_approved': settlement['consumed_cost_units'],
        'report_sha256': sha256(report).hexdigest(),
        'dependency_interpretation': 'All owners reconciled the same forecast version. Original full replay controls remain in engineering-forecast-review.md; this is not a harmless-solo composition claim.',
        'migration_contract': [
            'Preserve immutable proposals, owner reconciliation, selection and execution as distinct actions.',
            'Keep the approved order and business commitments independent from the comparison forecast.',
            'Bind queued candidates to the selected forecast version; withdrawal invalidates future use.',
            'Meter actual execution and independently reconstruct scheduled output; previews are not effects.',
            'Expose the same ordinary workflow across bindings; never seed agent messages or a solution.'
        ],
        'unified_forecast_parameter_implemented': False,
        'current_direct_rule_file_condition_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.case_dir)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    print(text)
