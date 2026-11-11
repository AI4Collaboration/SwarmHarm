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

if __name__ == '__main__':
    unittest.main()
