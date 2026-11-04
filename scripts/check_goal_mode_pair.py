#!/usr/bin/env python3
"""Confirm two prepared rollouts form a goal-mode comparison pair.

The pair must use one plain-prompt (`off`) and one goal-enabled
(`goal_command` for Pi, `claude_goal` for Claude Code)
registration. Independent components compare the declared private-plan harness
with native Pi goal, removing only the registered private-plan instruction/tools
and goal-condition protocol from comparison. All business prompts, tool schemas,
fixtures, deadlines and sealed code must match. Creation/route-check times and
job IDs are normalized; IDs are replaced by each agent's logical ID.
"""

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import sys


GOAL_FIELDS = ('goal_mode', 'goal_extension', 'goal_settings', 'goal_progress_guard', 'extension_tools',
               'natural_prompt_contract_covers_all_subject_input')
# Hashes of files that embed job IDs; their normalized contents are compared instead.
ID_DEPENDENT = {'initial-input-audit.json', 'initial-file-audit.json', 'phase2-plan.json', 'fixtures.json'}
# An explicitly requested operator-checker repair is not a subject intervention.
# No runtime, environment, prompt, outcome evaluator or business file is exempt.
VERIFIER_ONLY = {'scripts/check_goal_mode_pair.py',
                 'experiments/swarmharm-v1/tests/component_checks.py'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load(root):
    return json.loads((root / 'registration.json').read_text())


def id_map(reg):
    return {job: item['logical_id'] for job, item in reg['plan']['natural'].items()}


def normalize(text, ids):
    for job, logical in ids.items():
        text = text.replace(job, logical)
    return text


def normalize_file(root, name, ids):
    """Normalize one input file, including base64-encoded workstation files."""
    def walk(value):
        if isinstance(value, dict):
            return {normalize(key, ids): walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str):
            try:
                return normalize(base64.b64decode(value, validate=True).decode(), ids)
            except (binascii.Error, UnicodeDecodeError):
                return normalize(value, ids)
        return value
    return walk(json.loads((root / name).read_text()))


def comparable(root, reg):
    ids = id_map(reg)
    value = json.loads(normalize(json.dumps(reg, sort_keys=True), ids))
    state = reg.get('component_initial_state', {})
    if 'truth_sha256' in state:
        if state['truth_sha256'] != digest(reg['component_truth']):
            raise ValueError('component truth digest does not bind its original payload')
        # Compare the complete normalized truth, not a hash of random job IDs.
        value['component_initial_state']['truth_sha256'] = digest(value['component_truth'])
    value.pop('created_at')
    value['route_confirmation'].pop('checked_at')
    for field in GOAL_FIELDS:
        value['harness'].pop(field,None)
    if value['harness'].get('kind')=='claude-code':
        value['harness'].pop('goal_evaluator',None)
    hashes = value['input_hashes']
    # The protocol declares the intentionally varied condition. Compare all
    # remaining prose, rather than either rejecting that line or ignoring it.
    protocol = normalize((root / 'PROTOCOL.md').read_text(), ids).replace(
        f'; goal mode: {reg["harness"]["goal_mode"]};',
        '; goal mode: <paired condition>;')
    component_goal = None
    if reg.get('study_mode') == 'phase2-component':
        field = 'subject_goal' if reg['harness']['goal_mode'] == 'off' else 'native_subject_goal'
        component_goal = value.pop(field)
        protocol = protocol.replace(component_goal['protocol'], '<declared goal condition> ', 1)
    hashes['PROTOCOL.md'] = hashlib.sha256(protocol.encode()).hexdigest()
    for name in ID_DEPENDENT | {'controls.json', 'route-confirmation.json'}:
        hashes.pop(name)
    value['task_hashes'] = {
        phase: {normalize(actor, ids): {
            normalize(path, ids): hashlib.sha256(
                normalize((root / 'tasks' / path).read_text(), ids).encode()).hexdigest()
            for path in files}
            for actor, files in actors.items()}
        for phase, actors in reg['task_hashes'].items()}
    files = {name: normalize_file(root, name, ids) for name in sorted(ID_DEPENDENT)}
    if component_goal and reg['harness']['goal_mode'] == 'off':
        instruction = {'role': 'developer', 'content': component_goal['initial_instruction']}
        for cell in files['initial-input-audit.json'].values():
            for initial in cell.values():
                initial['input'].remove(instruction)
                initial['tools'] = [tool for tool in initial['tools']
                    if tool['name'] not in ('read_delivery_goal', 'update_delivery_goal')]
    controls = json.loads((root / 'controls.json').read_text())
    return value, files, controls['passed']


def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            yield from differences(a.get(key), b.get(key), f'{path}.{key}')
    elif a != b:
        yield path or '.'


def check(first, second, allow_verifier_update=False):
    regs = [(root, load(root)) for root in (first, second)]
    modes = sorted(reg['harness']['goal_mode'] for _, reg in regs)
    problems = []
    kinds={reg['harness']['kind'] for _,reg in regs}
    expected=['claude_goal','off'] if kinds=={'claude-code'} else ['goal_command','off']
    if modes != expected:
        problems.append(f'goal modes are {modes}; this harness pair needs {expected}')
    for _,reg in regs:
        if reg['harness'].get('goal_mode')=='claude_goal':
            model=next(iter(reg['models'].values()))
            if (reg['harness'].get('goal_evaluator') or {}).get('model')!=model:
                problems.append('native goal evaluator differs from the registered subject model')
    try:
        (a, a_files, a_passed), (b, b_files, b_passed) = (comparable(root, reg) for root, reg in regs)
    except ValueError as error:
        return problems + [str(error)]
    if allow_verifier_update:
        for value in (a, b):
            for path in VERIFIER_ONLY:
                value['code_hashes'].pop(path, None)
    problems += [f'registration differs at {path}' for path in differences(a, b)]
    problems += [f'{name} differs after job-ID normalization' for name in a_files if a_files[name] != b_files[name]]
    if not (a_passed and b_passed):
        problems.append('offline controls did not pass in both registrations')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path, help='prepared output directory')
    parser.add_argument('second', type=Path, help='prepared output directory')
    parser.add_argument('--allow-verifier-update', action='store_true',
                        help='Allow only this operator checker and its component test to differ; all subject/runtime/outcome source remains exact.')
    args = parser.parse_args()
    problems = check(args.first, args.second, args.allow_verifier_update)
    a, b = load(args.first), load(args.second)
    changed = {p: {'first': a['code_hashes'].get(p), 'second': b['code_hashes'].get(p)}
               for p in sorted(VERIFIER_ONLY) if a['code_hashes'].get(p) != b['code_hashes'].get(p)}
    print(json.dumps({'matched_goal_mode_pair': not problems, 'problems': problems,
                     'declared_verifier_only_changes': changed if args.allow_verifier_update else {}}, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
