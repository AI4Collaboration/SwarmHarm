"""The cross-desk contrast changes mail circulation while holding business decisions fixed."""
import base64
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, unified_delivery as reporting, world_config


class DeskUpliftChecks(unittest.TestCase):
    def test_only_mail_circulation_changes(self):
        root = Path(__file__).resolve().parents[1] / 'configs'
        outcomes = []
        for arm in ('within', 'across'):
            world = world_config.normalize(json.loads((root / f'desk-uplift-{arm}.json').read_text()), preset='resource')
            config, _ = world_config.components(world)
            plan = reporting.plan_for(reporting.cohort.actor_ids(4), domain='knowledge-work')
            for row in plan.values():
                row.update(binding_preset='resource', world_config=world, delivery_config=config,
                           continuous_workflow=True, native_record_harness='codex', work_entries_only=True)
            claim = 'coordinated_adverse_outcomes'
            contract = delivery_paths.audit(plan, target_claim=claim)
            delivery_paths.require_challenge(contract, 'resource', claim)
            with self.assertRaises(ValueError):
                delivery_paths.require_challenge({**contract, 'desk_capacity': {}}, 'resource', claim)
            subjects = world_config.subject_inputs(plan)
            probe = delivery_paths.Probe(plan, initial_files=subjects['initial_files'])
            flow = probe.flow
            flow.world.shared = {}
            for actor in plan:
                self.assertEqual(probe.call(actor, 'read_delivery_discussion')['messages'], [])
            for actor, row in plan.items():
                self.assertEqual(probe.call(actor, 'post_delivery_message', text=row['account'], reply_to=None)['status'], 201)
            desks = [{'Northline', 'Meridian'}, {'Aster', 'Harbor'}]
            for actor, row in plan.items():
                account = row['account']
                expected = set.union(*desks) if arm == 'across' else next(team for team in desks if account in team)
                inbox = probe.call(actor, 'read_delivery_discussion')['messages']
                self.assertEqual({note['text'] for note in inbox}, expected)
                files = subjects['initial_files'][actor]
                directory = json.loads(base64.b64decode(files.pop('/workspace/reporting-records.json')))
                self.assertEqual(set(directory.pop('circulation')), expected)
                files['directory_without_circulation'] = directory
            for actor, row in plan.items():
                probe.upload(actor)
                probe.stage(actor, reporting.ITEMS, [row['account']]*2 + [reporting.RESERVE]*2)
                probe.execute(actor)
                self.assertEqual(probe.call(actor, 'release_delivery', revision=flow.plans[actor]['revision'])['status'], 201)
            views = {a: [probe.call(a, op) for op in ('read_dispatch_budget','check_delivery')] for a in plan}
            with TemporaryDirectory() as temp:
                flow.world.operator = Path(temp)
                flow.finalize()
                output = Path(temp) / 'delivery-files'
                with sqlite3.connect(output / 'operations-execution.sqlite') as db:
                    late = list(db.execute("select reference from jobs where kind='operations' and slot is null order by reference"))
                self.assertEqual(len(late), 4)
                files = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*.csv')}
            outcomes.append((subjects, views, files, late))
        self.assertEqual(*outcomes)
