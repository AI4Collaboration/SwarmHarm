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
            "Knowledge Work",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.FINANCIAL_ANALYSIS).DOMAIN,
            "Financial Analysis",
        )
        self.assertEqual(
            domain_runtime.mechanics(domain_runtime.KNOWLEDGE_WORK).DOMAIN,
            "Knowledge Work",
        )

    def test_unknown_scenario_fails_closed(self):
        for value in (None, "", "unknown", "procurement-pilot", domain_runtime.SHARED_FIXTURE,
                      domain_runtime.ENGINEERING, domain_runtime.ENGINEERING_MAINTENANCE,
                      domain_runtime.DATA_ANALYSIS, domain_runtime.FINANCIAL_ANALYSIS):
            with self.subTest(value=value), self.assertRaises(ValueError):
                domain_runtime.normalize(value)

    def test_two_domains_preserve_source_workloads_and_registered_history(self):
        self.assertEqual(domain_runtime.SUPPORTED, ('engineering-capacity', 'knowledge-work'))
        for workload in domain_runtime.WORKLOADS:
            domain = domain_runtime.domain_for(workload)
            self.assertEqual(domain_runtime.resolve_workload(domain, workload), workload)
            self.assertEqual(domain_runtime.registered_workload({'scenario': domain, 'workload': workload}), workload)
            self.assertEqual(domain_runtime.registered_workload({'scenario': workload}), workload)
        for workload in ('data-analysis', 'financial-analysis'):
            self.assertEqual(domain_runtime.domain_for(workload), 'knowledge-work')
            with self.assertRaises(ValueError):
                domain_runtime.resolve_workload('engineering-capacity', workload)

    def test_each_scenario_pressure_is_accepted_by_collection_preflight(self):
        for scenario in domain_runtime.WORKLOADS:
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
            "swarmharm/scenarios/engineering.py",
            relative,
        )
        self.assertIn(
            "swarmharm/domain_runtime.py",
            relative,
        )
        self.assertIn(
            "swarmharm/scenarios/data_analysis.py",
            relative,
        )
        self.assertIn(
            "swarmharm/scenarios/financial_analysis.py",
            relative,
        )
        self.assertIn(
            "swarmharm/scenarios/knowledge_work.py",
            relative,
        )

