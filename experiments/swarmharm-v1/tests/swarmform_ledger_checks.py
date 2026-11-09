"""Regressions for historical evidence crossing into the active three-agent matrix."""

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[3] / 'scripts'
with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
    import check_swarmform_inputs as checks
    import inspect_swarmform_workload as preview


class SwarmFormLedgerChecks(unittest.TestCase):
    def setUp(self):
        self.status = json.loads(checks.STATUS.read_text())
        # Each test supplies its own registrations and collection state.
        self.status['active_rollouts'] = []
        self.matrix = self.status['matrix']
        self.cell = 'shared_files/payload_content/Data Analysis'
        self.alias = 'shared_files/identifiers_metadata/Data Analysis'

    def test_frozen_pilot_and_unrelated_prose_cannot_admit_new_cell(self):
        for ref in ('docs/research/swarmform-cache-pilot.json', 'docs/phase2-design.md',
                    str(checks.ROOT / 'README.md'), '../swarmharm/README.md'):
            self.matrix['cells'] = {self.cell: {'status': 'admitted', 'evidence': ref}}
            with self.subTest(ref=ref), self.assertRaises(SystemExit):
                checks.validate_active_matrix(self.status)

    def test_five_labels_from_a_different_study_are_not_five_valid_deployments(self):
        self.matrix['deployments'][-1] = 'records'
        with self.assertRaisesRegex(SystemExit, 'deployments differ'):
            checks.validate_active_matrix(self.status)

    def test_current_model_selection_can_be_one_known_model_or_both(self):
        with patch.object(checks, 'check_dispositions', return_value={}):
            for models in (['openai/gpt-6.1-sol'], ['openai/gpt-5.6-sol'], list(checks.KNOWN_MODELS)):
                self.status['current_models'] = models
                with self.subTest(models=models):
                    self.assertEqual(checks.validate_active_matrix(self.status), {})
            for models in ([], ['openai/unknown'], ['openai/gpt-6.1-sol'] * 2, None, 'openai/gpt-6.1-sol'):
                self.status['current_models'] = models
                with self.subTest(models=models), self.assertRaisesRegex(SystemExit, 'known Sol models'):
                    checks.validate_active_matrix(self.status)

    def test_delivery_scope_keeps_supplemental_cells_out_of_default_selection(self):
        from swarmform_scope import selected_cells, role
        selected = selected_cells(self.status)
        retained = selected_cells(self.status, all_retained=True)
        self.assertEqual(len(selected), 30)
        self.assertEqual(sum(cell[2] == 'Knowledge Work' for cell in selected), 25)
        engineering = [cell for cell in selected if cell[2] == 'Engineering']
        self.assertEqual(len(engineering), 5)
        self.assertEqual({cell[1] for cell in engineering}, {'payload_content'})
        self.assertEqual({cell[0] for cell in engineering}, set(self.matrix['deployments']))
        self.assertEqual(len(retained), 100)
        self.assertTrue(set(selected) < set(retained))
        self.assertEqual(role(self.status, self.cell), 'supplemental')

    def test_workload_suite_is_bound_to_its_domain(self):
        for path in (self.matrix['offline_workload_checks']['Data Analysis'],
                     'experiments/swarmharm-v1/tests/swarmform_runtime_checks.py'):
            self.matrix['offline_workload_checks'] = {'Engineering': path}
            with self.subTest(path=path), self.assertRaisesRegex(SystemExit, 'identify the SwarmForm domain'):
                checks.check_workloads(self.matrix)

    def test_frozen_four_worker_registration_is_rejected(self):
        retained = json.loads((checks.ROOT / 'docs/research/reporting-run-index.json').read_text())
        self.status['maintained_registrations'] = retained['swarmform']['registrations'][:1]
        with self.assertRaisesRegex(SystemExit, 'three-agent'):
            checks.check_registrations(self.status, {})

    def test_admission_equivalence_and_registration_bind_the_same_effective_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            package = root / 'experiments/swarmharm-v1'
            folder = package / 'registrations/test-only'
            folder.mkdir(parents=True)
            def save(name, value):
                data = json.dumps(value).encode()
                (root / name).write_bytes(data)
                return sha256(data).hexdigest()

            identity = {'research_study': 'SwarmForm', 'population': 3}
            manifest = {**identity, 'domain': 'Data Analysis', 'mount': 'shared test volume'}
            save('input.json', manifest)
            digest = checks.json_digest(manifest)
            self.matrix['cells'] = {
                self.cell: {'status': 'admitted', 'evidence': 'cell.json'},
                self.alias: {'status': 'equivalent', 'canonical': self.cell, 'evidence': 'alias.json'},
            }
            report = {**identity, 'matrix_cell': self.cell, 'status': 'admitted',
                      'input_manifest': 'input.json', 'input_sha256': digest}
            alias = {**report, 'matrix_cell': self.alias, 'status': 'equivalent'}
            save('cell.json', report)
            save('alias.json', alias)
            reg = {**identity, 'matrix_cell': self.cell, 'input_sha256': digest, 'inference_gateway': 'axonhub',
                   'reasoning': 'high', 'api_base': checks.AXONHUB_BASE,
                   'harness': {'kind': 'codex', 'authentication': 'axonhub', 'goal_mode': 'off',
                               'gateway': checks.AXONHUB_BASE},
                   'budget': {'active_contexts_natural': 3}, 'models': {'sol': 'openai/gpt-6.1-sol'},
                   'plan': {'natural': {actor: {'provider': 'sol'} for actor in ('a', 'b', 'c')}}}
            self.status['maintained_registrations'] = [str(folder.relative_to(root))]
            self.status['active_rollouts'] = [{'registration': str(folder.relative_to(root))}]
            keys = {self.cell, self.alias}
            with patch.object(checks, 'ROOT', root), patch.object(checks, 'PACKAGE', package):
                manifests = checks.check_dispositions(self.status, keys)
                self.assertEqual(manifests, dict.fromkeys(keys, digest))
                def seal_registration(value):
                    signature = save(folder / 'registration.json', value)
                    save(folder / 'registration-seal.json', {'sha256': signature})

                seal_registration(reg)
                checks.check_registrations(self.status, manifests)
                # A narrower collection selection does not invalidate frozen registrations.
                self.status['current_models'] = ['openai/gpt-6.1-sol']
                seal_registration({**reg, 'models': {'sol': 'openai/gpt-5.6-sol'}})
                checks.check_registrations(self.status, manifests)
                seal_registration(reg)
                self.status['active_rollouts'].append({'registration': 'unregistered-fixture'})
                with self.assertRaisesRegex(SystemExit, 'active rollout has no matching'):
                    checks.check_registrations(self.status, manifests)
                self.status['active_rollouts'].pop()
                save(folder / 'registration.json', {**reg, 'reasoning': 'low'})
                with self.assertRaisesRegex(SystemExit, 'digest mismatch'):
                    checks.check_registrations(self.status, manifests)
                for delta, message in (({'input_sha256': '0' * 64}, 'admitted input'),
                                       ({'matrix_cell': self.alias}, 'admitted input'),
                                       ({'models': {'sol': 'openai/unknown'}}, 'route or runtime'),
                                       ({'api_base': 'https://wrong.invalid'}, 'route or runtime'),
                                       ({'budget': {'active_contexts_natural': 2}}, 'three-agent')):
                    seal_registration({**reg, **delta})
                    with self.subTest(delta=delta), self.assertRaisesRegex(SystemExit, message):
                        checks.check_registrations(self.status, manifests)

                other = {**manifest, 'mount': 'private test volume'}
                save('other.json', other)
                other_digest = checks.json_digest(other)
                save('alias.json', {**alias, 'input_manifest': 'other.json', 'input_sha256': other_digest})
                with self.assertRaisesRegex(SystemExit, 'identical effective input'):
                    checks.check_dispositions(self.status, keys)
                self.matrix['cells'][self.alias]['status'] = 'admitted'
                (root / 'same.json').write_text(json.dumps(manifest, sort_keys=True, indent=2))
                save('alias.json', {**alias, 'status': 'admitted', 'input_manifest': 'same.json'})
                with self.assertRaisesRegex(SystemExit, 'admitted twice'):
                    checks.check_dispositions(self.status, keys)
                old_population = {**manifest, 'population': 4}
                save('input.json', old_population)
                with self.assertRaisesRegex(SystemExit, 'digest mismatch'):
                    checks.check_dispositions(self.status, keys)
                save('cell.json', {**report, 'input_sha256': checks.json_digest(old_population)})
                with self.assertRaisesRegex(SystemExit, 'different study, population or domain'):
                    checks.check_dispositions(self.status, keys)

    def test_failed_preview_leaves_destination_available_for_retry(self):
        def interrupted(folder, *args):
            folder.mkdir()
            (folder / 'partial.csv').write_text('incomplete')
            raise OSError('simulated write failure')

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'preview'
            with patch.object(preview, 'write_preview', side_effect=interrupted), self.assertRaises(OSError):
                preview.export_workload(target, 'same dataset', staged=True)
            self.assertEqual(list(target.parent.iterdir()), [])
            preview.export_workload(target, 'same dataset', staged=True)
            initial = (target / 'arrival-offsets-seconds.json').read_bytes()
            with self.assertRaises(FileExistsError):
                preview.export_workload(target, 'different dataset')
            self.assertEqual((target / 'arrival-offsets-seconds.json').read_bytes(), initial)
