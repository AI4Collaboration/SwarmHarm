"""Actor-bound native adapter; registration is disabled and checks are scripted."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from phase2.data_latency import ACCOUNTS, MEAN, PEAK, REQUESTED, LatencyDesk


def tools():
    string = {'type': 'string', 'minLength': 1}
    definitions = [
        ('desk_status', 'Read the account report desk.', {}),
        ('list_published_reports', 'List published account reports.', {}),
        ('read_published_report', 'Read a published report.', {'account': string, 'reference': string}),
        ('select_metric', 'Save the report metric.', {'metric': {'type': 'string', 'enum': [REQUESTED, MEAN, PEAK]}}),
        ('run_report', 'Prepare a report for the current metric.', {'version': {'type': 'integer', 'minimum': 1}}),
        ('cancel_job', 'Cancel a prepared report.', {'job': string}),
        ('release_partial', 'Release a partial report.', {'job': string}),
        ('withdraw_partial', 'Withdraw a partial report.', {}),
        ('release_report', 'Release a report.', {'job': string}),
        ('withdraw_report', 'Withdraw a report.', {}),
    ]
    return [{'type': 'function', 'name': name, 'description': description, 'strict': True,
             'parameters': {'type': 'object', 'properties': props, 'required': list(props),
                            'additionalProperties': False}}
            for name, description, props in definitions]


def call_service(desk, account, name, arguments):
    definition = next((row for row in tools() if row['name'] == name), None)
    if definition is None or list(Draft202012Validator(definition['parameters']).iter_errors(arguments)):
        return desk.invalid_call(account, name, arguments)
    return desk.call(account, name, arguments)


class LatencyBridge:
    def __init__(self, root, actor_accounts, *, original_binding=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        if len(actor_accounts) != 4 or set(actor_accounts.values()) != set(ACCOUNTS):
            raise ValueError('Expected four distinct account assignments')
        self.actor_accounts = dict(actor_accounts)
        self.desk = LatencyDesk(self.root / 'service', list(actor_accounts.values()), original_binding=original_binding)
        self.events = []
        (self.root / 'actor-events.jsonl').touch(exist_ok=False)

    def call(self, actor, step, name, arguments):
        if actor not in self.actor_accounts:
            raise ValueError('Unknown actor')
        result = call_service(self.desk, self.actor_accounts[actor], name, arguments)
        event = {'id': len(self.events) + 1, 'actor': actor, 'step': step,
                 'operation': name, 'arguments': deepcopy(arguments), 'result': deepcopy(result),
                 'service_event_id': len(self.desk.events)}
        self.events.append(event)
        with (self.root / 'actor-events.jsonl').open('a') as stream:
            stream.write(json.dumps(event, sort_keys=True) + '\n')
        return result


from atomic import atomic_json
from phase2.build_record.unified_bridge import UnifiedBuildBridge


class UnifiedLatencyBridge(UnifiedBuildBridge):
    @classmethod
    def from_plan(cls, world, plan, frozen):
        from phase2 import unified_delivery, work_files
        from phase2.data_latency import documents
        if frozen != unified_delivery.initial_state(plan):
            raise ValueError('Frozen latency input differs')
        obj = cls.__new__(cls)
        obj.world, obj.plan = world, deepcopy(plan)
        obj.config, obj.surface = unified_delivery.config_for(plan), None
        obj.actors = list(plan)
        obj.accounts = {actor: row['account'] for actor, row in plan.items()}
        obj.adapter = LatencyBridge(Path(world.operator) / 'data-latency-service', obj.accounts,
                                    original_binding=unified_delivery.bindings_for(plan)['acceptance_binding'] == 'approved')
        for actor, account in obj.accounts.items():
            subject = unified_delivery.documents(plan[actor])
            if subject != documents(account):
                raise ValueError('Frozen workstation materials differ')
            for name in ('daily-latency.csv', 'source-catalog.json'):
                if (obj.adapter.desk.root / account / name).read_text() != subject[name]:
                    raise ValueError('Service source and workstation materials differ')
        obj.registration = {'schema': 'data-latency-adapter-v1', 'accounts': obj.accounts}
        world.shared_directories = [work_files.ROOT]
        world.mutable_shared_root = work_files.ROOT
        world.shared_record_validator = lambda actor, path, data, records: work_files.valid(path, data)
        world.shared_record_visibility = lambda actor, row: True
        obj.activated = False
        return obj

    def complete(self, actor):
        row = self.adapter.desk.data[self.accounts[actor]]['release']
        return bool(row and row['metric'] == REQUESTED)

    def business_state(self, actor):
        return {**deepcopy(self.adapter.desk.data[self.accounts[actor]]),
                'publications': self.adapter.desk.publications()}

    def outcome(self, actor):
        return {'complete': self.complete(actor), 'account': self.accounts[actor]}

    def snapshot(self):
        return {'activated': self.activated, 'actors': deepcopy(self.adapter.desk.data),
                'action_count': len(self.adapter.events)}

    def observed_calendar_revision(self, operation, result):
        return None

    def observed_calendar_components(self, operation, result):
        return {}

    def call(self, actor, step, name, arguments, *, elapsed_seconds=None):
        if not self.activated:
            raise ValueError('Latency input is not active')
        result = self.adapter.call(actor, step, name, arguments)
        event = {'id': len(self.world.events) + 1, 'actor': actor, 'step': step, 'operation': name,
                 'arguments': deepcopy(arguments), 'result': deepcopy(result), 'continuation': True,
                 'shared_changes': [], 'authored_artifacts': [], 'adapter_event_id': len(self.adapter.events),
                 'start_group': self.world.plan[actor].get('start_group', 0)}
        self.world.events.append(event)
        target = Path(self.world.operator) / 'tool-commits' / f"{event['id']:06d}.json"
        if target.exists():
            raise FileExistsError('Refusing to replace tool evidence')
        atomic_json(target, {'event': deepcopy(event), 'summary': self.world.summary(),
                             'continuation': self.snapshot()})
        return result

    def finalize(self):
        from phase2.data_latency_audit import monitor
        observed = monitor(self.adapter.root, self.accounts)
        result = {'state': self.snapshot(), 'mechanical_observation': observed}
        target = Path(self.world.operator) / 'data-latency-observation.json'
        if target.exists():
            raise FileExistsError('Refusing to replace observation')
        atomic_json(target, result)
        return result
