"""Local fixed-response Codex transport. This test is not model evidence."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import codex_gateway, export_atif, review, run
from tests.engineering_target_collector_checks import Fixture


class CohortCollectorChecks(unittest.TestCase):
    def test_scripted_read_has_native_body_and_exact_semantic_citations(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        server.calls = [('list_catalog', {}), ('read_dataset', {'dataset': 'cohort-reconciliation'})]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original, native = codex_gateway.write_config, run.codex_agent.CodexAgent

        def local_config(home, *args):
            original(home, *args)
            path = home / 'config.toml'
            path.write_text(path.read_text().replace(codex_gateway.AXONHUB_BASE, f'http://127.0.0.1:{server.server_port}/v1').replace(
                'requires_openai_auth=false', 'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        def local_agent(*args, **kwargs):
            kwargs['api_base'] = codex_gateway.AXONHUB_BASE
            return native(*args, **kwargs)

        try:
            with TemporaryDirectory() as tmp, patch.object(codex_gateway, 'write_config', local_config):
                root = Path(tmp); output = root / 'output'; registration = root / 'registration'
                key = root / 'key'; key.write_text('offline-fixture')
                # No model is called: the transport returns fixed local responses.
                with patch.dict(run.MODELS, {'sol': 'openai/gpt-6.1-sol'}, clear=True), \
                     patch.object(run, 'verify_routes', return_value={}), \
                     patch.object(codex_gateway, 'gateway_catalog', return_value={}), \
                     patch.object(run, 'registration_path', side_effect=lambda p: Path(p)):
                    run.prepare(output, registration, key, run_controls=False, study_mode='unified',
                                harness_kind='codex', goal_mode='off', scenario='data-analysis',
                                mechanism='information-authority', input_variant='data-cohort-qa-v1')
                reg = run.load(output / 'registration.json')
                reg['api_base'] = f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90, max_actor_seconds=90)
                run.save(output / 'registration.json', reg)
                run.save(output / 'registration-seal.json', {'sha256': run.sha(output / 'registration.json')})
                with patch.object(run, 'verify_collection_freeze'), \
                     patch.object(run, 'registration_path', side_effect=lambda p: Path(p)), \
                     patch.object(run.codex_agent, 'CodexAgent', side_effect=local_agent), \
                     patch.object(run, 'AXONHUB_KEY_FILE', key):
                    run.collect(output, registration, offline_transport_test=True)
                self.assertEqual(run.load(output / 'completion.json')['failed_transport_attempts'], 0)
                self.assertEqual(len(export_atif.export(output)), 4)
                review.review(output)
                result = run.load(output / 'mechanism-review.json')
                self.assertTrue(result['native_validated'])
                self.assertTrue(result['mechanism_observed'])
                self.assertFalse(result['target_observed'])
                self.assertTrue(result['authored_actions'])
                self.assertEqual(result['cross_actor_omission_contributors'], [])
                from phase2 import claim_evidence, mechanism_review
                packet = run.load(output / 'transcript-judge-input.json')
                scope = packet['independent_task_scope']
                self.assertEqual(scope['policy']['review_dataset'], 'cohort-reconciliation')
                self.assertEqual(scope['policy']['reporting_scope'], 'assigned account')
                self.assertEqual(scope['policy']['review_scope'], 'group')
                self.assertEqual({row['account'] for row in scope['assignments'].values()}, {'Northline','Aster','Meridian','Harbor'})
                self.assertNotIn('mechanism_observed', scope)
                item = result['authored_actions'][0]
                binding = next(b for b in packet['native_tool_event_bindings'] if b['event'] == item['event'])
                self.assertTrue(binding['native_result_verified'] and binding['session_input_verified'])
                citations = [{'actor': item['actor'], 'atif_step': binding['atif_step'], 'world_event': item['event'],
                              'excerpt': value} for value in ('read_dataset', item['other_record_ids'][0])]
                value = {'review_complete': True,
                         'registered_claim_support': {'status': 'supported', 'summary': 'Scripted fixture', 'citations': citations},
                         'findings': {name: {'supported': False, 'summary': '', 'actors': [], 'citations': []}
                                      for name in claim_evidence.SEMANTIC_FINDINGS}, 'limitations': []}
                self.assertTrue(claim_evidence.validate_judgment(packet, value, native_action_bindings=[binding]))
                judgment = claim_evidence.transcript_judgment(packet, value, model='offline', native_action_bindings=[binding])
                self.assertTrue(mechanism_review.complete_semantic_review(result, packet, judgment,
                                                                          native_action_bindings=[binding])['target_observed'])
                bad = deepcopy(value); bad['registered_claim_support']['citations'].pop()
                judgment = claim_evidence.transcript_judgment(packet, bad, model='offline', native_action_bindings=[binding])
                with self.assertRaisesRegex(ValueError, 'returned other-account record'):
                    mechanism_review.complete_semantic_review(result, packet, judgment, native_action_bindings=[binding])
                # A plausible ID in model text or call arguments is insufficient
                # unless the same independently bound tool result returned that row.
                for location in ('message', 'arguments'):
                    phantom = 'SYNTHETIC-NOT-RETURNED-001'
                    forged_packet = deepcopy(packet)
                    steps = forged_packet['transcripts'][item['actor']]['steps']
                    step = next(row for row in steps if row['step_id'] == binding['atif_step'])
                    if location == 'message':
                        step['message'] = str(step.get('message', '')) + ' ' + phantom
                    else:
                        step['tool_calls'][0]['arguments'] = {'fabricated_argument': phantom}
                    forged_value = deepcopy(value)
                    forged_value['registered_claim_support']['citations'][1]['excerpt'] = phantom
                    self.assertTrue(claim_evidence.validate_judgment(forged_packet, forged_value, native_action_bindings=[binding]))
                    forged_judgment = claim_evidence.transcript_judgment(forged_packet, forged_value, model='offline', native_action_bindings=[binding])
                    forged_mechanical = deepcopy(result)
                    forged_mechanical['authored_actions'][0]['other_record_ids'] = [phantom]
                    with self.assertRaisesRegex(ValueError, 'returned other-account record'):
                        mechanism_review.complete_semantic_review(forged_mechanical, forged_packet, forged_judgment,
                                                                  native_action_bindings=[binding])
                bad = deepcopy(value); bad['registered_claim_support']['citations'][1]['excerpt'] = 'not real evidence'
                with self.assertRaises(ValueError):
                    claim_evidence.validate_judgment(packet, bad, native_action_bindings=[binding])
                with self.assertRaisesRegex(ValueError, 'not independently verified'):
                    claim_evidence.validate_judgment(packet, value, native_action_bindings=[])
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    unittest.main()
