"""A partial export must not stand in for all three registered actors."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from swarmform.actor_evidence import completeness, export_closed_actors


class ActorEvidenceChecks(unittest.TestCase):
    def test_failed_member_does_not_skip_healthy_later_exports_or_hide_missing_history(self):
        actors = [f'Research{i:02d}' for i in range(1, 9)]
        reg = {'study_mode': 'swarmform-structure', 'population': 8,
               'plan': {'natural': dict.fromkeys(actors, {})}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'completion.json').write_text('{}')
            for actor in actors:
                folder = root / 'natural' / actor
                (folder / 'codex/native').mkdir(parents=True)
                (folder / 'codex/native/000001.json').write_text('{"original":true}')
                if actor != 'Research06':
                    (folder / 'history.json').write_text('[]')
            originals = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            attempted = []
            def export_actor(root, phase, actor):
                attempted.append(actor)
                if actor == 'Research02':
                    raise AssertionError('Codex context compacted')
                return {'phase': phase, 'actor': actor, 'native_continuity_passed': True}
            with patch('export_atif.export_actor', side_effect=export_actor):
                result = export_closed_actors(root, reg)
            self.assertEqual(attempted, [a for a in actors if a != 'Research06'])
            self.assertEqual([x['actor'] for x in result['failed_trajectories']], ['Research02', 'Research06'])
            self.assertFalse(result['all_registered_actors_exported'])
            coverage = completeness(root, reg)
            self.assertFalse(coverage['actor_evidence_complete'])
            self.assertEqual(coverage['missing_actors']['atif'], ['Research02', 'Research06'])
            self.assertIn('Research08', coverage['continuity_verified_actors'])
            self.assertEqual({p: p.read_bytes() for p in originals}, originals)
            before = (root / 'atif-validation.json').read_bytes()
            with patch('export_atif.export_actor') as export, self.assertRaises(FileExistsError):
                export_closed_actors(root, reg)
            export.assert_not_called()
            self.assertEqual((root / 'atif-validation.json').read_bytes(), before)

    def test_export_requires_closed_collection_and_does_not_swallow_interrupt(self):
        reg = {'plan': {'natural': {'actor': {}}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                export_closed_actors(root, reg)
            (root / 'completion.json').write_text('{}')
            folder = root / 'natural/actor';folder.mkdir(parents=True)
            (folder / 'history.json').write_text('[]')
            with patch('export_atif.export_actor', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                export_closed_actors(root, reg)
            self.assertFalse((root / 'atif-validation.json').exists())

    def test_missing_actor_is_partial_even_when_present_trajectories_pass(self):
        actors = ('Northline', 'Aster', 'Meridian')
        registration = {'population': 3, 'plan': {'natural': dict.fromkeys(actors, {})}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for actor in actors[:2]:
                native = root / 'natural' / actor / 'codex/native'
                native.mkdir(parents=True)
                (native / '000001.json').write_text('{"original": true}\n')
            trajectories = [{'phase': 'natural', 'actor': actor, 'native_continuity_passed': True}
                            for actor in actors[:2]]
            validation = root / 'atif-validation.json'
            validation.write_text(json.dumps({'trajectories': trajectories}) + '\n')
            originals = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}

            report = completeness(root, registration)
            self.assertFalse(report['actor_evidence_complete'])
            self.assertEqual(report['actor_coverage_status'], 'partial')
            self.assertEqual(report['registered_actors'], sorted(actors))
            self.assertEqual(report['missing_actors'], {
                'native': ['Meridian'], 'atif': ['Meridian'], 'verified_continuity': ['Meridian']})
            self.assertEqual({path: path.read_bytes() for path in root.rglob('*') if path.is_file()}, originals)

            native = root / 'natural/Meridian/codex/native'
            native.mkdir(parents=True)
            (native / '000001.json').write_text('{"original": true}\n')
            self.assertFalse(completeness(root, registration)['actor_evidence_complete'])
            trajectories.append({'phase': 'natural', 'actor': 'Meridian', 'native_continuity_passed': True})
            self.assertTrue(completeness(root, registration, trajectories)['actor_evidence_complete'])


if __name__ == '__main__':
    unittest.main()
