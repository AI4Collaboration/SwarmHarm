"""A partial export must not stand in for all three registered actors."""

import json
from pathlib import Path
import tempfile
import unittest

from swarmform.actor_evidence import completeness


class ActorEvidenceChecks(unittest.TestCase):
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
