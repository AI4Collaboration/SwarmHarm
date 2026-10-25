"""Checks for scenario resolution and source-freezing coverage."""

import unittest

import domain_runtime
import run


class DomainRuntimeChecks(unittest.TestCase):
    def test_registered_scenarios_resolve(self):
        self.assertEqual(
            domain_runtime.public_domain(domain_runtime.PILOT),
            "Procurement pilot",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.ENGINEERING).DOMAIN,
            "Engineering",
        )

    def test_unknown_scenario_fails_closed(self):
        with self.assertRaises(ValueError):
            domain_runtime.normalize("unknown")

    def test_domain_sources_are_frozen(self):
        relative = {
            path.relative_to(run.REPO).as_posix()
            for path in run.code_paths()
        }
        self.assertIn(
            "experiments/swarmharm-v1/domains/engineering.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/domain_runtime.py",
            relative,
        )

