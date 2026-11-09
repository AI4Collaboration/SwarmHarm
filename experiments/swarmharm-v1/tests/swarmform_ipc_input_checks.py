"""Static checks for the parameterized operator-only IPC witnesses."""

import ast
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'experiments/runtime'), str(ROOT / 'experiments/swarmharm-v1'), str(ROOT / 'scripts')]

from swarmform.input_catalog import build
import swarmform_ipc_witness_protocols as protocols


class IPCInputChecks(unittest.TestCase):
    def test_all_twenty_inputs_build_and_keep_protocols_operator_only(self):
        encodings = ('payload_content','identifiers_metadata','operational_state','event_pattern','timing')
        domains = ('Engineering','Data Analysis','Financial Analysis','Knowledge Work')
        for encoding in encodings:
            for domain in domains:
                visible, _, manifest = build('november', domain, deployment='shared_ipc', encoding=encoding, shared=True)
                self.assertEqual(manifest['effective_settings']['encoding_opportunity'], encoding)
                joined = '\n'.join(text for files in visible['startup'].values() for text in files.values())
                self.assertNotIn('EVENT_PUBLISH', joined);self.assertNotIn('TIMING_PUBLISH', joined)

    def test_embedded_protocols_parse(self):
        names = [name for name in dir(protocols) if name.endswith(('_PUBLISH','_RECEIVE','_PREPARE'))]
        self.assertEqual(len(names), 11)
        for name in names:
            ast.parse(getattr(protocols, name), filename=name)


if __name__ == '__main__':unittest.main()
