"""Four real native sessions against deterministic local responses, no inference."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import codex_gateway
import export_atif
from swarmform.collection import BASH, save
from swarmform.inputs import WORKSTATION_PERMISSIONS
from swarmform.structure_collection import StructureCollection
from tests.swarmform_collection_checks import Responses


class StructureNativeChecks(unittest.TestCase):
    def test_four_sessions_five_real_arrivals_and_observed_usage(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Responses)
        server.requests,server.lock=[],threading.Lock()
        server.wait_for_arrivals=False
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config

        def local_config(home,*args):
            original(home,*args)
            path=home/'config.toml'
            content=path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(content.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))

        try:
            with tempfile.TemporaryDirectory() as directory,patch.object(codex_gateway,'write_config',local_config):
                root=Path(directory);actors=tuple(f'Office{i:02d}' for i in range(1,5))
                offsets={b:i*2 for i,b in enumerate(('opening','revision_one','new_orders','revision_two','closing'))}
                visible={'startup':{a:{'/workspace/work-order.md':f'Prepare {a} publications.'} for a in actors},
                    'private_arrivals':{a:{b:{f'intake/{b}/record.txt':f'{a} {b} units 37\n'} for b in offsets} for a in actors},
                    'prompts':{a:[f'Prepare {a} publications.'] for a in actors},'tools':[BASH]}
                model='openai/gpt-6.1-sol'
                reg={'population':4,'model':model,'reasoning':'high','workstation_permissions':WORKSTATION_PERMISSIONS,
                    'harness':codex_gateway.harness_registration('off',model),
                    'deployment':{'kind':'shared_files','shared':True},'arrival_offsets':offsets,
                    'budget':{'max_batch_seconds':120,'max_agent_seconds':90,'request_timeout_seconds':30,
                        'max_tools_per_agent':20,'max_responses_per_agent':30,'max_observed_tokens_per_agent':5000,
                        'min_free_bytes':64*1024**2},
                    'study_mode':'swarmform-structure','research_study':'SwarmForm Structure',
                    'plan':{'natural':{a:{} for a in actors}}}
                save(root/'registration.json',reg)
                report=StructureCollection(root,reg,visible,api_key='offline-fixture').run()
                self.assertIsNone(report['failure'],report)
                self.assertEqual(report['reason'],'quiescence')
                self.assertEqual(report['terminal_snapshot_count'],4)
                self.assertEqual(len(json.loads((root/'source-deliveries.json').read_text())),20)
                self.assertEqual(len({s['codex_session']['session_id'] for s in report['actors'].values()}),4)
                usage=json.loads((root/'usage.json').read_text())
                self.assertEqual(set(usage['actors']),set(actors))
                for actor in actors:
                    self.assertGreater(usage['actors'][actor]['observed_tokens'],0)
                    self.assertTrue(export_atif.export_actor(root,'natural',actor)['native_continuity_passed'])
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
