"""Guarded native bridge for the offline release-delivery prototype.

Connected to the unified runner and review, with registration still guarded.
Only fixed-response scripts have been tested; these are not model results or
formal freeze verification. Uploads bind a committed actor workstation
snapshot; replay does not rerun shell commands or model actions.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from atomic import atomic_json
from phase2 import engineering_release_delivery_candidate as desk_module
from phase2.build_record.unified_bridge import UnifiedBuildBridge


def committed_shell(events, actor, private, operator):
    """Require the latest actor workspace snapshot to be a completed tool commit.

    This is only an operator-journal check; native/session and evidence-manifest
    validation remain separate prerequisites for any published result.
    """
    shells = [event for event in events if event.get('actor') == actor
              and event.get('operation') == 'bash' and 'private_files' in event]
    if not shells:
        raise ValueError('No committed shell workspace snapshot')
    event = shells[-1]
    result = event.get('result', {})
    if (result.get('status') != 200 or type(result.get('exit_code')) is not int
            or result.get('output_truncated') is not False or result.get('limit') is not None
            or event.get('private_files') != private):
        raise ValueError('Shell workspace snapshot is incomplete or differs')
    path = Path(operator) / 'tool-commits' / f"{event['id']:06d}.json"
    if path.is_symlink() or not path.is_file() or json.loads(path.read_text()).get('event') != event:
        raise ValueError('Shell snapshot tool commit differs')
    return event['id']


class ReleaseDeliveryBridge(UnifiedBuildBridge):
    """Expose ordinary delivery operations using the actor's committed files."""
    continuous_workflow = True

    def __init__(self, world, accounts, *, receipt_binding=False):
        self.world = world
        self.accounts = dict(accounts)
        self.root = Path(world.operator) / 'release-delivery-service'
        self.root.mkdir(parents=True, exist_ok=False)
        self.desk = desk_module.ReleaseDesk(self.root / 'desk', accounts, receipt_binding=receipt_binding)
        self.calls = []
        (self.root / 'actor-events.jsonl').touch()
        (self.root / 'upload-inputs').mkdir()
        self.actors = list(accounts)
        self.activated = True

    @classmethod
    def from_plan(cls, world, plan, frozen):
        from phase2 import unified_delivery, work_files
        config = unified_delivery.config_for(plan)
        if frozen != unified_delivery.initial_state(plan) or frozen.get('live_partner_source_arrivals') is not False:
            raise ValueError('Frozen release-delivery input differs')
        if config.get('workstation_processes', 'tool_scoped') != 'tool_scoped':
            raise ValueError('Release delivery requires tool-scoped workstation execution')
        accounts = {actor: row['account'] for actor, row in plan.items()}
        obj = cls(world, accounts, receipt_binding=unified_delivery.bindings_for(plan)['evidence_binding'] != 'register')
        obj.plan, obj.config = deepcopy(plan), config
        obj.surface = None
        obj.initial_private = unified_delivery.initial_files(plan)
        obj.registration = {'schema': 'release-delivery-guarded-v1', 'accounts': accounts}
        world.shared_directories = [work_files.ROOT]
        world.mutable_shared_root = work_files.ROOT
        world.shared_record_validator = lambda actor, path, data, records: work_files.valid(path, data)
        world.shared_record_visibility = lambda actor, row: True
        obj.activated = False
        return obj

    def complete(self, actor):
        active = self.desk.active[self.accounts[actor]]
        return active is not None and active['scope'] == 'complete'

    def business_state(self, actor):
        account = self.accounts[actor]
        return {'account': account, 'records': deepcopy(self.desk.records[account]),
                'files': sorted(path.name for path in (self.desk.root / 'repository' / account).glob('*.zip')),
                'active_release': deepcopy(self.desk.active[account])}

    def outcome(self, actor):
        return {'complete': self.complete(actor), 'account': self.accounts[actor]}

    def snapshot(self):
        return {'activated': self.activated, 'actors': {actor: self.business_state(actor) for actor in self.actors},
                'action_count': len(self.calls)}

    def observed_calendar_revision(self, operation, result):
        return None

    def observed_calendar_components(self, operation, result):
        return {}

    def finalize(self):
        observation = inspect_bridge(self.root, {'events': self.world.events}, self.accounts,
                                     self.initial_private, receipt_binding=self.desk.receipt_binding)
        target = Path(self.world.operator) / 'release-delivery-observation.json'
        if target.exists():
            raise FileExistsError('Refusing to replace release observation')
        result = {'state': self.snapshot(), 'mechanical_observation': observation,
                  'scope': 'Service and committed workspace replay only; native/ATIF not established.'}
        atomic_json(target, result)
        return result

    def call(self, actor, step, operation, arguments, *, elapsed_seconds=None):
        if not self.activated:
            raise ValueError('The registered input is not active')
        if actor not in self.accounts:
            raise ValueError('Unknown actor')
        if operation not in {row['name'] for row in self.definitions()}:
            raise ValueError('Unsupported delivery operation')
        if (actor in getattr(self.world, 'running_shells', set())
                or getattr(self.world, 'observation_error', None) is not None
                or actor not in self.world.private):
            raise ValueError('Workstation snapshot is not committed')
        snap = None
        if operation == 'upload_package' and set(arguments) == {'locale'}:
            locale = arguments['locale']
            if locale in desk_module.LOCALES:
                path = f'/workspace/{locale}-{desk_module.REVISION}.zip'
                encoded = self.world.private.get(actor, {}).get(path)
                target = self.desk.root / 'workstations' / self.accounts[actor] / Path(path).name
                if encoded is not None:
                    snapshot_event = committed_shell(self.world.events, actor, self.world.private[actor], self.world.operator)
                    try:
                        body = base64.b64decode(encoded, validate=True)
                    except (ValueError, TypeError) as exc:
                        raise ValueError('Invalid committed workstation snapshot') from exc
                    if len(body) > 2_000_000:
                        raise ValueError('Workstation input exceeds snapshot limit')
                # Never reuse a prior tool snapshot when the actor removed the file.
                target.unlink(missing_ok=True)
                if encoded is not None:
                    digest = sha256(body).hexdigest()
                    archive = self.root / 'upload-inputs' / f'{len(self.calls)+1:06d}.zip'
                    with archive.open('xb') as out:
                        out.write(body)
                    target.write_bytes(body)
                    snap = {'actor': actor, 'path': path, 'sha256': digest, 'shell_event': snapshot_event,
                            'bytes': len(body), 'archive': str(archive.relative_to(self.root))}
        result = self.desk.call(actor, operation, arguments)
        record = {'id': len(self.calls)+1, 'actor': actor, 'step': step, 'operation': operation,
                  'arguments': deepcopy(arguments), 'result': deepcopy(result),
                  'service_event_id': len(self.desk.events), 'upload_snapshot': snap}
        self.calls.append(record)
        with (self.root / 'actor-events.jsonl').open('ab') as out:
            out.write(desk_module._json(record))
        event = {'id': len(self.world.events)+1, 'actor': actor, 'step': step,
                 'operation': operation, 'arguments': deepcopy(arguments), 'result': deepcopy(result),
                 'continuation': True, 'shared_changes': [], 'authored_artifacts': [],
                 'adapter_event_id': record['id'], 'upload_snapshot': deepcopy(snap),
                 'start_group': self.world.plan[actor].get('start_group', 0)}
        self.world.events.append(event)
        target = Path(self.world.operator) / 'tool-commits' / f"{event['id']:06d}.json"
        if target.exists():
            raise FileExistsError('Refusing to replace tool evidence')
        atomic_json(target, {'event': deepcopy(event), 'summary': self.world.summary()})
        return result

    @staticmethod
    def definitions():
        # Builds are performed by the supplied script on the actual workstation.
        return [row for row in desk_module.definitions() if row['name'] != 'build_package']


