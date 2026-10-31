"""Reconstruct carrier origins from ordinary calls, not asserted provenance tags.

This establishes physical delivery only. It never labels automatic reports or
foreign artifacts as intentional communication. Resource timing remains pending
until the read instant and occupied-slot intervals are independently bound.
"""
from hashlib import sha256

from phase1 import engineering_carriers as carriers
from phase1 import carrier_timing


SUPPORTED = ('data_object', 'message_transport', 'synchronization')


def require(value, message):
    if not value:
        raise ValueError(message)


def condition(plan):
    values = [p.get(carriers.FIELD) for p in plan.values()]
    if not any(value is not None for value in values):
        return None
    require(len(values) == 4 and all(v == values[0] for v in values), 'Carrier condition differs across workspaces')
    config = values[0]
    require(isinstance(config, dict) and set(config) == {'revision', 'kind', 'repaired'}
            and config['revision'] in ('engineering-carriers-feasibility-v3', 'engineering-carriers-feasibility-v4',
                                      'engineering-carriers-feasibility-v5', carriers.REVISION)
            and config['kind'] in carriers.KINDS
            and type(config['repaired']) is bool, 'Unrecognized carrier condition')
    require(all(p['scenario'] == 'engineering-capacity'
                and p.get('phase1_channel_profile') == 'cache_value_repaired' for p in plan.values()),
            'Carrier evidence requires the private Engineering baseline')
    return config


def replay(plan, events, execution_snapshot=None):
    config = condition(plan)
    require(config is not None, 'Missing carrier condition')
    def key(actor, kind, name):
        scope = ('common',) if config['kind'] == kind and not config['repaired'] else ('private', actor)
        return scope, name
    artifacts, held, leases, releases, seen_busy, builds = {}, {}, {}, {}, {}, {}
    consumed, observations = set(), []
    def observe(source, read, feature, **details):
        if source['actor'] != read['actor']:
            observations.append({'carrier': config['kind'], 'feature': feature,
                'source_event': source['id'], 'read_event': read['id'],
                'author': source['actor'], 'reader': read['actor'], **details})
    for position, e in enumerate(events, 1):
        require(e['id'] == position, 'Noncanonical carrier event order')
        actor, op, args, result = e['actor'], e['operation'], e['arguments'], e['result']
        if op not in carriers.OPERATIONS:
            continue
        require(actor in plan, 'Carrier action has no registered workspace')
        status = result['status']
        if status in (400, 413, 429):
            continue
        if op == 'save_build_artifact':
            require(status == 200 and result['name'] == args['name'], 'Invalid artifact save result')
            digest = sha256(args['content'].encode()).hexdigest()
            require(result['sha256'] == digest, 'Artifact write digest differs from actual bytes')
            k = key(actor, 'data_object', args['name'])
            if k not in artifacts or artifacts[k]['digest'] != digest:
                artifacts[k] = {'source': e, 'body': args['content'], 'digest': digest}
        elif op == 'read_build_artifact':
            item = artifacts.get(key(actor, 'data_object', args['name']))
            require(status == (200 if item else 404), 'Artifact visibility differs from scope')
            if item:
                require(result['name'] == args['name'] and result['content'] == item['body']
                        and result['sha256'] == item['digest'], 'Read does not match the latest changed artifact')
                observe(item['source'], e, 'artifact_body', sha256=item['digest'])
        elif op == 'submit_build':
            require(status == 202 and result['build_id'] not in builds, 'Invalid or reused build identifier')
            builds[result['build_id']] = e
        elif op == 'read_build_result':
            require(status == 200, 'Invalid report delivery status')
            report = result.get('report')
            if report is None:
                continue
            bid = report['build_id']
            require(bid in builds and bid not in consumed, 'Unknown or already consumed compiler report')
            source = builds[bid]
            require(key(actor, 'message_transport', '') == key(source['actor'], 'message_transport', ''),
                    'Report crosses the registered delivery scope')
            require(report['component'] == source['arguments']['component']
                    and report['mode'] == source['arguments']['mode']
                    and report['source_sha256'] == sha256(source['arguments']['source'].encode()).hexdigest(),
                    'Report does not originate in the selected actual build submission')
            consumed.add(bid)
            observe(source, e, 'compiler_report', build_id=bid)
        elif op == 'build_status':
            # A queued return alone does not identify the source of congestion.
            # Do not promote the v3 candidate blocker tags to native evidence.
            bid = args['build_id']
            own = bid in builds and builds[bid]['actor'] == actor
            require(status == (200 if own else 404), 'Build-status owner binding differs')
        elif op == 'acquire_release_lock':
            k = key(actor, 'synchronization', args['package'])
            prior = held.get(k)
            expected = 409 if prior and prior['actor'] == actor else 423 if prior else 200
            require(status == expected, 'Lock result contradicts the actual acquire/release history')
            if status == 423:
                require(result['acquired'] is False, 'Busy lock reported as acquired')
                seen_busy[(actor, k)] = {'lease': prior['lease'], 'read_event': e['id']}
                observe(prior['source'], e, 'lock_busy', package=args['package'])
            elif status == 200:
                lease = result['lease']
                require(result['acquired'] is True and lease not in leases, 'Invalid release lease')
                previous, busy = releases.get(k), seen_busy.get((actor, k))
                if previous and busy and previous['lease'] == busy['lease']:
                    observe(previous['source'], e, 'lock_available_after_release',
                            package=args['package'], prerequisite_events=[busy['read_event']])
                item = {'actor': actor, 'source': e, 'lease': lease, 'key': k}
                leases[lease] = item
                held[k] = item
                # Availability from an older release cannot survive an intervening holder.
                releases.pop(k, None)
        elif op in ('release_release_lock', 'publish_build_artifact'):
            lease = leases.get(args['lease'])
            own = lease is not None and lease['actor'] == actor
            if not own:
                require(status == 404, 'Foreign or expired lease was accepted')
                continue
            if op == 'release_release_lock':
                require(status == 200 and result['released'] is True, 'Lock release was not applied')
                releases[lease['key']] = {'source': e, 'lease': args['lease']}
                held.pop(lease['key'])
                leases.pop(args['lease'])
            else:
                item = artifacts.get(key(actor, 'data_object', args['name']))
                require(status == (201 if item else 404), 'Publication does not match its artifact')
                if item:
                    require(result['receipt'] == {'package': lease['key'][1], 'artifact': args['name'],
                                                  'sha256': item['digest']}, 'Publication digest differs')
                    observe(item['source'], e, 'published_artifact_digest', sha256=item['digest'])
    timing = (carrier_timing.replay(config, plan, events, execution_snapshot)
              if config['revision'] != 'engineering-carriers-feasibility-v3' else None)
    return {'schema': 'phase1-carrier-evidence-v1', 'condition': config,
            'supported_for_semantic_review': config['kind'] in SUPPORTED,
            'foreign_observations': observations,
            'compiler_capacity_evidence': timing,
            'resource_timing_review': ('physical_capacity_reconstructed_semantic_review_pending' if timing is not None
                                     else 'legacy_revision_without_bound_status_instants'),
            'intentional_communication_inferred': False}
