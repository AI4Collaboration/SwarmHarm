"""Executable engineering releases and foreign-source dependence."""
import unittest
from unittest.mock import patch
from swarmform import engineering, decoder_base
SWARMFORM_DOMAIN = 'Engineering'

class EngineeringChecks(unittest.TestCase):
    def test_private_incomplete_combined_complete_and_version_corrections(self):
        result=engineering.check()
        self.assertEqual(result['actual_reference_release_executions'],9)
        self.assertEqual(result['private_incomplete_releases'],9)
        self.assertGreater(result['stale_release_mismatches'],0)

    def test_supplied_frame_reader_requires_dated_type_records(self):
        _, versions, probes, catalogs, placement = engineering.source_material('november')
        self.assertEqual(decoder_base.TYPE_RECORDS, {})
        for stage, facts in enumerate(versions):
            for actor, ids in catalogs.items():
                for scope, expected_count in [('local', 200), ('combined', 800)]:
                    table = {key: facts[key] for key in ids
                             if scope == 'combined' or placement[key] == actor}
                    with patch.dict(decoder_base.TYPE_RECORDS, table, clear=True):
                        correct = 0
                        for frame, expected in probes[stage][actor]:
                            if expected['type_id'] in table:
                                self.assertEqual(decoder_base.decode(frame), expected)
                                correct += 1
                            else:
                                with self.assertRaises(KeyError):
                                    decoder_base.decode(frame)
                    self.assertEqual(correct, expected_count)

if __name__=='__main__':unittest.main()
