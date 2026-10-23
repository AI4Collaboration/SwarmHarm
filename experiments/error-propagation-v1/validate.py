"""Actual Docker controls and Harbor schemas; no model calls or process stops."""
import json
from pathlib import Path
import sys
import time
from harbor.models.task.config import TaskConfig
from design import advance
from grade import score
from run import native, read_state
from durability import save


root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve(); out.mkdir(parents=True, exist_ok=False)
results = []
for task in sorted(p.parent for p in root.glob('*/*/task.toml')):
    TaskConfig.model_validate_toml((task / 'task.toml').read_text())
    tag = native.image_for(task)
    ctr = native.sh('docker', 'run', '-d', '--network', 'none', '--memory', '256m', '--cpus', '1', tag, 'sleep', 'infinity').stdout.strip()
    folder = out / task.parent.name / task.name; folder.mkdir(parents=True)
    save(folder / 'container.json', {'id': ctr, 'image': tag, 'purpose': 'scripted mechanics control, no model'})
    for attempt in range(50):
        result = native.bash(ctr, 'office overview')
        if result['exit_code'] == 0: break
        time.sleep(.1)
    else: raise RuntimeError('office failed to start')
    isolation = native.bash(ctr, 'cat /var/lib/office/state.json /opt/office/seed.json /tests/truth.json /solution/solve.sh')
    assert isolation['exit_code'] != 0 and not isolation['stdout'], isolation
    truth = json.loads((task / 'tests/truth.json').read_text())
    state = read_state(ctr); assert not score(state, truth)['settled_correctly']
    amount = truth['incorrect_cents']
    result = native.bash(ctr, f'office post --item A-104 --cents {amount} --memo "Scripted wrong-amount control"')
    assert result['exit_code'] == 0
    before = read_state(ctr); bad = score(before, truth); assert bad['any_overpayment']
    native.sh('docker', 'cp', str(task / 'tests'), ctr + ':/tests')
    native.sh('docker', 'exec', ctr, 'sh', '/tests/test.sh')
    independent_bad = json.loads(native.sh('docker', 'exec', ctr, 'cat', '/logs/verifier/details.json').stdout)
    assert independent_bad == bad
    advance(before, json.loads((task / 'second-wave.json').read_text()))
    save(folder / 'connected-state.json', before)
    native.sh('docker', 'cp', str(folder / 'connected-state.json'), ctr + ':/var/lib/office/state.json')
    native.sh('docker', 'exec', ctr, 'chmod', '600', '/var/lib/office/state.json')
    after = read_state(ctr)
    assert after['ledger'] == before['ledger'] and after['audit'] == before['audit']
    delta = amount - truth['wave1']['A-104']
    new = truth['wave2']['B-208']
    result = native.bash(ctr, f'office reverse --payment PAY-1 --cents {delta} --memo "Reconciliation"\noffice post --item B-208 --cents {new} --memo "New settlement"')
    assert result['exit_code'] == 0
    native.sh('docker', 'exec', ctr, 'sh', '/tests/test.sh')
    final = read_state(ctr)
    final_grade = json.loads(native.sh('docker', 'exec', ctr, 'cat', '/logs/verifier/details.json').stdout)
    assert final_grade == score(final, truth) and final_grade['settled_correctly']
    # Deliberate grading crash removes the previously successful reward entirely.
    native.sh('docker', 'exec', ctr, 'sh', '-c', 'echo "{}" > /tests/truth.json')
    failure = native.sh('docker', 'exec', ctr, 'sh', '/tests/test.sh', check=False)
    assert failure.returncode != 0
    assert native.sh('docker', 'exec', ctr, 'test', '-e', '/logs/verifier/reward.json', check=False).returncode != 0
    grade_error = json.loads(native.sh('docker', 'exec', ctr, 'cat', '/logs/verifier/grading-status.json').stdout)
    assert grade_error['grading_status'] == 'grading_error'
    save(folder / 'state.json', final)
    results.append({'task': str(task.relative_to(root)), 'schema': 'Harbor 0.24.0', 'container': ctr,
                    'isolation': 'passed', 'wrong_amount': bad, 'connected_repair': final_grade,
                    'grading_error': grade_error, 'status': 'passed'})
    save(out / 'controls.json', results)
    print(results[-1]['task'], 'PASS', flush=True)
assert len(results) == 6
