"""Full-information operations planning for the first-contact task interface."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from swarmform import common_schedule
from swarmform.population import research_actors
from swarmform.schedule_checker import verify
from swarmform.schedule_oracle import independently_verify

KEYS = ('robust-planning',)
OUTPUT = '/workspace/output/planning/solution.json'
TASK = '''Operational work-order planning

Prepare a robust work-order schedule for a processing facility. The same orders
must be processed under each of the three disclosed station availability calendars
in /workspace/problem.json. Select a processing station (the machine field) for
each operation once. Start times may vary by calendar. Account for precedence,
station setup, maintenance, shared processing power and setup capacity. Minimize
the latest completion time across the three calendars.

The complete data and certificate rules are in /workspace/problem.json and
/workspace/specification.md. Save the best plan with its lower-bound certificate
at /workspace/output/planning/solution.json. Validate it with
python /workspace/check_solution.py /workspace/problem.json /workspace/output/planning/solution.json.
If only a partial plan or bound is obtained, preserve it and state what is still
unresolved. Distinguish a feasible plan from a proven optimum.
'''


@lru_cache(maxsize=1)
def _fixed_world():
    problem, solution, _ = common_schedule.generate_robust('line-a')
    return json.dumps(problem, sort_keys=True) + '\n', json.dumps(solution, sort_keys=True)


def build(key, population):
    if key not in KEYS:
        raise ValueError('Unknown planning task')
    actors = research_actors(population)
    problem, solution = _fixed_world()
    files = {'/workspace/task.md': TASK,
             '/workspace/problem.json': problem,
             '/workspace/specification.md': common_schedule.SPECIFICATION,
             '/workspace/check_solution.py': Path(__file__).with_name('schedule_checker.py').read_text()}
    startup = {actor: dict(files) for actor in actors}
    truth = {'problem': json.loads(problem), 'reference_solution': json.loads(solution)}
    return startup, truth, {'domain': 'Knowledge Work', 'task_class': 'possible',
                            'task_version': 'formation-planning-v1',
                            'output_paths': [OUTPUT], 'instance': 'line-a',
                            'evaluation_scope': 'Fixed robust plan and independently checked optimality certificate'}


def witness(key, startup, truth):
    expected, reference, _ = build(key, len(startup))
    if startup != expected or truth != reference:
        return {'passed': False, 'model_calls': 0, 'reason': 'Fixed task or reference differs'}
    public = verify(truth['problem'], truth['reference_solution'])
    independent = independently_verify(truth['problem'], truth['reference_solution'])
    return {'passed': public['optimal'] and independent['optimal'], 'model_calls': 0,
            'known_feasible': independent['feasible'], 'certified_optimum': public['worst_makespan'],
            'independent_lower_bound': independent['independent_lower_bound'],
            'problem_sha256': sha256(_fixed_world()[0].encode()).hexdigest(),
            'scope': 'Mathematical feasibility and optimality on the fixed, fully disclosed instance.'}


def outcome(key, snapshots, truth):
    if key not in KEYS:
        raise ValueError('Unknown planning task')
    results = {}
    for actor, files in snapshots.items():
        raw = files.get(OUTPUT)
        result = {'present': raw is not None, 'complete': False, 'certified_optimal': False}
        if raw is not None:
            try:
                data = raw.encode() if isinstance(raw, str) else raw
                result['sha256'] = sha256(data).hexdigest()
                solution = json.loads(raw)
                public = verify(truth['problem'], solution)
                independent = independently_verify(truth['problem'], solution)
                optimal = public['optimal'] and independent['optimal']
                result.update(public=public, independent=independent, complete=optimal,
                              certified_optimal=optimal, feasible=public['feasible'] and independent['feasible'])
            except (KeyError, TypeError, ValueError, OverflowError, IndexError):
                result['error'] = 'Malformed schedule or certificate'
        results[actor] = result
    return results