def inspect_bridge(root, world, accounts, initial_private, *, receipt_binding=False):
    """Replay committed snapshots and service calls; never rerun native shells."""
    root = Path(root)
    calls = [json.loads(line) for line in (root / 'actor-events.jsonl').read_text().splitlines()]
    service_calls = [json.loads(line) for line in (root / 'desk/events.jsonl').read_text().splitlines()]
    events = [event for event in world['events'] if event.get('adapter_event_id') is not None]
    if len(calls) != len(service_calls) or [event['adapter_event_id'] for event in events] != list(range(1, len(calls)+1)):
        raise ValueError('Delivery event order differs')
    for call, event, service in zip(calls, events, service_calls):
        if (call['id'] != event['adapter_event_id'] or call['service_event_id'] != service['id']
                or call['actor'] not in accounts or service['actor'] != call['actor']
                or any(call[name] != event[name] for name in ('actor', 'step', 'operation', 'arguments', 'result', 'upload_snapshot'))
                or any(call[name] != service[name] for name in ('actor', 'operation', 'arguments', 'result'))):
            raise ValueError('Delivery service and actor events differ')
    expected_archives = {Path(row['upload_snapshot']['archive']).name for row in calls if row['upload_snapshot'] is not None}
    archive_dir = root / 'upload-inputs'
    if any(item.is_symlink() or not item.is_file() for item in archive_dir.iterdir()) or {item.name for item in archive_dir.iterdir()} != expected_archives:
        raise ValueError('Retained upload inputs differ from actor events')
    private = deepcopy(initial_private)
    preceding = []
    with TemporaryDirectory(prefix='release-delivery-replay-') as tmp:
        replayed = desk_module.ReleaseDesk(Path(tmp) / 'desk', accounts, receipt_binding=receipt_binding)
        by_id = {row['id']: row for row in calls}
        for event in world['events']:
            actor = event['actor']
            if event.get('operation') == 'bash' and 'private_files' in event:
                private[actor] = deepcopy(event['private_files'])
            identity = event.get('adapter_event_id')
            if identity is None:
                preceding.append(event)
                continue
            call = by_id[identity]
            if call['operation'] == 'upload_package' and set(call['arguments']) == {'locale'}:
                locale = call['arguments']['locale']
                if locale in desk_module.LOCALES:
                    path = f'/workspace/{locale}-{desk_module.REVISION}.zip'
                    encoded = private.get(actor, {}).get(path)
                    target = replayed.root / 'workstations' / accounts[actor] / Path(path).name
                    target.unlink(missing_ok=True)
                    expected = call['upload_snapshot']
                    if encoded is None:
                        if expected is not None:
                            raise ValueError('Upload lacks committed workspace bytes')
                    else:
                        try:
                            body = base64.b64decode(encoded, validate=True)
                        except (ValueError, TypeError) as exc:
                            raise ValueError('Invalid committed workstation snapshot') from exc
                        archive = root / 'upload-inputs' / f'{identity:06d}.zip'
                        shell_event = committed_shell(preceding, actor, private[actor], root.parent)
                        if (len(body) > 2_000_000 or expected != {'actor': actor, 'path': path, 'shell_event': shell_event,
                                'sha256': sha256(body).hexdigest(), 'bytes': len(body),
                                'archive': str(archive.relative_to(root))}
                                or not archive.is_file() or archive.is_symlink() or archive.read_bytes() != body):
                            raise ValueError('Upload bytes differ from committed workspace snapshot')
                        target.write_bytes(body)
            if replayed.call(actor, call['operation'], call['arguments']) != call['result']:
                raise ValueError('Delivery response differs from snapshot replay')
            preceding.append(event)
        def files(path):
            result = {}
            for item in path.rglob('*'):
                if item.is_symlink():
                    raise ValueError('Unexpected service link')
                if item.is_file():
                    result[item.relative_to(path).as_posix()] = item.read_bytes()
            return result
        if files(root / 'desk') != files(replayed.root):
            raise ValueError('Delivery service final bytes differ from replay')
    return {'service_calls_replayed': True, 'workspace_snapshots_bound': True,
            'shell_commands_reexecuted': False, 'native_or_atif_verified': False,
            'receipt_binding': receipt_binding}


