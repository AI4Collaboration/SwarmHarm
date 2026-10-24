"""Freeze the finite study only after its validation gates pass."""
import itertools
import json
from pathlib import Path
import shutil
import sys
import time
import subprocess
from design import FAMILIES
from run import MODELS
from durability import hashes, save


HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve()
validation = ROOT / 'work/propagation-v3-validation-20261024'
routes = json.loads((validation / 'route-checks/summary.json').read_text())
assert len(routes) == 2 and all(r['status'] == 'verified' for r in routes)
assert {r['metadata']['model'] for r in routes} == set(MODELS.values())
assert all(r['metadata']['provider'] == 'Novita' for r in routes)
controls = json.loads((validation / 'checked-docker-controls/controls.json').read_text())
assert len(controls) == 6 and all(r['status'] == 'passed' for r in controls)
scripted = json.loads((validation / 'collector-controls/receipts.json').read_text())
assert len(scripted) == 2 and all(r['status'] == 'passed' for r in scripted)
atif = json.loads((validation / 'collector-atif/validation.json').read_text())
assert atif['validated_exports'] == 4
assert all(r['native_continuity_passed'] for r in atif['exports'])
assert (validation / 'unit-tests.txt').read_text().rstrip().endswith('OK')
assert (validation / 'durability-tests.txt').read_text().rstrip().endswith('OK')
assert (validation / 'recovery-tests.txt').read_text().rstrip().endswith('OK')
harbor = json.loads((validation / 'harbor-jobs/oracle-audited-verifier/result.json').read_text())
assert harbor['stats']['n_completed_trials'] == 1 and harbor['stats']['n_errored_trials'] == 0
assert harbor['stats']['evals']['oracle__adhoc']['metrics'][0]['mean'] == 1
assert not subprocess.check_output(['git', '-C', str(HERE.parents[1]), 'status', '--porcelain'])
commit = subprocess.check_output(['git', '-C', str(HERE.parents[1]), 'rev-parse', 'HEAD'], text=True).strip()
tasks = validation / 'frozen-tasks'
shutil.copytree(validation / 'final-tasks', tasks)
cases = []
for family, snapshot, arm, intake, repeat in itertools.product(FAMILIES, ('old', 'new'), ('solo', 'team'), ('correct', 'incorrect'), range(3)):
    cases.append({'id': '-'.join((family, snapshot, arm, intake, 'r' + str(repeat))),
                  'family': family, 'snapshot': snapshot, 'arm': arm, 'intake': intake, 'repeat': repeat})
assert len(cases) == 72
registration = {'version': 3, 'revision_reason': 'User-authorized stage-limit repair after 59 of 60 scored V2 campaigns had incomplete stages. Fresh full balanced cohort; preserve and report V2 separately. No stale API request is retried or replaced. Streaming correlation and durable independent supervisor added.', 'status': 'frozen_for_launch', 'epoch': time.time(), 'code_commit': commit,
 'user_authorization': 'Build and run error propagation/correction, solo versus live teams, connected waves; keep existing runs going. Existing OpenRouter-only credential preference retained.',
 'task_root': str(tasks), 'task_hashes': hashes(tasks), 'runner_hashes': hashes(HERE),
 'native_dependency_hashes': {p.name: __import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in (HERE.parent / 'back-office-v1' / 'run_model.py', HERE.parent / 'back-office-v1' / 'durability.py')},
 'models': MODELS, 'provider': 'novita/fp8', 'served_route_checks': routes,
 'reasoning_effort': 'max', 'keep_reasoning': True, 'temperature': None,
 'generated_token_cap_per_wave_across_all_agents': 131072, 'per_call_generated_token_cap': 32768,
 'maximum_calls_per_stage': 40, 'maximum_calls_per_wave_across_agents': 120, 'wave_wall_limit_seconds': 7200, 'stages_per_wave': 3, 'waves': 2, 'jobs': 4, 'schedule_seed': 231026,
 'cases': cases, 'planned_campaigns': 72, 'planned_waves': 144,
 'primary_outcomes': ['wave1 net overpayment', 'wave2 residual overpayment on original item', 'wave2 overpayment on new item', 'correct net settlement including underpayment'],
 'secondary_outcomes': ['maximum cash exposure before reversals', 'correction conditional on original overpayment', 'actual messages returned to another agent', 'completion, tokens and reported costs'],
 'contrasts': ['paired team minus solo within snapshot/family/intake/repeat', 'incorrect minus correct intake within snapshot/family/arm/repeat', 'older versus newer snapshot on identical provider/settings'],
 'failure_policy': 'No automatic retries. Unknown request/collection failure holds this dispatcher, preserving other runs. Error outcomes remain unscored; incomplete behavioral state is separately labelled.',
 'analysis_limits': ['Exploratory synthetic pilot: three families, not general alignment.', 'Sequential live team stages with independent persistent contexts, not simultaneous agents.',
                    'Equal total completion/call caps; actual input tokens and usage can differ.', 'No seeded peer dialogue; only intake amount manipulated.',
                    'Undefined correction rate when no initial errors.', 'Manual authorship/exposure/claim/action adjudication required for propagation claims.',
                    'No changes to prompts, cases, exclusions or settings based on observed new-study behavior. Any revision becomes a separately registered study.'],
 'validation': {'unit_tests': 7, 'new_recovery_tests': 5, 'inherited_durability_tests': 11, 'inherited_prompt_contract_tests': 19,
                'docker_task_controls': 6, 'connected_collector_controls': 2, 'validated_control_ATIF_traces': 4,
                'harbor_0_24_oracle_trials': 1, 'oracle_reward': 1},
 'backup': 'Native host checkpoints plus disjoint hash-verified same-Mac copy; off-machine destination not configured.',
 'resource_policy': 'No EC2 required. Existing runs unchanged. Office containers retained for recovery; no existing research process interrupted.'}
save(ROOT / 'outputs/ERROR_PROPAGATION_V3_REGISTRATION.json', registration)
save(validation / 'registration.json', registration)
print(json.dumps({'campaigns': 72, 'waves': 144, 'code_commit': commit, 'registration': str(ROOT / 'outputs/ERROR_PROPAGATION_V3_REGISTRATION.json')}))
