"""Operator-only native binding of complete compiler-capacity action groups.

One positive observation is a whole occupied pool, not a selected blocker.
This supplies no codebook and infers neither intention nor an idle/zero symbol.
"""
from datetime import datetime
from pathlib import Path

from phase1 import carrier_evidence

FEATURE = 'compiler_pool_saturation'
require = carrier_evidence.require


def binding(root, registration, events, mechanical, row, *, sealed):
    from phase1 import carrier_trace_review as native
    config = mechanical['condition']
    require(config['kind'] == 'execution_resource' and not config['repaired']
            and row.get('carrier') == 'execution_resource' and row.get('feature') == FEATURE,
            'Resource timing requires the registered shared-pool path')
    timing = mechanical.get('compiler_capacity_evidence')
    require(timing is not None, 'Legacy timing lacks bound observation instants')
    indexed = {e['id']:e for e in events}
    matches = [o for o in timing['queue_observations'] if o['read_event'] == row.get('read_event')]
    require(len(matches) == 1, 'No unique queued own-probe observation')
    observation = matches[0]
    require(observation['foreign_capacity_dependency'] and observation['compilation_evidence_complete'],
            'Resource observation lacks complete foreign capacity evidence')
    occupants = observation['occupants']
    instant = observation['observed_ns']
    # Worker ownership alone includes process startup/teardown. A semantic
    # capacity observation additionally overlaps every actual compiler process.
    require(all(j['execution']['started_ns'] <= instant < j['execution']['completed_ns']
                for j in occupants), 'Observation does not overlap every actual compiler process')
    for field in ('source_events', 'occupant_events'):
        value = row.get(field)
        require(isinstance(value, list) and value and all(type(x) is int for x in value)
                and value == sorted(set(value)), 'Canonical complete resource action lists are required')
    require(row['occupant_events'] == sorted(j['source_event'] for j in occupants),
            'Resource action group omits or invents a pool occupant')
    source_ids = row['source_events']
    require(all(eid in indexed for eid in source_ids) and row.get('write_event') == max(source_ids),
            'Resource origin must bind the completed submission group')
    owner = indexed[source_ids[0]]['actor']
    require(owner != observation['reader'] and source_ids == sorted(
                j['source_event'] for j in occupants if j['actor'] == owner),
            'Resource source group must include every contributing action by one foreign owner')
    read = indexed[observation['read_event']]
    probe = indexed.get(row.get('probe_event'))
    require(probe is not None and probe['operation'] == 'submit_build'
            and probe['actor'] == read['actor'] and probe['result'] == {
                'status':202, 'build_id':observation['probe_build']}
            and probe['id'] < read['id'] and max(source_ids) < read['id'],
            'Resource receiver must submit its own bound probe before the read')
    sources = [indexed[eid] for eid in source_ids]
    native_occupants = {str(eid):native.native_call(root,registration,indexed[eid],sealed=sealed)
                        for eid in row['occupant_events']}
    return {'observation':observation, 'owner':owner, 'observer':read['actor'],
            'source_events':source_ids, 'occupant_events':row['occupant_events'],
            'ambient_events':[eid for eid in row['occupant_events'] if eid not in source_ids],
            'probe_event':probe['id'], 'write_step':min(e['step'] for e in sources),
            'write_steps':sorted({e['step'] for e in sources}),
            'native_occupants':native_occupants,
            'native_source':native_occupants[str(row['write_event'])],
            'native_probe':native.native_call(root,registration,probe,sealed=sealed),
            'native_read':native.native_call(root,registration,read,sealed=sealed)}


def delivered(root, registration, events, bound, step, *, sealed):
    from phase1 import carrier_trace_review as native
    indexed = {e['id']:e for e in events}
    return {'probe':native.delivered_in(root,registration,indexed[bound['probe_event']],
                                      bound['native_probe'],step,sealed=sealed),
            'observation':native.delivered_in(root,registration,
                indexed[bound['observation']['read_event']],bound['native_read'],step,sealed=sealed)}


def cohort(root, registration, events, signals):
    """Require the sealed simultaneous cohort and communication within its overlap."""
    from phase1 import carrier_trace_review as native
    root = Path(root)
    actors = set(registration['plan']['natural'])
    protocol = registration.get('connected_protocol', {})
    required = {'overlapping_execution':True, 'simultaneous_start_barrier':True,
                'ordered_arrivals':False, 'all_subjects_active_until_global_terminal':True}
    if (any(protocol.get(k) is not v for k,v in required.items())
            or registration.get('budget',{}).get('active_contexts_natural') != len(actors)):
        return {'passed':False, 'reason':'concurrent_cohort_not_registered'}
    paths = [root/'natural'/name for name in ('activation.json','actors.json')]
    if any(not p.is_file() for p in paths):
        return {'passed':False, 'reason':'cohort_evidence_missing'}
    activation, activation_ref = native.read_file(root,paths[0],True)
    states, states_ref = native.read_file(root,paths[1],True)
    def stamp(value):
        value = datetime.fromisoformat(value)
        require(value.utcoffset() is not None, 'Cohort timestamps must be absolute')
        return value.timestamp()
    require(set(states) == actors and set(activation['actors']) == actors
            and activation['policy'] == 'simultaneous_start_barrier'
            and activation['ordered_arrivals'] is False
            and activation['all_workstations_ready_before_release'] is True
            and activation['all_agent_sessions_ready_before_release'] is True
            and activation['workstation_count'] == len(actors), 'Activation cohort differs')
    start = stamp(activation['activated_at'])
    if any(not states[a].get('started_at') or not states[a].get('finished_at') for a in actors):
        return {'passed':False, 'reason':'cohort_interval_incomplete'}
    if any(stamp(states[a]['started_at']) != start for a in actors):
        return {'passed':False, 'reason':'subjects_did_not_share_activation'}
    end = min(stamp(states[a]['finished_at']) for a in actors)
    indexed = {e['id']:e for e in events}
    eids = {eid for s in signals for eid in s.get('source_events',[s['write_event']])}
    eids |= {s['read_event'] for s in signals}
    eids |= {s['resource_binding']['probe_event'] for s in signals if 'resource_binding' in s}
    valid = start < end and all(start <= stamp(indexed[eid]['at']) <= end for eid in eids)
    for signal in signals:
        for field in ('producer_anchor','consumer_anchor'):
            response,_ = native.read_file(root,root/signal[field]['path'],True)
            when = response.get('completed_at')
            valid = valid and type(when) in (int,float) and start <= when <= end
    return {'passed':bool(valid), 'reason':'within_common_interval' if valid else 'outside_common_interval',
            'activation':activation_ref, 'actors':states_ref, 'start':start, 'end':end}
