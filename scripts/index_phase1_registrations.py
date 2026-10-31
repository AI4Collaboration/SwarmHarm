"""Verify the frozen cache registrations and emit one publication record per rollout."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess


from audit_phase1_evidence import digest, load


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *arguments):
    return subprocess.check_output(['git', *arguments], cwd=repo)


def check_registration(repo, path, root, registration):
    relative = str(path.relative_to(repo))
    commit = git(repo, 'log', '-1', '--diff-filter=A', '--format=%H', '--', relative).decode().strip()
    require(commit and git(repo, 'show', commit + ':' + relative) == path.read_bytes() == (root / 'registration.json').read_bytes(),
            'Uncommitted or mismatched registration ' + relative)
    tree = {}
    for entry in git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0'):
        if entry:
            metadata, filename = entry.split(b'\t', 1)
            tree[filename.decode()] = metadata.split()[-1].decode()
    hashes = registration['code_hashes']
    for filename, expected in hashes.items():
        data = (root / 'code' / filename).read_bytes()
        algorithm = 'sha1' if len(tree[filename]) == 40 else 'sha256'
        blob = b'blob ' + str(len(data)).encode() + b'\0' + data
        require(hashlib.sha256(data).hexdigest() == expected
                and hashlib.new(algorithm, blob).hexdigest() == tree[filename],
                'Frozen source differs from registration or commit: ' + filename)
    index_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return commit, index_hash


def native_coverage(root, model, actors, manifest):
    trajectories = load(root / 'atif-validation.json')['trajectories']
    by_actor = {row['actor']:row for row in trajectories}
    require(set(by_actor) == set(actors) and len(trajectories) == len(actors), 'ATIF cohort differs')
    for actor, row in by_actor.items():
        replies = sorted((root/'natural'/actor/'trace').glob('????.response.json'))
        require([int(p.name[:4]) for p in replies] == list(range(1, len(replies) + 1)), 'Native step gap: ' + actor)
        for path in replies:
            require(load(path)['model'] == model and digest(path) == manifest[str(path.relative_to(root))],
                    'Native model or digest differs: ' + str(path))
        require(row['schema_version'] == 'ATIF-v1.8' and row['native_continuity_passed']
                and row['requests'] == len(replies) and row['tool_results'] == actors[actor]['tools']
                and digest(root/row['path']) == row['sha256'], 'Invalid native projection: ' + actor)
    return sum(r['requests'] for r in trajectories), sum(r['tool_results'] for r in trajectories)


def reviewed_fields(root, registration, model):
    manifest = load(root/'evidence-manifest.json')['files']
    for name, expected in manifest.items():
        require(digest(root/name) == expected, 'Collected evidence differs: ' + name)
    auxiliary = root / 'phase1-review-evidence-index.json'
    if auxiliary.is_file():
        index = load(auxiliary)
        require(index['review_complete'] and index['files'], 'Incomplete auxiliary evidence index')
        for name, expected in index['files'].items():
            path = (root/name).resolve()
            require(path.is_relative_to(root.resolve()) and digest(path) == expected,
                    'Indexed review evidence differs: ' + name)
    report = load(root/'independent-review.json')
    phase = report['phase1']
    semantic = load(root/'phase1-semantic-review.json')
    require(semantic['registration_sha256'] == digest(root/'registration.json')
            and semantic['all_native_traces_reviewed'] and not phase['manual_trace_review_required'],
            'Incomplete or unbound native review')
    actors = load(root/'natural/actors.json')
    require(set(actors) == set(registration['plan']['natural']), 'Registered cohort differs')
    responses, tools = native_coverage(root, model, actors, manifest)
    world = load(root/'natural/world.json')
    pattern = registration['phase1_channel_condition']['pattern']
    observations = [e['id'] for e in world['events'] if any(
        o['cross_boundary'] and o['pattern'] == pattern and any(s['author'] != e['actor'] for s in o['sources'])
        for o in e.get('cache_observations', []))]
    notes = load(root/'phase1-review-notes.json')
    attempts = notes.get('attempted_signaling', {})
    attempts = attempts.get('write_events', []) if isinstance(attempts, dict) else []
    actions = {e['id']:e['operation'] for e in world['events']}
    require(all(actions[i] in ('cache_store', 'cache_remove', 'cache_order', 'fetch_archive') for i in attempts),
            'Attempt refers to an unrelated event')
    evidence = ['evidence-manifest.json','controls.json','phase1-semantic-review.json','phase1-review-notes.json',
                'independent-review.json','atif-validation.json','phase1-cache-counterfactual.json',
                'phase1-pressure-native-anchors.json','phase1-resource-pair-evidence.json','matched-start-timing.json',
                'matched-control-audit.json','phase1-isolation-pair-evidence.json','phase1-peer-validation-plan.json',
                'phase1-peer-intervention-audit.json','phase1-peer-pair-evidence.json',
                'phase1-business-trace-replay.json','phase1-immediate-archive-value-reuse.json',
                'phase1-exact-source-reuse.json','phase1-native-scope-pair.json','phase1-order-overflow-control.json','phase1-native-order-workload.json',
                'phase1-contingent-filing-original.json','phase1-contingent-filing-fresh.json','phase1-review-evidence-index.json']
    result = {'review_status':'complete', 'native_actors':len(actors), 'native_responses':responses,
              'native_tool_returns':tools, 'native_continuity_verified':True,
              'actor_terminal_states':dict(Counter(a['status'] for a in actors.values())),
              'failed_transport_attempts':load(root/'completion.json')['failed_transport_attempts'],
              'filed':sum(a['submitted_reviews'] for a in world['summary']),
              'assigned':sum(a['assigned_reviews'] for a in world['summary']),
              'foreign_observation_events':observations, 'documented_attempt_write_events':attempts,
              'native_models_observed':[model], 'confirmed_signals':len(semantic['signals']),
              'confirmed_episodes':(0 if not semantic['signals'] else notes.get('confirmed_episode_count')),
              'autonomous_communication':phase['autonomous_channel_use_passed'],
              'recurrent_formation':phase['phase1_formation_passed'],
              'evidence':{f:digest(root/f) for f in evidence if (root/f).is_file()}}
    pair_path = root/'phase1-native-scope-pair.json'
    if pair_path.is_file():
        pair = load(pair_path)
        require(pair['reviewer_program_sha256'] == digest(root/'phase1-native-scope-pair.py')
                and pair['registration_pair_sha256'] == digest(root/'phase1-isolation-pair-evidence.json')
                and pair['matched_inputs_sha256'] == digest(root/'matched-control-audit.json'), 'Unbound ordinary scope pair')
        require(len(pair['arms']) == 2 and pair['arms'][1]['registration_sha256'] == digest(root/'registration.json')
                and pair['arms'][1]['world_sha256'] == manifest['natural/world.json'], 'Scope pair differs from its registration')
        result['ordinary_scope_pair'] = {
            'native_contrast_coverage':pair['native_contrast_coverage'],
            'arms':[{k:a[k] for k in ('scope','registration_sha256','native_responses','native_returns','final_active_filings',
                'delivered_primary_probe_events','delivered_feature_contrasts','equal_feature_despite_foreign_provenance',
                'confirmed_communication')} for a in pair['arms']]}
        reproduced = []
        for label in ('original','fresh'):
            path = root/('phase1-contingent-filing-' + label + '.json')
            if path.is_file():
                control = load(path)
                require(control['program_sha256'] == digest(root/'phase1-contingent-filing-reproduction.py') and
                        control['target_registration_sha256'] == pair['arms'][int(label == 'fresh')]['registration_sha256']
                        and control['source_registration_sha256'] == pair['arms'][0]['registration_sha256']
                        and control['hosted_model_calls'] == 0, 'Unbound conditional filing control')
                reproduced.append({'instance':label,'cases':[{'check':c['assigned_check'],
                    'native_event_chain':c['native_source_events'],'ordinary_filed':c['controls'][0]['normal_filings'],
                    'vulnerable_filed':c['controls'][0]['final_filings'],'repaired_filed':c['controls'][1]['final_filings']}
                    for c in control['cases']]})
        require(len(reproduced) in (0, 2), 'Incomplete conditional filing reproductions')
        if reproduced:
            result['ordinary_scope_pair']['operator_contingent_filings'] = reproduced
    overflow_path = root/'phase1-order-overflow-control.json'
    if overflow_path.is_file():
        overflow = load(overflow_path)
        require(overflow['registration_sha256'] == digest(root/'registration.json') and
                overflow['control_program_sha256'] == digest(root/'phase1-order-overflow-control.py') and
                overflow['cache_source_sha256'] == registration['code_hashes']['experiments/swarmharm-v1/phase1/cache_channels.py']
                and overflow['hosted_model_calls'] == 0, 'Unbound capacity control')
        result['order_capacity_control'] = [{k:branch[k] for k in ('profile','order_set_by_reader','capacity',
            'observed_order','cross_boundary_order','overflow_victim','authoritative_source_still_fetchable')}
            for branch in overflow['branches']]
    workload_path = root/'phase1-native-order-workload.json'
    if workload_path.is_file():
        workload = load(workload_path)
        require(workload['registration_sha256'] == digest(root/'registration.json') and
                workload['world_sha256'] == manifest['natural/world.json'] and
                workload['replay_sha256'] == digest(root/'phase1-cache-counterfactual.json') and
                workload['program_sha256'] == digest(root/'phase1-native-order-workload.py'), 'Unbound native cache workload')
        result['native_order_workload'] = {
            'capacity':workload['capacity'], 'reached_capacity':workload['any_job_reached_capacity'],
            'peak_entries_by_job':{a:v['peak_entries'] for a,v in workload['jobs'].items()},
            'order_choices_by_job':{a:v['order_choices'] for a,v in workload['jobs'].items() if v['order_choices']}}
    reuse_audit = root/'phase1-immediate-archive-value-reuse.json'
    manual_reuse = root/'phase1-exact-source-reuse.json'
    if reuse_audit.is_file():
        reuse = load(reuse_audit)
        require(reuse['registration_sha256'] == digest(root/'registration.json')
                and reuse['world_sha256'] == manifest['natural/world.json']
                and reuse['scope_replay_sha256'] == digest(root/'phase1-cache-counterfactual.json')
                and reuse['reviewer_program_sha256'] == digest(root/'phase1-immediate-archive-value-reuse.py'),
                'Unbound immediate archive reuse audit')
        result['immediate_foreign_archive_reuse'] = [{key:r[key] for key in (
            'source_event','read_event','reuse_event','operation','field','appeared_earlier_in_same_native_request')}
            for r in reuse['exact_next_action_reuse']]
        if reuse.get('consecutive_source_backed_filings') is not None:
            require(reuse['business_replay_sha256'] == digest(root/'phase1-business-trace-replay.json'),
                    'Unbound business outcome following archive reuse')
            chains = []
            for chain in reuse['consecutive_source_backed_filings']:
                ids = [chain[k] for k in ('source_event','read_event','lookup_event','fetch_event','accepted_filing_event')]
                require(ids == sorted(set(ids)) and chain['read_event'] in observations
                        and actions[ids[2]] == 'search_archive' and actions[ids[3]] == 'fetch_archive'
                        and actions[ids[4]] == 'submit_review' and world['events'][ids[4]-1].get('verified_submission') is True,
                        'Invalid source-to-filing event chain')
                chains.append({k:chain[k] for k in ('source_event','read_event','lookup_event','fetch_event',
                    'accepted_filing_event','check_id','filed_by_same_instance_repaired_control')})
            result['source_backed_filings_after_foreign_lookup'] = chains
    elif manual_reuse.is_file():
        reuse = load(manual_reuse)
        require(reuse['registration_sha256'] == digest(root/'registration.json')
                and reuse['world_sha256'] == manifest['natural/world.json'], 'Unbound manual archive reuse audit')
        result['immediate_foreign_archive_reuse'] = [
            {'source_event':reuse['source_event'],'read_event':r['read_event'],'reuse_event':r['reused_in_event'],
             'operation':actions[r['reused_in_event']],'field':r['copied_field']} for r in reuse['exact_native_reuse']]
    for row in result.get('immediate_foreign_archive_reuse', []):
        require(row['source_event'] < row['read_event'] < row['reuse_event'] and row['read_event'] in observations
                and actions[row['reuse_event']] == row['operation'], 'Reused archive value lacks a matching native action')
    control = load(root/'controls.json').get('phase1_filing_path')
    if control:
        result['operator_filing_witness'] = {
            profile:{k:branch[k] for k in ('ordinary_filed','final_filed','total_assigned','invalid_source_statuses')}
            for profile,branch in control['branches'].items()}
    if registration.get('phase1_resource_policy'):
        policy = phase['resource_intervention']
        reads = policy['exact_record_tool_returns']
        result['resource'] = {
            'status':policy['status'],
            'kernel_vcpu_by_job':{e['owner']:e['effective_vcpu'] for e in policy['enforcement'] if e['enforced']},
            'opening_terms_delivered_to_jobs':len({e['actor'] for e in reads if e['reservation'] == 'open' and e['native_delivery_step']}),
            'settled_terms_delivered_to_jobs':len({e['actor'] for e in reads if e['reservation'] == 'settled' and e['native_delivery_step']})}
        if policy['profile'] in ('peer_preservation', 'peer_ordinary'):
            result['resource']['preperiod_standard_terms_delivered_to_jobs'] = len({
                e['actor'] for e in reads if e['reservation'] == 'standard' and e['native_delivery_step']})
            result['resource']['confirmed_discovery'] = policy['discovery'] is not None
            result['resource']['intervention_delivered'] = policy['complete']
    return result


def build(repo, evidence_root):
    records = []
    seen_namespaces = set()
    tracked = git(repo, 'ls-tree', '-r', '-z', '--name-only', 'HEAD', 'experiments/swarmharm-v1/registrations')
    for filename in tracked.split(b'\0'):
        if not filename.endswith(b'/registration.json'):
            continue
        path = repo / filename.decode()
        reg = load(path)
        channel = reg.get('phase1_channel_condition') or {}
        if reg.get('study_mode') != 'phase1' or not channel.get('profile','').startswith('cache_'):
            continue
        name = re.fullmatch(r'\d{4}-\d{2}-\d{2}-(.+-r(\d+))', path.parent.name)
        require(name, 'Unknown registered cache rollout name: ' + path.parent.name)
        root = evidence_root/name[1]
        commit, source = check_registration(repo, path, root, reg)
        models = set(reg['models'].values())
        require(len(models) == 1 and len(reg['plan']['natural']) == 4, 'Unexpected study cohort')
        model = models.pop()
        terminal = load(root/'completion.json')['status'] if (root/'completion.json').is_file() else None
        row = {'rollout':int(name[2]), 'domain':reg['domain'], 'scenario':reg['scenario'],
               'channel':channel['pattern'], 'isolation':channel['isolation'], 'pressure':channel['pressure_condition'],
               'resource_profile':reg.get('phase1_resource_policy',{}).get('profile'),
               'input_revision':reg['input_revision'], 'gate_revision':reg['phase1_gate_revision'],
               'registered_model':model, 'harness':reg['harness']['kind'], 'reasoning':reg['reasoning'],
               'registration_commit':commit, 'registered_code_sha256':source,
               'sealed_code_files':len(reg['code_hashes']), 'registration':str(path.parent.relative_to(repo)),
               'registration_sha256':digest(root/'registration.json'), 'evidence_directory':root.name,
               'terminal_status':terminal, 'review_status':'pending'}
        archive = reg.get('phase1_archive_identifiers')
        if archive:
            nonces = {assignment['phase1_archive_instance'] for assignment in reg['plan']['natural'].values()}
            require(len(nonces) == 1, 'Population archive namespace differs')
            nonce = nonces.pop()
            require(isinstance(nonce, str) and re.fullmatch('[0-9a-f]{32}', nonce), 'Invalid registered archive nonce')
            namespace = hashlib.sha256(bytes.fromhex(nonce)).hexdigest()
            require(namespace == archive['namespace_sha256'] and namespace not in seen_namespaces,
                    'Unbound or reused archive namespace: ' + root.name)
            seen_namespaces.add(namespace)
            row['archive_namespace_sha256'] = namespace
        required = ('completion.json','phase1-semantic-review.json','independent-review.json','atif-validation.json')
        if all((root/n).is_file() for n in required):
            row.update(reviewed_fields(root, reg, model))
        records.append(row)
    records.sort(key=lambda r:r['rollout'])
    require(records and len({row['rollout'] for row in records}) == len(records), 'Missing or duplicate rollout IDs')
    return {'schema':'phase1-publication-registration-index-v1', 'unit':'one independent four-context rollout',
            'scope':'All standalone cache registrations in the worktree. Each revision retains its original score.',
            'evidence_layout':'Each evidence_directory is relative to the external evidence root.',
            'reading':'Foreign observations and separately documented attempted writes retain their event IDs. An empty attempt list means no attempt was separately indexed. Confirmed signals require validated encoding and interpretation. Development examples and minimum validation rollouts do not estimate behavioral rates.',
            'registrations':records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parents[1]
    parser.add_argument('--repo', type=Path, default=repo)
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--output', type=Path, help='Print JSON to stdout when omitted.')
    args = parser.parse_args()
    repo = args.repo.resolve()
    value = build(repo, (args.evidence_root or repo.parent/'eval-readiness').resolve())
    body = json.dumps(value, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(body)
    else:
        print(body, end='')
