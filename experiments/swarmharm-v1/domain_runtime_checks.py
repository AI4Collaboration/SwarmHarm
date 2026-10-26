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
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.DATA_ANALYSIS).DOMAIN,
            "Data Analysis",
        )
        self.assertEqual(
            domain_runtime.public_domain(domain_runtime.DATA_ANALYSIS),
            "Data Analysis",
        )
        self.assertEqual(
            domain_runtime.continuation_module(domain_runtime.DATA_ANALYSIS),
            "domains.data_analysis_continuation",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.FINANCIAL_ANALYSIS).DOMAIN,
            "Financial Analysis",
        )
        self.assertEqual(
            domain_runtime.continuation_module(domain_runtime.FINANCIAL_ANALYSIS),
            "domains.financial_analysis_continuation",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.KNOWLEDGE_WORK).DOMAIN,
            "Knowledge Work",
        )
        self.assertEqual(
            domain_runtime.continuation_module(domain_runtime.KNOWLEDGE_WORK),
            "domains.knowledge_work_continuation",
        )

    def test_unknown_scenario_fails_closed(self):
        with self.assertRaises(ValueError):
            domain_runtime.normalize("unknown")

    def test_each_scenario_pressure_is_accepted_by_collection_preflight(self):
        for scenario in domain_runtime.SUPPORTED:
            expected = domain_runtime.mechanics(scenario).business_pressure(
                "2030-01-01T00:00:00+00:00"
            )["kind"]
            self.assertEqual(run.expected_pressure_kind(scenario), expected)

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
        self.assertIn(
            "experiments/swarmharm-v1/domains/data_analysis.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/domains/financial_analysis.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/domains/knowledge_work.py",
            relative,
        )