def native_tool_bindings(root, registration, world):
    """Bind service actions to delivered native outputs and later session input.

    Caller must independently verify the collection manifest and tool commits.
    """
    import re
    from phase2.consolidation_adapter import bind_native
    root = Path(root)
    accounts = {actor: row['account'] for actor, row in registration['phase2']['assignments'].items()}
    service = root / 'natural/operator/release-delivery-service'
    calls = [json.loads(line) for line in (service / 'actor-events.jsonl').read_text().splitlines()]
    events = [row for row in world['events'] if row.get('adapter_event_id') is not None]
    if [row['adapter_event_id'] for row in events] != [row['id'] for row in calls]:
        raise ValueError('Delivery native event order differs')
    if any(event.get('step') != call.get('step') for event, call in zip(events, calls)):
        raise ValueError('Delivery controller step differs')
    bindings = list(bind_native(root, world, accounts, calls).values())
    by_id = {event['id']: event for event in events}
    for binding in bindings:
        event = by_id[binding['event']]
        match = re.fullmatch(r'(\d+)-tool-\d+\.json', Path(binding['tool_record']).name)
        if match is None or int(match.group(1)) != event['step']:
            raise ValueError('Delivery native turn differs from controller step')
        binding['upload_snapshot'] = event['upload_snapshot']
        binding['returned_result'] = event['result']
    return bindings


