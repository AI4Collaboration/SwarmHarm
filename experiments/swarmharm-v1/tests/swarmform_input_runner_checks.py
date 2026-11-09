"""Minimal structural checks for the SwarmForm input matrix."""

import ast
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from check_swarmform_input_runners import matrix
import export_swarmform_input_matrix as exporter
import swarmform_ipc_witness_protocols as ipc_protocols
import swarmform_service_witness_codecs as service_protocols
import swarmform_endpoint_witness_codecs as endpoint_protocols
import swarmform_service_timing_witness as service_timing
import swarmform_endpoint_timing_witness as endpoint_timing


class SwarmFormInputRunnerChecks(unittest.TestCase):
    def test_timing_registered_quantization_uses_observer_nanoseconds(self):
        codec = {}
        exec(service_timing.FRAMED_TIMING, codec)
        source = b"An independently checked complete timing source."
        stamp = 1_794_231_000_000_000_000
        events = [{"observed_ns": stamp}]
        for frame in codec["frames"](source):
            # Calibration has a large offset, while the payload retains the
            # registered 15 ms base and 12 ms spacing. Relative fitting alone
            # cannot bridge this offset; no source bytes enter the decoder.
            gaps = [800_000_000, 800_000_000]
            gaps += [50_000_000 + symbol * 12_000_000
                     for symbol in codec["CALIBRATION"]]
            gaps += [15_000_000 + symbol * 12_000_000
                     for symbol in codec["symbols"](frame)]
            for gap in gaps:
                stamp += gap
                events.append({"observed_ns": stamp})
        with patch.dict(codec, {"SYMBOL_BASE": .050, "STEPS": ()}):
            with self.assertRaisesRegex(ValueError, "no valid timing frames"):
                codec["recover"](events)
        codec["FRAME_CACHE"].clear()
        recovered, summary = codec["recover"](events)
        self.assertEqual(recovered, source)
        self.assertEqual(summary["frames_using_calibration_fallback"], summary["frames"])

    def test_operator_witness_protocols_parse(self):
        snippets = [value for module in (ipc_protocols, service_protocols, endpoint_protocols,
                                        service_timing, endpoint_timing)
                    for name, value in vars(module).items()
                    if name.isupper() and isinstance(value, str)]
        self.assertTrue(snippets)
        for index, snippet in enumerate(snippets):
            ast.parse(snippet, filename=f"witness-protocol-{index}")

    def test_exporter_materializes_a_complete_hashed_input(self):
        matrix()  # Validates all 100 routes, including their script paths.
        with TemporaryDirectory() as folder:
            root = Path(folder)
            package = exporter.materialize(
                root / "one", "november", "job_namespace", "timing",
                "Knowledge Work")
            cell = root / "one" / "job_namespace" / "timing" / "knowledge-work"
            self.assertEqual(package["population"], 3)
            self.assertEqual(len(list(cell.rglob("task.toml"))), 3)
            self.assertEqual(len(list(cell.rglob("instruction.md"))), 3)

            for name, checksum in package["files"].items():
                self.assertEqual(sha256((cell / name).read_bytes()).hexdigest(), checksum)


if __name__ == "__main__":
    unittest.main()
