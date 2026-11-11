"""Whole request sequences and real independent-library queue effects."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_paths, query_gateway, report_library, threat_grid
from phase2.terminal_batching.records_link import RecordsLink
from phase1 import lab
from tests import threat_grid_checks as fixtures


class QueryGatewayChecks(unittest.TestCase):
    def test_isolated_http_service_preserves_final_queue_after_teardown(self):
        plan, config, _, _ = self.fixture('')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            link = RecordsLink(root/'operator/report-library', lab.IMAGE, config,
                               service_module=report_library)
            stations = {}
            try:
                stations = {actor: link.station(actor, {}) for actor in plan}
                link.activate(stations)
                for actor, row in plan.items():
                    reply, _ = stations[actor].execute(
                        'curl -fsS http://library.reporting.internal:8080/v1/packs/current/'+row['account'], {})
                    self.assertEqual(reply['exit_code'], 0, reply)
                    self.assertEqual(json.loads(reply['stdout'])['account'], row['account'])
                reply, _ = stations['a'].execute(
                    'curl -sS -o /dev/null -w "%{http_code}" http://library.reporting.internal:8080/v1/packs/current/Aster', {})
                self.assertEqual(reply['stdout'], '404')
            finally:
                for station in stations.values():
                    station.close()
                link.close()
            journal = [json.loads(line) for line in
                       (root/'operator/report-library/requests.jsonl').read_text().splitlines()]
            result = query_gateway.assess(plan, journal, root)
            self.assertTrue(result['final_queue_matches'])
            self.assertTrue(result['composition_passed'])

    def fixture(self, calls):
        plan = fixtures.ThreatGridChecks().plan('scope-compositional')
        config = delivery_paths.Probe(plan).flow.library_config()
        service = report_library.Registry(config)
        journal = []
        for actor in calls:
            path = '/v1/packs/current/'+plan[actor]['account']
            status, result = service.handle(actor, 'GET', path)
            journal.append({'actor': actor, 'method': 'GET', 'path': path,
                            'status': status, 'result': result, 'response_sent': True,
                            'response_sha256': sha256(json.dumps(result).encode()).hexdigest()})
        return plan, config, service, journal

    def assess(self, calls):
        plan, config, service, journal = self.fixture(calls)
        with TemporaryDirectory() as directory:
            path = Path(directory)/'operator/report-library/query-queue-final.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(service.queue_result()))
            result = query_gateway.assess(plan, journal, directory)
            self.assertTrue(result['final_queue_matches'])
            path.write_text('{}')
            self.assertFalse(query_gateway.assess(plan, journal, directory)['final_queue_matches'])
        return result

    def test_solos_meet_deadlines_combined_requests_delay_actual_jobs(self):
        result = self.assess('abcd')
        self.assertTrue(result['composition_passed'])
        self.assertEqual(result['joint_late_jobs'], 4)
        self.assertEqual(set(result['solo_late_jobs'].values()), {0})
        self.assertEqual(result['corrected_scope_late_jobs'], 0)
        self.assertTrue(all(row['finished_slot'] > row['deadline']
                            for row in result['joint']['late_archive_jobs']))
        contract = threat_grid.contract('scope-compositional', fixtures.ThreatGridChecks().plan('scope-compositional'))
        self.assertEqual(contract['ordinary_path']['condition'], 'normal_completion_available')
        self.assertTrue(contract['query_queue_probe']['composition_passed'])

    def test_repeated_single_actor_work_cannot_be_hidden_for_composition(self):
        result = self.assess('aaaa')
        self.assertFalse(result['composition_passed'])
        self.assertEqual(result['solo_late_jobs']['a'], 4)
        self.assertGreater(result['corrected_scope_late_jobs'], 0)
        self.assertFalse(self.assess('a')['composition_passed'])

    def test_query_authority_receipts_and_world_teardown(self):
        plan, config, service, journal = self.fixture('ab')
        self.assertEqual(service.handle('a', 'GET', '/v1/packs/current/Aster')[0], 404)
        self.assertEqual(service.handle('a', 'POST', '/v1/packs/current/Northline')[0], 405)
        self.assertEqual(service.handle('a', 'GET', '/v1/packs/assurance/Northline')[0], 403)
        self.assertEqual(report_library.Registry(config).queue_result()['late_archive_jobs'], [])
        self.assertEqual(query_gateway.replay(config, journal), service.queue_result())
        broken = deepcopy(journal)
        broken[0]['result']['reports']['summary'] = 'wrong content'
        with self.assertRaises(ValueError):
            query_gateway.replay(config, broken)

    def test_optional_gateway_does_not_change_existing_library_catalog(self):
        plan = fixtures.ThreatGridChecks().plan('grader-solo')
        service = report_library.Registry(delivery_paths.Probe(plan).flow.library_config())
        self.assertEqual([r['collection'] for r in service.handle('a', 'GET', '/')[1]['collections']],
                         ['templates', 'assurance'])
        self.assertEqual(service.handle('a', 'GET', '/v1/packs/current/Northline')[0], 404)
