"""Offline shutdown evidence checks; no model, SDK or container calls."""

from concurrent.futures import Future
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from phase1 import lab
import review
import run


class ShutdownChecks(unittest.TestCase):
    def world(self, directory):
        plan, _ = run.make_plan(4, scenario='knowledge-work')
        world = lab.World(plan['natural'], directory/'operator')
        for actor in world.plan:
            world.private[actor] = lab.files(world.plan[actor], actor)
        return world

    def pending(self, world, actor, future, index=1):
        world.running_shells.add(actor)
        args = {'command': 'printf completed > local-note.txt'}
        call = {'name': 'bash', 'arguments': json.dumps(args)}
        return (actor, {'turn': 1, 'call_id': actor+'-call'}, call, args, index)

    def test_completed_shell_keeps_snapshots_without_publication_or_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            world = self.world(directory)
            actor = next(iter(world.plan))
            future = Future()
            task = self.pending(world, actor, future)
            private = {**world.private[actor], '/workspace/local-note.txt': lab.ENCODE('completed')}
            registry = {'/registry/cache/proposal.json': lab.ENCODE('not yet committed')}
            execution = {'actor': actor, 'command': task[3]['command'], 'before': {},
                'reply': {'exit_code': 0, 'stdout': 'actual stdout', 'stderr': 'actual stderr'},
                'snapshot': {'/workspace': private, '/registry': registry},
                'snapshot_at': 'before', 'started_at': 'start', 'finished_at': 'finish'}
            future.set_result(deepcopy(execution))
            pending = {future: task}
            world.deferred_private_updates[actor] = {'/workspace/source-publication.json': lab.ENCODE('new state')}
            run.preserve_pending_shells(world, pending, directory, reason='rollout_limit')
            path = directory/actor/'trace/0001-tool-1-undelivered.json'
            record = run.load(path)
            self.assertEqual(record['execution'], execution)
            self.assertEqual(record['execution_status'], 'completed')
            self.assertEqual(record['delivery_status'], 'not_delivered')
            self.assertFalse(record['shared_commit_applied'])
            self.assertEqual(world.private[actor]['/workspace/local-note.txt'], lab.ENCODE('completed'))
            self.assertIn('/workspace/source-publication.json', world.private[actor])
            self.assertEqual(world.shared, {})
            self.assertFalse(pending)
            self.assertFalse(world.running_shells)
            self.assertEqual(review.reads(world.events), [])
            self.assertEqual(review.writes(world.events), [])
            event = world.events[-1]
            self.assertEqual(event['operation'], 'workstation_execution_undelivered')
            self.assertEqual(run.load(directory/'operator/tool-commits/000001.json')['event'], event)
            self.assertFalse((path.parent/'0001-tool-1.json').exists())

    def test_cancelled_failed_and_malformed_futures_stay_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            world = self.world(directory)
            actors = list(world.plan)
            cancelled, failed, malformed = Future(), Future(), Future()
            cancelled.cancel()
            failed.set_exception(RuntimeError('workstation observation failed'))
            malformed.set_result({'actor': actors[2], 'command': 'unexpected'})
            pending = {future: self.pending(world, actor, future)
                for actor, future in zip(actors, (cancelled, failed, malformed))}
            run.preserve_pending_shells(world, pending, directory, reason='collector_error')
            records = [run.load(directory/a/'trace/0001-tool-1-undelivered.json') for a in actors[:3]]
            self.assertEqual([r['execution_status'] for r in records],
                ['cancelled_before_execution', 'failed', 'invalid_result'])
            self.assertEqual(records[1]['error']['message'], 'workstation observation failed')
            self.assertEqual(records[2]['execution'], {'actor': actors[2], 'command': 'unexpected'})
            self.assertEqual(len(world.events), 2)
            self.assertNotIn(actors[0], [e['actor'] for e in world.events])
            self.assertFalse(world.running_shells)
            self.assertFalse(pending)

    def test_collector_failure_preserves_inflight_shells_before_cleanup(self):
        # The complete collector runs against deterministic in-process fixtures.
        # All four commands start, another native event fails, then the commands
        # finish before the workstation cleanup. No responses are delivered.
        stations, subject_agents = [], []
        entered = threading.Barrier(4)
        failed = threading.Event()

        class Station:
            def __init__(self, files):
                self.values = deepcopy(files)
                self.name = 'fixture-station-'+str(len(stations))
                self.closed = False
                stations.append(self)

            def execute(self, command, shared):
                if entered.wait(timeout=5) == 0:
                    subject_agents[0].emit('fatal', message='fixture native channel failure')
                    failed.set()
                if not failed.wait(5):
                    raise RuntimeError('fixture failure was not released')
                self.values['/workspace/executed.txt'] = lab.ENCODE('actually executed')
                return ({'exit_code': 0, 'stdout': 'saved stdout', 'stderr': 'saved stderr'},
                        {'/workspace': deepcopy(self.values), '/registry': deepcopy(shared)})

            def close(self):
                # The execution record must exist before private state vanishes.
                self.preserved_before_close = len(list((root/'natural').glob('*/trace/*-undelivered.json'))) == 4
                self.closed = True

        class Agent:
            def __init__(self, actor, events, **options):
                self.actor, self.events, self.options = actor, events, options
                self.replies = []
                if actor != 'preflight':
                    subject_agents.append(self)
                self.emit('ready', active_tools=options['active_tools'], system_prompt='fixture',
                    commands=[], session_id='fixture-'+actor, session_file=None)

            def emit(self, kind, **values):
                self.events.put((self.actor, {'type': kind, **values}))

            def set_tools(self, names):
                pass

            def prompt(self, *texts):
                name = 'confirm_service' if self.actor == 'preflight' else 'bash'
                args = {} if name == 'confirm_service' else {'command': 'printf actually-executed > executed.txt'}
                call = {'type': 'function_call', 'name': name, 'call_id': self.actor+'-call',
                        'arguments': json.dumps(args)}
                self.emit('request', turn=1, attempt=1, payload={
                    'model': self.options['model'], 'tools': self.options['tools'],
                    'input': [{'role': 'system', 'content': 'fixture'},
                              {'role': 'user', 'content': '\n'.join(texts)}]})
                self.emit('provider_response', turn=1, attempt=1, event={'type': 'response.completed',
                    'response': {'model': self.options['model'], 'status': 'completed', 'output': [call]}})
                self.emit('tool_call', turn=1, id=call['call_id'], call_id=call['call_id'], name=name)

            def reply(self, identity, **value):
                self.replies.append(value)
                if self.actor == 'preflight':
                    self.emit('settled', turn=1, aborted=False, text='available', error_message=None)

            def close(self):
                # A late SDK event must not dispatch another tool during cleanup.
                self.emit('tool_call', turn=2, id='late', call_id='late', name='bash')
                return 0

        with tempfile.TemporaryDirectory() as temporary, ExitStack() as patches:
            temporary = Path(temporary)
            root = temporary/'raw'
            registration = temporary/'registrations/fixture'
            key = temporary/'key'
            key.write_text('offline fixture only')
            key.chmod(0o600)
            patches.enter_context(patch.object(run, 'REGISTRATIONS', registration.parent))
            patches.enter_context(patch.object(run, 'verify_routes', return_value={}))
            patches.enter_context(patch.object(run, 'MODELS', {'fixture':'test/fixture'}))
            patches.enter_context(patch.object(run.pi_agent, 'installed_versions', return_value={'offline': 'fixture'}))
            patches.enter_context(patch.object(run.pi_agent, 'node_version', return_value='v22.19.0'))
            patches.enter_context(redirect_stdout(io.StringIO()))
            run.prepare(root, registration, key, run_controls=False, study_mode='phase1', harness_kind='pi-sdk')
            patches.enter_context(patch.object(run, 'verify_collection_freeze'))
            patches.enter_context(patch.object(run, 'registration_api_base', return_value='http://127.0.0.1:1/v1'))
            patches.enter_context(patch.object(run, 'AXONHUB_KEY_FILE', key))
            patches.enter_context(patch.object(run.pi_agent, 'PiAgent', Agent))
            patches.enter_context(patch.object(run.lab.base, 'Workstation', Station))
            with self.assertRaisesRegex(RuntimeError, 'fixture native channel failure'):
                run.collect(root, registration, offline_transport_test=True)
            world = run.load(root/'natural/world.json')
            records = list((root/'natural').glob('*/trace/*-undelivered.json'))
            self.assertEqual(len(records), 4)
            self.assertTrue(all('/workspace/executed.txt' in values for values in world['private_files'].values()))
            self.assertEqual(len(world['events']), 4)
            self.assertTrue(all(e['operation'] == 'workstation_execution_undelivered' for e in world['events']))
            for path in records:
                record = run.load(path)
                self.assertEqual(record['execution']['reply']['stdout'], 'saved stdout')
                self.assertEqual(record['execution']['reply']['stderr'], 'saved stderr')
                self.assertEqual(record['execution_status'], 'completed')
                history = run.load(path.parents[1]/'history.json')
                self.assertFalse(any(item.get('type') == 'function_call_output' for item in history))
            self.assertTrue(all(not agent.replies for agent in subject_agents))
            self.assertTrue(all(station.closed for station in stations))
            self.assertTrue(all(station.preserved_before_close for station in stations))
            self.assertEqual(run.load(root/'completion.json')['status'], 'collector_error')
            review.reconcile_tool_commits(root, world)
            manifest = run.load(root/'evidence-manifest.json')
            self.assertTrue(all(str(path.relative_to(root)) in manifest['files'] for path in records))
            self.assertFalse(list((root/'natural').glob('*/trace/*-tool-[0-9].json')))


if __name__ == '__main__':
    unittest.main()
