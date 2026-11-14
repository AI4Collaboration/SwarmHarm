"""Default coverage, exact dispatch and resume checks without hosted inference."""
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
loader = SourceFileLoader('default_runner', str(ROOT/'scripts/run-evals'))
spec = importlib.util.spec_from_loader(loader.name, loader)
runner = importlib.util.module_from_spec(spec)
loader.exec_module(runner)


class DefaultRunnerChecks(unittest.TestCase):
    def test_default_plan_and_every_child_match_the_promised_coverage(self):
        plan = runner.plan('http://localhost:8000/v1')
        self.assertEqual(len(plan['models']), 11)
        self.assertEqual(plan['settings']['swarmform']['populations'], [4, 8, 16, 32])
        self.assertEqual(plan['settings']['swarmharm']['populations'], [4, 8, 16])
        self.assertEqual((plan['settings']['repeats'], plan['settings']['goal'], plan['settings']['reasoning']),
                         (1, 'off', 'high'))
        self.assertEqual(plan['cohorts'], {'swarmform':1056, 'swarmharm':396})
        for model in plan['models']:
            for study, count in [('swarmform',96), ('swarmharm',36)]:
                command = runner.batch_command(sys.executable, study, model, plan['api_base'], '/tmp/unused-plan')
                command.remove('--execute')
                with self.subTest(model=model['name'], study=study):
                    output = subprocess.check_output(command, cwd=ROOT, text=True)
                    rows = [json.loads(line) for line in output.splitlines()]
                    self.assertEqual(len(rows), count)
                    self.assertEqual({r['population'] for r in rows}, set(plan['settings'][study]['populations']))
                    self.assertEqual({r['model'] for r in rows}, {model['model']})
                    self.assertEqual({r['harness'] for r in rows}, {model['harness']})
                    self.assertEqual({r['replicate'] for r in rows}, {1})
                    if study == 'swarmform':
                        self.assertEqual({r['task'] for r in rows}, set(runner.defaults.TASKS))
                        self.assertEqual({r['channel'] for r in rows}, set(runner.defaults.CHANNELS))
                    else:
                        self.assertEqual({r['scenario'] for r in rows}, set(runner.defaults.SCENARIOS))
                        self.assertEqual(len({r['mechanism'] for r in rows}), 6)

    def make_api_evidence(self, root, plan):
        root.mkdir()
        runner.write(root/'registration.json', dict(models=plan['models'], population=4,
                     api_base=plan['api_base'], api_protocol='chat-completions'))
        runner.write(root/'summary.json', [dict(name=m['name'], passed=True,
                     agents=[dict(passed=True)]*4) for m in plan['models']])
        runner.write(root/'evidence-manifest.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.iterdir()})

    def test_resume_reuses_intact_api_check_and_dispatches_all_22_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = runner.plan('http://localhost:8000/v1')
            self.make_api_evidence(root/'api-check', plan)
            args = SimpleNamespace(out=root, key_file=None, model_map=None)
            config = dict(python=sys.executable, images=dict(swarmform='form-image', swarmharm='harm-image'))
            calls = []
            def invoke(command, **kwargs):
                if command[0] != 'git': calls.append((command, kwargs['env']))
                return SimpleNamespace(returncode=0)
            with patch.object(runner.subprocess, 'run', side_effect=invoke), \
                 patch.object(runner.subprocess, 'check_output', return_value=b''), \
                 patch.object(runner, 'run_process', side_effect=lambda command, **kw: (invoke(command, **kw).returncode, None)), \
                 patch.object(runner, 'source_signature', return_value=plan['source_sha256']), \
                 patch.dict(os.environ, {'OPENAI_API_KEY':'fixture-only'}):
                self.assertEqual(runner.execute(args, plan, config), 0)
            self.assertEqual(len(calls), 22)
            self.assertTrue(all('check-model-lineup' not in c[0][1] for c in calls))
            self.assertEqual({env['OPENAI_API_KEY'] for _,env in calls}, {'fixture-only'})
            self.assertEqual({env['OPENAI_BASE_URL'] for _,env in calls}, {plan['api_base']})
            self.assertEqual({env['SWARMHARM_DOCKER_IMAGE'] for _,env in calls}, {'form-image','harm-image'})
            index = json.loads((root/'index.json').read_text())
            self.assertEqual(len(index['batches']), 22)
            self.assertNotIn('fixture-only', (root/'plan.json').read_text()+(root/'index.json').read_text())

    def test_interruption_stops_before_next_model_or_study(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = runner.plan('http://localhost:8000/v1')
            self.make_api_evidence(root/'api-check', plan)
            args = SimpleNamespace(out=root, key_file=None, model_map=None)
            config = dict(python=sys.executable, images=dict(swarmform='form', swarmharm='harm'))
            with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                 patch.object(runner, 'source_signature', return_value=plan['source_sha256']), \
                 patch.object(runner, 'run_process', return_value=(1, 'SIGTERM')) as run:
                self.assertEqual(runner.execute(args, plan, config), 1)
            run.assert_called_once()
            batches = json.loads((root/'index.json').read_text())['batches']
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0]['status'], 'incomplete')
            self.assertEqual(batches[0]['interrupted'], 'SIGTERM')

    def test_partial_or_tampered_api_check_never_starts_study_or_repeats_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = runner.plan('http://localhost:8000/v1')
            self.make_api_evidence(root/'api-check', plan)
            (root/'api-check/summary.json').write_text('[]')
            args=SimpleNamespace(out=root, key_file=None, model_map=None)
            with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                with self.assertRaisesRegex(RuntimeError, 'incomplete or failed'):
                    runner.execute(args, plan, dict(python=sys.executable))
            self.assertTrue(all(c.args[0][0]=='git' for c in run.call_args_list))
            self.assertEqual(json.loads((root/'index.json').read_text()), {'api_check':'failed','batches':[]})
            changed={**plan, 'api_base':'http://different.local/v1'}
            with self.assertRaisesRegex(RuntimeError, 'different plan'):
                runner.execute(args, changed, {})


if __name__ == '__main__':
    unittest.main()
