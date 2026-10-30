"""Checks for scenario resolution and source-freezing coverage."""

import unittest

import domain_runtime
import run


class DomainRuntimeChecks(unittest.TestCase):
    def test_registered_scenarios_resolve(self):
        self.assertEqual(
            domain_runtime.public_domain(domain_runtime.SHARED_FIXTURE),
            "Shared implementation fixture",
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
            "phase2.domains.data_analysis_continuation",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.FINANCIAL_ANALYSIS).DOMAIN,
            "Financial Analysis",
        )
        self.assertEqual(
            domain_runtime.continuation_module(domain_runtime.FINANCIAL_ANALYSIS),
            "phase2.domains.financial_analysis_continuation",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.KNOWLEDGE_WORK).DOMAIN,
            "Knowledge Work",
        )
        self.assertEqual(
            domain_runtime.continuation_module(domain_runtime.KNOWLEDGE_WORK),
            "phase2.domains.knowledge_work_continuation",
        )

    def test_unknown_scenario_fails_closed(self):
        for value in (None, "", "unknown", "procurement-pilot", domain_runtime.SHARED_FIXTURE,
                      domain_runtime.ENGINEERING, domain_runtime.ENGINEERING_MAINTENANCE):
            with self.subTest(value=value), self.assertRaises(ValueError):
                domain_runtime.normalize(value)

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
            "experiments/swarmharm-v1/scenarios/engineering.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/domain_runtime.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/scenarios/data_analysis.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/scenarios/financial_analysis.py",
            relative,
        )
        self.assertIn(
            "experiments/swarmharm-v1/scenarios/knowledge_work.py",
            relative,
        )

