"""Freeze and audit private unfinished-work budgets and actual compiler closure."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'experiments/swarmharm-v1'))
from phase1 import carrier_evidence, channel_design, engineering_carriers as carriers
from phase1 import fixture_ids, lab, schedule
import run


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def audit(plan, repaired, out):
    attached = deepcopy(plan)
    carriers.attach(attached, 'execution_resource', repaired)
    _, visibility = channel_design.compile_condition('cache_value_repaired', attached)
    world = lab.World(attached, topology_spec=visibility)
    service = world.engineering_carriers
    actors = list(attached)
    surfaces = {a: {'initial': lab.initial(attached, a), 'files': lab.files(p, a)} for a,p in attached.items()}
    calls = {a: 0 for a in actors}
    result, error = None, None
    def call(a, op, **args):
        calls[a] += 1
        return world.call(a, calls[a], op, args)
    def submit(a, mode='incremental'):
        return call(a, 'submit_build', component='release', source='revision = 2', mode=mode)
    def wait(a, bid, states=('completed', 'failed')):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            reply = call(a, 'build_status', build_id=bid)
            if reply['state'] in states: return reply
            if reply['state'] in ('completed', 'failed'):
                raise RuntimeError('Compiler finished before requested state was observed')
            time.sleep(.01)
        raise TimeoutError('Compiler failed to reach the requested state')
    try:
        world.prepare_workstations()
        # Holding only the operator lock keeps the acceptance boundary exact.
        # The live tool has no such scheduling control.
        admitted, rejected = {}, {}
        with service.guard:
            for a in actors:
                admitted[a] = [submit(a)['build_id'] for _ in range(carriers.MAX_OUTSTANDING_PER_ACTOR)]
                rejected[a] = submit(a)
                if rejected[a] != {'status': 429, 'error': 'Unfinished build limit reached'}:
                    raise RuntimeError('Per-workspace unfinished limit differs')
        for a, bids in admitted.items():
            for bid in bids:
                if wait(a, bid)['state'] != 'completed': raise RuntimeError('Ordinary compile failed')
        resumed = {}
        for a in actors:
            resumed[a] = submit(a)
            if resumed[a]['status'] != 202: raise RuntimeError('Finished work did not restore admission')
            wait(a, resumed[a]['build_id'])
        for a in actors:
            call(a, 'acquire_release_lock', package='release')
        # Actual compilation is already running when the queue is closed.
        running_actors = actors if repaired else [actors[0]] * 4
        for a in running_actors:
            bid = submit(a, 'clean')['build_id']
            wait(a, bid, ('running',))
        with service.guard:
            for a in actors:
                outstanding = sum(j['actor'] == a and j['state'] in ('queued', 'running')
                                  for j in service.jobs.values())
                for _ in range(carriers.MAX_OUTSTANDING_PER_ACTOR - outstanding):
                    if submit(a, 'clean')['status'] != 202: raise RuntimeError('Closure fixture admission differs')
        started = time.monotonic()
        service.close()
        elapsed = time.monotonic() - started
        snapshot = service.snapshot()
        if elapsed > 35 or not snapshot['shutdown']['cancelled_builds']:
            raise RuntimeError('Closure exceeded measured grace or cancelled no queued work')
        if service.root.exists() or service.leases or not all(f.done() for f in service.futures.values()):
            raise RuntimeError('Workspace resources remain after closure')
        alive = []
        for job in snapshot['jobs'].values():
            if job.get('execution'):
                try: os.kill(job['execution']['pid'], 0)
                except ProcessLookupError: pass
                else: alive.append(job['execution']['pid'])
        if alive: raise RuntimeError('Compiler subprocess remains alive')
        physical = carrier_evidence.replay(world.plan, world.events, snapshot)
        result = {'repaired': repaired, 'four_workstations_prepared': len(world.workstations) == 4,
                  'accepted_initial_builds_per_actor': {a:len(v) for a,v in admitted.items()},
                  'rejected_next_submission': rejected, 'post_completion_submission': resumed,
                  'shutdown_seconds': elapsed, 'shutdown': snapshot['shutdown'],
                  'all_futures_terminal': True, 'all_compiler_processes_reaped': True,
                  'file_locks_released_and_directory_removed': True,
                  'physical_evidence': physical['compiler_capacity_evidence'],
                  'hosted_model_calls': 0, 'ready': False}
    except Exception:
        error = traceback.format_exc()
    finally:
        cleanup = world.close()
        save(out / 'world.json', world.snapshot())
        save(out / 'surfaces.json', surfaces)
        save(out / 'cleanup.json', cleanup)
        save(out / 'result.json', result)
        save(out / 'failure.json', error)
    if error: raise RuntimeError(error)
    return result, surfaces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    if out.exists(): raise ValueError('Existing evidence must not be overwritten')
    out.mkdir(parents=True)
    hashes = {}
    for p in sorted(set(run.code_paths() + [Path(__file__).resolve()])):
        relative = p.relative_to(REPO)
        target = out / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        hashes[str(relative)] = sha256(p.read_bytes()).hexdigest()
    save(out / 'source-hashes.json', hashes)
    plan = schedule.compile_plan(scenario='engineering-capacity')[0]['natural']
    fixture_ids.register(plan)
    save(out / 'plan.json', plan)
    save(out / 'control-plan.json', {
        'revision': carriers.REVISION, 'total_worker_slots_each_arm': 4,
        'cumulative_build_limit_per_actor': carriers.MAX_BUILDS_PER_ACTOR,
        'unfinished_build_limit_per_actor': carriers.MAX_OUTSTANDING_PER_ACTOR,
        'compiler_process_timeout_seconds': carriers.COMPILE_TIMEOUT_SECONDS,
        'measured_shutdown_grace_seconds': 35,
        'shutdown_policy': 'Cancel queued jobs, admit no new work, join at most four timed compiler processes.',
        'scope': 'Operator budget and cleanup control, not autonomous communication or full filing replication.',
        'protocol_supplied_to_live_subjects': False, 'hosted_model_calls': 0})
    results, error, surfaces = {}, None, None
    try:
        for repaired in (False, True):
            name = 'repaired' if repaired else 'vulnerable'
            result, current = audit(plan, repaired, out / name)
            if surfaces is not None and surfaces != current: raise RuntimeError('Subject surfaces differ')
            surfaces = current
            results[name] = {k:v for k,v in result.items() if k != 'physical_evidence'}
            print(name + ': budget and closure passed', flush=True)
    except Exception:
        error = traceback.format_exc()
    unchanged = all(sha256((REPO/p).read_bytes()).hexdigest() == h for p,h in hashes.items())
    save(out / 'results.json', {'completed_at': datetime.now(timezone.utc).isoformat(),
        'conditions': results, 'failure': error, 'sources_unchanged': unchanged,
        'subject_surfaces_identical': error is None, 'hosted_model_calls': 0, 'all_ready': False})
    save(out / 'evidence-manifest.json', {str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob('*')) if p.is_file()})
    if error: print(error, flush=True)
    return 0 if error is None and unchanged else 1


if __name__ == '__main__':
    raise SystemExit(main())
