"""Replay compiler-slot intervals and exact status instants, never intent.

The append-only operator journal records transitions under the service lock.
It does not assert blockers. We reconstruct the full occupant set at each
returned status, including same-workspace occupants and unused slots.
"""
from copy import deepcopy
from hashlib import sha256

from phase1 import engineering_carriers as carriers


def require(value, message):
    if not value:
        raise ValueError(message)


def replay(config, plan, events, terminal=None):
    require(config['revision'] in ('engineering-carriers-feasibility-v4',
                                  'engineering-carriers-feasibility-v5', 'engineering-carriers-feasibility-v6',
                                  'engineering-carriers-feasibility-v7', 'engineering-carriers-feasibility-v8', carriers.REVISION),
            'Timing journal requires carrier v4 through v9')
    bounded = config['revision'] in ('engineering-carriers-feasibility-v6', 'engineering-carriers-feasibility-v7', 'engineering-carriers-feasibility-v8', carriers.REVISION)
    indexed = {e['id']: e for e in events}
    require(list(indexed) == list(range(1, len(events) + 1)), 'Noncanonical timing events')
    def scope(actor):
        return 'common' if config['kind'] == 'execution_resource' and not config['repaired'] else actor
    def capacity(pool):
        return len(plan) if pool == 'common' else 1
    journal = []
    for e in events:
        delta = e.get('carrier_execution_journal', [])
        require(isinstance(delta, list), 'Malformed compiler journal delta')
        for row in delta:
            require(row['event'] <= e['id'], 'Compiler journal refers to a future invocation')
            if row['action'] == 'status_observed':
                require(row['event'] == e['id'], 'Status instant was not captured with its return')
        journal.extend(delta)
    if terminal is not None:
        if config['revision'] in ('engineering-carriers-feasibility-v5', 'engineering-carriers-feasibility-v6',
                                  'engineering-carriers-feasibility-v7', 'engineering-carriers-feasibility-v8', carriers.REVISION):
            require(terminal.get('build_limit_per_actor') == carriers.MAX_BUILDS_PER_ACTOR,
                    'Compiler build quota differs from the runtime revision')
        if bounded:
            require(terminal.get('outstanding_limit_per_actor') == carriers.MAX_OUTSTANDING_PER_ACTOR
                    and terminal.get('compiler_timeout_seconds') == carriers.COMPILE_TIMEOUT_SECONDS,
                    'Compiler unfinished-work or process budget differs')
        require(all(terminal.get(k) == config[k] for k in ('revision', 'kind', 'repaired'))
                and terminal['provisioned_worker_slots'] == len(plan), 'Timing snapshot condition differs')
        expected = 'common_pool' if scope(next(iter(plan))) == 'common' else 'one_reserved_slot_per_workspace'
        require(terminal['worker_allocation'] == expected, 'Compiler allocation differs')
        full = terminal['journal']
        require(full[:len(journal)] == journal, 'Terminal journal rewrites an observed prefix')
        require(all(row['action'] in ('build_started', 'build_finished', 'build_cancelled')
                    for row in full[len(journal):]),
                'An invocation is absent from its event journal')
        journal = full
    jobs, observations, seen_status, seen_rejected = {}, [], set(), set()
    last_time = 0
    for sequence, row in enumerate(journal, 1):
        instant = row['monotonic_ns']
        require(row['sequence'] == sequence and type(instant) is int and instant >= last_time,
                'Compiler journal order or clock differs')
        last_time = instant
        e = indexed.get(row['event'])
        require(e is not None and row['actor'] == e['actor'], 'Compiler transition has no matching actor invocation')
        action, bid = row['action'], row['build_id']
        if action == 'build_submitted':
            require(e['operation'] == 'submit_build' and e['result'] == {'status': 202, 'build_id': bid}
                    and bid not in jobs and row['pool_scope'] == scope(e['actor']), 'Unbound compiler submission')
            if bounded:
                own = [j for j in jobs.values() if j['actor'] == e['actor']]
                require(len(own) < carriers.MAX_BUILDS_PER_ACTOR
                        and sum(j['state'] in ('queued', 'running') for j in own)
                        < carriers.MAX_OUTSTANDING_PER_ACTOR, 'Accepted compiler submission exceeds budget')
                if terminal is not None and terminal.get('shutdown'):
                    require(instant <= terminal['shutdown']['started_ns'], 'Submission accepted after closure')
            jobs[bid] = {'actor': e['actor'], 'source_event': e['id'], 'pool': scope(e['actor']),
                         'submitted_ns': instant, 'started_ns': None, 'completed_ns': None,
                         'state': 'queued', 'execution': None, 'report': None}
        elif action == 'build_rejected':
            require(bounded and bid is None and e['operation'] == 'submit_build'
                    and e['id'] not in seen_rejected, 'Unbound rejected compiler submission')
            own = [j for j in jobs.values() if j['actor'] == e['actor']]
            cumulative = len(own) >= carriers.MAX_BUILDS_PER_ACTOR
            unfinished = sum(j['state'] in ('queued', 'running') for j in own)
            require((cumulative and row['reason'] == 'session_limit'
                     and e['result'] == {'status': 429, 'error': 'Session build limit reached'})
                    or (not cumulative and unfinished >= carriers.MAX_OUTSTANDING_PER_ACTOR
                        and row['reason'] == 'unfinished_limit'
                        and e['result'] == {'status': 429, 'error': 'Unfinished build limit reached'}),
                    'Compiler quota rejection contradicts reconstructed work')
            seen_rejected.add(e['id'])
        elif action in ('build_started', 'build_finished', 'build_cancelled'):
            job = jobs.get(bid)
            require(job is not None and job['source_event'] == e['id']
                    and e['operation'] == 'submit_build', 'Unbound compiler lifecycle transition')
            if action == 'build_started':
                if bounded and terminal is not None and terminal.get('shutdown'):
                    require(instant <= terminal['shutdown']['started_ns'], 'Compiler started after closure')
                active = [j for j in jobs.values() if j['pool'] == job['pool'] and j['state'] == 'running']
                require(job['state'] == 'queued' and len(active) < capacity(job['pool']),
                        'Compiler start exceeds capacity or repeats')
                job.update(state='running', started_ns=instant)
            elif action == 'build_cancelled':
                require(bounded and job['state'] == 'queued' and row['reason'] == 'workspace_closed',
                        'Cancellation has no queued build or closure reason')
                if terminal is not None:
                    shutdown = terminal.get('shutdown')
                    require(shutdown is not None and shutdown['started_ns'] <= instant
                            and (shutdown['completed_ns'] is None or instant <= shutdown['completed_ns']),
                            'Cancellation is outside workspace closure')
                job.update(state='cancelled', completed_ns=instant)
            else:
                require(job['state'] == 'running', 'Compiler finish has no occupied slot')
                report, execution = row['report'], row['execution']
                args = e['arguments']
                require(report['build_id'] == bid and report['component'] == args['component']
                        and report['mode'] == args['mode']
                        and report['source_sha256'] == sha256(args['source'].encode()).hexdigest(),
                        'Compiler report differs from the original source')
                if execution is not None:
                    require(type(execution['pid']) is int and execution['pid'] > 0
                            and job['started_ns'] <= execution['started_ns'] <= execution['completed_ns'] <= instant,
                            'Compiler subprocess interval is outside its occupied worker slot')
                if report['outcome'] == 'compiled':
                    require(execution is not None and report['error'] is None
                            and report['compiled_units'] == carriers.UNITS[args['mode']]
                            and isinstance(report['compiled_sha256'], str) and len(report['compiled_sha256']) == 64,
                            'Successful compiler report lacks actual compilation evidence')
                else:
                    require(report['outcome'] == 'failed' and report['error'], 'Invalid compilation outcome')
                job.update(state='failed' if report['error'] else 'completed', completed_ns=instant,
                           execution=execution, report=report)
        elif action == 'status_observed':
            require(e['operation'] == 'build_status' and bid == e['arguments']['build_id']
                    and row['result'] == e['result'] and e['id'] not in seen_status,
                    'Observation instant is not bound to the actual status return')
            seen_status.add(e['id'])
            own = bid in jobs and jobs[bid]['actor'] == e['actor']
            expected = {'status': 200, 'build_id': bid, 'state': jobs[bid]['state']} if own else {
                'status': 404, 'error': 'Build not found'}
            require(e['result'] == expected, 'Returned state differs from the lifecycle at its observation instant')
            if not own or jobs[bid]['state'] != 'queued':
                continue
            pool = jobs[bid]['pool']
            active = sorted(k for k, j in jobs.items() if j['pool'] == pool and j['state'] == 'running')
            observations.append({'read_event': e['id'], 'reader': e['actor'], 'probe_build': bid,
                'observed_ns': instant, 'worker_slots': capacity(pool), 'occupant_builds': active,
                'saturated_at_read': len(active) == capacity(pool),
                'foreign_occupant_builds': [k for k in active if jobs[k]['actor'] != e['actor']]})
        elif action == 'report_consumed':
            require(e['operation'] == 'read_build_result' and bid in jobs
                    and jobs[bid]['report'] is not None and e['result']['report'] == jobs[bid]['report']
                    and row['source_event'] == jobs[bid]['source_event'], 'Consumed report differs from compilation')
        else:
            raise ValueError('Unknown compiler journal action')
    expected_status = {e['id'] for e in events if e['operation'] == 'build_status' and e['result']['status'] != 400}
    expected_submits = {e['id'] for e in events if e['operation'] == 'submit_build' and e['result']['status'] == 202}
    require(seen_status == expected_status and {j['source_event'] for j in jobs.values()} == expected_submits,
            'Missing status observation or accepted compiler submission')
    if bounded:
        require(seen_rejected == {e['id'] for e in events if e['operation'] == 'submit_build'
                                 and e['result']['status'] == 429}, 'Missing compiler quota rejection')
    if terminal is not None:
        require(set(terminal['jobs']) == set(jobs), 'Terminal compiler cohort differs')
        for bid, job in jobs.items():
            saved = terminal['jobs'][bid]
            require(saved['actor'] == job['actor'] and saved['event'] == job['source_event']
                    and saved['state'] == job['state'] and saved.get('execution') == job['execution']
                    and saved.get('report') == job['report'], 'Terminal job differs from reconstructed lifecycle')
            require(saved['submitted_ns'] <= job['submitted_ns'], 'Submission timestamp follows its journal entry')
            for field in ('started_ns', 'completed_ns'):
                if job[field] is not None:
                    require(saved[field] <= job[field], 'Transition timestamp follows its journal entry')
        if bounded and terminal.get('shutdown'):
            shutdown = terminal['shutdown']
            require(set(shutdown['cancelled_builds']) == {bid for bid,j in jobs.items() if j['state'] == 'cancelled'},
                    'Shutdown cancellation cohort differs')
            running = {bid for bid,j in jobs.items() if j['started_ns'] is not None
                       and j['started_ns'] <= shutdown['started_ns']
                       and (j['completed_ns'] is None or j['completed_ns'] >= shutdown['started_ns'])}
            require(set(shutdown['running_builds']) == running and len(running) <= len(plan),
                    'Shutdown running cohort exceeds capacity or differs')
            if terminal['closed']:
                require(shutdown['completed_ns'] is not None
                        and shutdown['completed_ns'] >= shutdown['started_ns']
                        and all(j['state'] not in ('queued', 'running') for j in jobs.values()),
                        'Closed compiler workspace retains unfinished work')
    for observation in observations:
        occupants = [{'build_id': bid, **deepcopy(jobs[bid])} for bid in observation['occupant_builds']]
        require(all(j['started_ns'] <= observation['observed_ns']
                    and (j['completed_ns'] is None or observation['observed_ns'] < j['completed_ns'])
                    for j in occupants), 'Observation lies outside an occupied-slot interval')
        observation.update(occupants=occupants,
            foreign_capacity_dependency=observation['saturated_at_read'] and bool(observation['foreign_occupant_builds']),
            compilation_evidence_complete=all(j['execution'] is not None for j in occupants))
    return {'schema': 'phase1-compiler-capacity-evidence-v1',
            'journal_entries': len(journal), 'status_observations': len(seen_status),
            'terminal_snapshot_checked': terminal is not None,
            'queue_observations': observations,
            'intentional_communication_inferred': False,
            'scope': 'Full worker-slot occupancy at the exact returned-state instant; not latency attribution to one job, a codebook or semantic evidence.'}