def verify_native_uploads(root, registration, world, initial_private, *, receipt_binding=False):
    """Verify archived upload bytes against delivered native shell/tool records.

    This does not verify evaluator source, registration inputs or claim semantics;
    callers must separately validate their real frozen registration and sources.
    """
    import review
    from phase2 import communication_evidence
    root = Path(root)
    if json.loads((root / 'registration.json').read_text()) != registration:
        raise ValueError('Registration differs from recorded input')
    if json.loads((root / 'natural/world.json').read_text()) != world:
        raise ValueError('World differs from recorded input')
    manifest_hash = review.verify_evidence_manifest(root)
    review.reconcile_tool_commits(root, world)
    accounts = {actor: row['account'] for actor, row in registration['phase2']['assignments'].items()}
    # ATIF is derived after the collector manifest; verify it against raw native
    # records without claiming it was part of that earlier manifest.
    from export_atif import export_actor
    for actor in accounts:
        export_actor(root, 'natural', actor)
    service = root / 'natural/operator/release-delivery-service'
    inspected = inspect_bridge(service, world, accounts, initial_private, receipt_binding=receipt_binding)
    actions = native_tool_bindings(root, registration, world)
    calls = [json.loads(line) for line in (service / 'actor-events.jsonl').read_text().splitlines()]
    shell_ids = {row['upload_snapshot']['shell_event'] for row in calls if row['upload_snapshot'] is not None}
    shell_bindings = communication_evidence.bind_events(root, world, accounts, shell_ids, refresh_atif=False)
    events = {event['id']: event for event in world['events']}
    import re
    for identity, binding in shell_bindings.items():
        event = events[identity]
        match = re.fullmatch(r'(\d+)-tool-\d+\.json', Path(binding['tool_record']).name)
        if (event['operation'] != 'bash' or match is None or int(match.group(1)) != event['step']
                or not binding['native_result_verified'] or not binding['session_input_verified']):
            raise ValueError('Committed shell lacks complete delivered native binding')
    required = {'natural/world.json', 'initial-file-audit.json',
                'natural/operator/release-delivery-service/actor-events.jsonl',
                'natural/operator/release-delivery-service/desk/events.jsonl'}
    for binding in list(shell_bindings.values()) + actions:
        required.update([binding['tool_record'], binding['world_commit'],
                         binding['following_session_input']])
        required.update(binding['native_records'])
    required.update(str((service / row['upload_snapshot']['archive']).relative_to(root))
                    for row in calls if row['upload_snapshot'] is not None)
    manifest = json.loads((root / 'evidence-manifest.json').read_text())
    if None in required or not required.issubset(manifest.get('files', {})):
        raise ValueError('Native upload evidence is absent from the manifest')
    return {'manifest_sha256': manifest_hash, 'shell_bindings': list(shell_bindings.values()),
            'action_bindings': actions, 'service_observation': inspected,
            'source_and_registration_verified': False,
            'scope': 'Native shell and service records bound to collected upload bytes; frozen source and semantics require separate review.'}


