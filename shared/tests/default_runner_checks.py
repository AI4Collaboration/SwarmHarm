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
        for study in ('swarmform', 'swarmharm'):
            self.assertEqual(plan['settings'][study]['populations'], [4, 8, 16, 32])
        self.assertEqual((plan['settings']['repeats'], plan['settings']['goal'], plan['settings']['reasoning']),
                         (1, 'off', 'high'))
        self.assertEqual(plan['cohorts'], {'swarmform':480, 'swarmharm':528})
        self.assertEqual(plan['settings']['swarmform']['models'], ['terra'])
        form_only = runner.plan('http://localhost:8000/v1', studies=['swarmform'])
        self.assertEqual([model['name'] for model in form_only['models']], ['terra'])
        for model in plan['models']:
            for study, count in [('swarmform',480), ('swarmharm',48)]:
                if model['name'] not in plan['settings'][study]['models']:
                    continue
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

    def test_resume_reuses_intact_api_check_and_dispatches_the_12_registered_batches(self):
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
                 patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != 'SWARMHARM_NATIVE_CODEX'}, clear=True), \
                 patch.dict(os.environ, {'OPENAI_API_KEY':'fixture-only'}):
                self.assertEqual(runner.execute(args, plan, config), 0)
            self.assertEqual(len(calls), 12)
            self.assertTrue(all('check-model-lineup' not in c[0][1] for c in calls))
            self.assertTrue(all('SWARMHARM_NATIVE_CODEX' not in env for _, env in calls))
            self.assertEqual({env['OPENAI_API_KEY'] for _,env in calls}, {'fixture-only'})
            self.assertEqual({env['OPENAI_BASE_URL'] for _,env in calls}, {plan['api_base']})
            self.assertEqual({env['SWARMHARM_DOCKER_IMAGE'] for _,env in calls}, {'form-image','harm-image'})
            index = json.loads((root/'index.json').read_text())
            self.assertEqual([r['model'] for r in index['batches'] if r['study']=='swarmform'], ['openai/gpt-6.1-terra'])
            self.assertEqual(len(index['batches']), 12)
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

    def test_swarmharm_single_agent_n1_and_targeted_cell_plans(self):
        n1_plan = runner.plan('http://localhost:8000/v1', studies=['swarmharm'], populations=[1],
                              reasoning_effort='medium')
        self.assertEqual(n1_plan['cohorts'], {'swarmform': 0, 'swarmharm': 132})
        self.assertEqual(n1_plan['settings']['swarmharm']['populations'], [1])
        self.assertEqual(n1_plan['settings']['reasoning'], 'medium')
        # Verify the child swarmharm/run_matrix.py CLI actually accepts --populations 1 --reasoning-effort medium
        n1_cmd = runner.batch_command(sys.executable, 'swarmharm', n1_plan['models'][0], n1_plan['api_base'],
                                      '/tmp/unused', populations=[1], reasoning_effort='medium')
        n1_cmd.remove('--execute')
        n1_rows = [json.loads(line) for line in subprocess.check_output(n1_cmd, cwd=ROOT, text=True).splitlines()]
        self.assertEqual(len(n1_rows), 12)
        self.assertEqual({r['population'] for r in n1_rows}, {1})
        self.assertEqual({r['reasoning_effort'] for r in n1_rows}, {'medium'})

        argon_cell = runner.plan('http://localhost:8000/v1', names=['argon'], studies=['swarmharm'],
                                 populations=[32], scenarios=['knowledge-work'], mechanisms=['task-gaming'],
                                 reasoning_effort='medium')
        self.assertEqual(argon_cell['cohorts'], {'swarmform': 0, 'swarmharm': 1})
        cmd = runner.batch_command(sys.executable, 'swarmharm', argon_cell['models'][0], argon_cell['api_base'],
                                   '/tmp/unused', populations=[32], scenarios=['knowledge-work'],
                                   mechanisms=['task-gaming'], coupling='uncoupled', reasoning_effort='medium')
        self.assertIn('--coupling', cmd)
        self.assertIn('uncoupled', cmd)
        self.assertIn('--reasoning-effort', cmd)
        self.assertIn('medium', cmd)
        self.assertIn('task-gaming', cmd)

    def test_runtime_config_rejects_outdated_recipe_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            config = {
                'python': sys.executable,
                'images': {'swarmform': 'form-img', 'swarmharm': 'harm-img'},
            }
            (state / 'default-runner.json').write_text(json.dumps(config))
            with patch.dict(os.environ, {'SWARMHARM_READINESS': str(state)}), \
                 patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, 'setup-defaults'):
                    runner.runtime_config()
                config['recipe_sha256'] = 'stale-digest'
                (state / 'default-runner.json').write_text(json.dumps(config))
                with self.assertRaisesRegex(RuntimeError, 'setup-defaults'):
                    runner.runtime_config()
                config['recipe_sha256'] = runner.recipe_sha256()
                (state / 'default-runner.json').write_text(json.dumps(config))
                self.assertEqual(runner.runtime_config()['recipe_sha256'], config['recipe_sha256'])


if __name__ == '__main__':
    unittest.main()