def post_rollout_receipts(root, destination):
    """Execute a synthetic recipient after collection, without changing raw evidence.

    This does not validate native or ATIF bindings; the independent review must
    do that separately. The recipient is not a customer in the model timeline.
    """
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination == root or root in destination.parents:
        raise ValueError('Post-rollout receipts must be outside the raw rollout')
    completion = json.loads((root / 'completion.json').read_text())
    if completion.get('status') not in ('collected', 'collected_with_limits'):
        raise ValueError('Post-rollout receiver requires a terminal collection')
    registration = json.loads((root / 'registration.json').read_text())
    plan = registration['phase2']['assignments']
    accounts = {actor: row['account'] for actor, row in plan.items()}
    if len(accounts) != 4 or set(accounts.values()) != set(desk_module.COMPONENTS):
        raise ValueError('Registered recipient accounts differ')
    service = root / 'natural/operator/release-delivery-service/desk'
    destination.mkdir(parents=True, exist_ok=False)
    outputs = {}
    for actor, account in accounts.items():
        outputs[actor] = desk_module.receive_to(service, account, destination / f'{account}.json')
    index = {'scope': 'post-rollout synthetic recipient execution; no model-time customer event or timestamp inferred',
             'registration_sha256': sha256((root / 'registration.json').read_bytes()).hexdigest(),
             'completion_sha256': sha256((root / 'completion.json').read_bytes()).hexdigest(),
             'world_sha256': sha256((root / 'natural/world.json').read_bytes()).hexdigest(),
             'native_or_atif_verified': False, 'outputs': outputs}
    with (destination / 'index.json').open('xb') as out:
        out.write(desk_module._json(index))
    return index


def compare_receipt_binding(root, world, accounts, initial_private):
    """Replay observed workspace snapshots and calls under the corrected binding."""
    root = Path(root)
    inspection = inspect_bridge(root, world, accounts, initial_private, receipt_binding=False)
    calls = [json.loads(line) for line in (root / 'actor-events.jsonl').read_text().splitlines()]
    with TemporaryDirectory(prefix='release-delivery-fixed-') as tmp:
        fixed = desk_module.ReleaseDesk(Path(tmp) / 'desk', accounts, receipt_binding=True)
        comparisons = []
        unchanged = True
        for call in calls:
            actor, operation, arguments = call['actor'], call['operation'], call['arguments']
            if operation == 'upload_package' and set(arguments) == {'locale'} and arguments['locale'] in desk_module.LOCALES:
                name = f"{arguments['locale']}-{desk_module.REVISION}.zip"
                target = fixed.root / 'workstations' / accounts[actor] / name
                target.unlink(missing_ok=True)
                snapshot = call['upload_snapshot']
                if snapshot is not None:
                    target.write_bytes((root / snapshot['archive']).read_bytes())
            result = fixed.call(actor, operation, arguments)
            comparisons.append({'id': call['id'], 'actor': actor, 'operation': operation,
                                'observed_result': call['result'], 'corrected_result': result,
                                'prior_service_responses_equal': unchanged})
            unchanged = unchanged and result == call['result']
        final = {account: desk_module.receive(fixed.root, account) for account in accounts.values()}
    return {'inspection': inspection, 'comparisons': comparisons, 'corrected_final': final,
            'scope': 'Same service calls and captured workstation bytes; shell commands, model decisions, shared changes and notifications are not counterfactually rerun.',
            'native_or_atif_verified': False}
