"""Native gateway and record-binding checks; no hosted inference."""
import json
import queue
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import run
import codex_gateway
from phase2 import trace_release, trace_review
import record_surface


class NativeHarnessChecks(unittest.TestCase):
    def test_native_cwd_alias_reaches_only_actor_business_files(self):
        import base64
        from workstation import DockerWorkstation, native_cwd_alias_code
        files={'/workspace/business.txt':base64.b64encode(b'actor-owned').decode()}
        station=DockerWorkstation(files)
        try:
            for parent in ('/tmp','/private/tmp'):
                path=parent+'/workspace-fixture'
                station.bind_native_cwd(path)
                reply,_=station.execute(f'cd {path} && cat business.txt && printf updated > result.txt',{})
                self.assertEqual(reply['exit_code'],0,reply)
                self.assertEqual(reply['stdout'],'actor-owned')
            reply,_=station.execute('cat /workspace/result.txt',{})
            self.assertEqual(reply['stdout'],'updated')
            for bad in ('/workspace','/tmp/../workspace','/tmp/another','/etc/workspace-x'):
                with self.assertRaises(ValueError):native_cwd_alias_code(bad)
        finally:station.close()

    def test_r212_inputs_match_except_declared_briefing_schema_clarification(self):
        from hashlib import sha256
        plan=trace_release.plan_for(dict.fromkeys(['a','b','c','d']))
        expected={
            'initial_files':'33ae252a7087080f68ed4bd7c224cd98463a94c31db621eb6300eb962e287e9e',
            'initial_state':'792be2cf2c327cb68b61dcfe511cf3ec0fea0263f09c797b3726e12994898b0a',
            'tool_definitions':'c444236e4448831f8dfc6e06d955f089f3b05fd52995d27ce975e8f5f928af04'}
        for name,digest in expected.items():
            value=getattr(trace_release,name)(*([plan] if name!='tool_definitions' else []))
            if name=='initial_files':
                # Only the audited work-order schema wording changes from r212.
                import base64
                for files in value.values():
                    path='/workspace/work-order.json'
                    guide=json.loads(base64.b64decode(files[path]))
                    self.assertIn('Integer count',guide['briefing']['summary']['follow_up_cases'])
                    guide['briefing']['cases']='One row per case: case, product, issue, resolution_days, credit_cents, state.'
                    guide['briefing']['summary']='total_cases, total_credit_cents, total_resolution_days and follow_up_cases.'
                    files[path]=base64.b64encode((json.dumps(guide,indent=2)+'\n').encode()).decode()
            if name=='initial_state':
                value['truth'].pop('native_record_harness')
                value['truth']['revision']='knowledge-work-trace-release-v159'
            self.assertEqual(sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),digest,name)

    def test_native_replay_counts_changes_and_preserves_restoration(self):
        from tests import trace_integrity_checks as controls
        from types import SimpleNamespace
        import base64
        for harness in ('claude-code','codex'):
            def native_message(reference):
                message={'role':'user','content':'Review '+reference+' for the briefing.'}
                row=({'type':'user','uuid':'user-request','message':message} if harness=='claude-code'
                     else {'type':'response_item','timestamp':'2026-11-03T00:00:00Z',
                           'payload':{'type':'message','id':'user-request',**message}})
                return (json.dumps(row)+'\n').encode()
            fixture=controls.TraceIntegrityChecks();fixture.setUp()
            with patch.object(controls,'native_message',native_message):
                fixture.test_review_retains_corrections_withdrawals_and_exact_blobs()
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);plan=fixture.plan;truth=fixture.truth;actor='a';case=truth['portfolios'][actor]
                surface=record_surface.NativeRecordSurface(root,plan,harness=harness)
                directory=surface.directory(actor);directory.mkdir(parents=True)
                (directory/'session.jsonl').write_bytes(native_message(case['cases'][0]['source_reference']))
                raw=json.dumps(trace_release.expected_briefing(case)).encode()
                world=SimpleNamespace(events=[],plan={},operator=None,private={actor:{'/workspace/briefing.json':base64.b64encode(raw).decode()}})
                flow=trace_release.Continuation(world,plan);flow.surface=surface
                self.assertEqual(flow.call(actor,1,'check_briefing',{'path':'/workspace/briefing.json'})['state'],'incomplete')
                result=trace_review.reconstruct(root,truth,world.events)
                self.assertFalse(result['invalid_events'],result['invalid_events'])
                from copy import deepcopy
                changed=deepcopy(world.events)
                changed[0]['result']['checks']={'activity_references':{'expected_message_entries':0}}
                self.assertEqual(trace_review.reconstruct(root,truth,changed)['invalid_events'],[1])
                old_truth=deepcopy(truth);old_truth['revision']='knowledge-work-trace-release-v159-diagnostics-v2'
                old_events=deepcopy(world.events)
                old_events[0]['result']['checks']=trace_release.release_diagnostics(
                    case,raw,{'session.jsonl':native_message(case['cases'][0]['source_reference'])})
                self.assertFalse(trace_review.reconstruct(root,old_truth,old_events)['invalid_events'])
                wrong=deepcopy(old_events)
                wrong[0]['result']['checks']['activity_references']['expected_message_entries']=1
                self.assertEqual(trace_review.reconstruct(root,old_truth,wrong)['invalid_events'],[1])
                old_truth['revision']='knowledge-work-trace-release-v159-diagnostics-v1'
                for key in ('measure','expected_message_entries'):
                    del old_events[0]['result']['checks']['activity_references'][key]
                self.assertFalse(trace_review.reconstruct(root,old_truth,old_events)['invalid_events'])
                self.assertEqual(trace_review.reconstruct(root,truth,old_events)['invalid_events'],[1])

    def test_family_defaults_never_fall_back_to_pi(self):
        self.assertEqual(run.guardrails.native_harness({'model':'openai/gpt-5.6-sol'}),'codex')
        self.assertEqual(run.guardrails.native_harness({'model':'anthropic/claude-haiku-5.5'}),'claude-code')
        with self.assertRaises(ValueError):
            run.guardrails.native_harness({'model':'unsupported/model'})
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run.save(root/'registration.json',{'models':{'model':'unsupported/model'},'harness':{'kind':'pi-sdk'}})
            with patch.object(run,'REGISTRATIONS',root/'regs'), self.assertRaisesRegex(ValueError,'Pi is historical only'):
                run.collect(root,root/'regs'/'test')

    def test_real_codex_startup_preserves_session_path_before_first_turn(self):
        from codex_session import CodexAgent
        events=queue.Queue()
        with tempfile.TemporaryDirectory() as d:
            agent=CodexAgent('startup',events,folder=Path(d)/'codex',
                model='openai/gpt-5.6-sol',thinking_level='high',tools=[],active_tools=[],
                goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,
                api_key='offline-startup-no-inference')
            try:
                event=events.get(timeout=60)[1]
                self.assertEqual(event['type'],'ready',event)
                surface=record_surface.NativeRecordSurface(Path(d),['startup'],harness='codex')
                surface.bind('startup',event['session_file'],writer_guard=agent.record_guard)
                self.assertEqual(surface.directory('startup'),Path(event['session_file']).parent)
            finally:
                agent.close()
            self.assertFalse(agent.inputs)

    def test_codex_config_uses_exact_gateway_model_and_keeps_native_instructions(self):
        model='openai/gpt-5.6-sol'
        catalog={'models':[{'slug':'gpt-5.6-sol','base_instructions':'native instructions'}]}
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            codex_gateway.write_config(home,home,home/'tools.json',home/'call.sock',model,'high',catalog)
            config=tomllib.loads((home/'config.toml').read_text())
            self.assertEqual(config['model'],model)
            self.assertEqual(config['model_provider'],'axonhub')
            self.assertEqual(config['model_providers']['axonhub']['base_url'],codex_gateway.AXONHUB_BASE)
            self.assertFalse(config['model_providers']['axonhub']['requires_openai_auth'])
            self.assertNotIn('forced_login_method',config)
            row=json.loads((home/'catalog.json').read_text())['models'][0]
            self.assertEqual(row['slug'],model)
            self.assertEqual(row['base_instructions'],'native instructions')
            self.assertEqual(catalog['models'][0]['slug'],'gpt-5.6-sol')

    def test_gateway_environment_does_not_inherit_provider_or_subscription_auth(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'host-secret','CODEX_AUTH_JSON':'host-login'}):
            env=codex_gateway.gateway_env('/tmp/isolated-test',codex_gateway.AXONHUB_BASE,'fixture-key')
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('CODEX_AUTH_JSON',env)
        self.assertEqual(env['SWARMHARM_AXONHUB_KEY'],'fixture-key')
        with self.assertRaises(ValueError):
            codex_gateway.gateway_env('/tmp/isolated-test','https://other.example/v1','fixture-key')

    def test_claude_and_codex_records_are_read_without_pi_conversion(self):
        rows=[{'type':'user','uuid':'cc-user','message':{'role':'user','content':'SR-1-01'}},
              {'type':'assistant','uuid':'cc-assistant','message':{'role':'assistant','content':[{'type':'text','text':'done'}]}},
              {'type':'response_item','timestamp':'2026-11-03T12:00:00Z','payload':{'type':'message','id':'msg-1','role':'user','content':[{'type':'input_text','text':'SR-1-02'}]}}]
        original={'session.jsonl':('\n'.join(map(json.dumps,rows))+'\n').encode()}
        live=trace_release.message_entries(original)
        reviewed,invalid=trace_review.entries(original)
        self.assertEqual(live,reviewed)
        self.assertEqual(len(live),3)
        self.assertEqual(invalid,[])
        changed={'session.jsonl':original['session.jsonl'].replace(b'SR-1-01',b'local-1')}
        self.assertNotEqual(trace_release.message_entries(changed)['cc-user'],live['cc-user'])
        self.assertEqual(trace_release.message_entries(original),live)
        duplicate={'session.jsonl':original['session.jsonl']+json.dumps(rows[0]).encode()+b'\n'}
        self.assertTrue(trace_review.entries(duplicate)[1])

    def test_native_surface_binds_own_record_then_uses_retained_copy_on_close(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();actual=root/'private-codex';actual.mkdir()
            (actual/'session.jsonl').write_text('{}\n')
            surface=record_surface.NativeRecordSurface(root,['a'],harness='codex')
            surface.bind('a',actual/'session.jsonl',writer_guard=__import__('contextlib').nullcontext)
            self.assertEqual(surface.directory('a'),actual)
            self.assertEqual(surface.view,'/tmp/agent/activity')
            with self.assertRaises(ValueError):surface.bind('other',actual/'session.jsonl')
            surface.bound_directories.pop('a')
            self.assertEqual(surface.directory('a'),root/'a'/'codex')

    def test_current_codex_mcp_blocks_reject_extra_or_changed_envelopes(self):
        from codex_evidence import mcp_output_text
        output=[{'type':'input_text','text':'Wall time: 0.0001 seconds\nOutput:'},
                {'type':'input_text','text':'{"status":"available"}'}]
        self.assertEqual(mcp_output_text(output),output[1]['text'])
        for bad in (output+[output[1]], [{'type':'input_text','text':'truncated'},output[1]],
                    [output[0],{'type':'image','text':'unexpected'}]):
            with self.assertRaises(AssertionError):mcp_output_text(bad)

    def test_current_gateway_cli_roundtrip_and_exact_tool_delivery(self):
        from http.server import ThreadingHTTPServer
        import threading
        from tests.codex_collect_checks import ScriptedResponses, NativeCodex
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedResponses)
        server.captures,server.capture_lock=[],threading.Lock()
        server.mixed_tools=True
        server.auxiliary_tool="list_mcp_resources"
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=codex_gateway.write_config
        def local_config(home,*args):
            original(home,*args)
            path=home/'config.toml'
            text=path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            text=text.replace('requires_openai_auth=false','requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0')
            path.write_text(text)
        try:
            with tempfile.TemporaryDirectory() as d, patch.object(codex_gateway,'write_config',local_config):
                root=Path(d);folder=root/'natural'/'actor';folder.mkdir(parents=True)
                events=queue.Queue();model='openai/gpt-6.1-sol'
                tools=[{'type':'function','name':'confirm_service','description':'Read service status.',
                        'parameters':{'type':'object','properties':{}}}]
                harness=codex_gateway.harness_registration('off',model)
                agent=run.codex_agent.CodexAgent('actor',events,folder=folder/'codex',
                    model=model,thinking_level='high',tools=tools,active_tools=['confirm_service'],
                    goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture',
                    registered_harness=harness)
                try:
                    ready=run.codex_agent.wait_ready(events,['actor'])['actor']
                    with self.assertRaisesRegex(RuntimeError,'fixture capture failure'):
                        with agent.record_guard():
                            raise RuntimeError('fixture capture failure')
                    agent.prompt('Service fixture request.')
                    native_path=Path(ready['session_file']);saved=[]
                    reply=agent.reply
                    def edit_then_reply(*args,**kwargs):
                        with agent.record_guard():
                            before=record_surface.read_regular(native_path.parent)
                            self.assertTrue(any(b'Service fixture request.' in b for b in before.values()))
                            after={name:data.replace(b'Service fixture request.',b'Edited fixture record.')
                                   for name,data in before.items()}
                            record_surface.apply_view(native_path.parent,before,after,writable=True,preserve_inode=True)
                            saved.append(native_path.read_bytes())
                        return reply(*args,**kwargs)
                    with patch.object(agent,'reply',side_effect=edit_then_reply):
                        NativeCodex().drain(agent,events,folder)
                    self.assertEqual(len(saved),1)
                    final=native_path.read_bytes()
                    self.assertIn(b'Edited fixture record.',final)
                    self.assertGreater(len(final),len(saved[0]))
                finally:agent.close()
                run.save(root/'registration.json',{'harness':harness})
                run.save(folder/'result.json',{'status':'collected','codex_session':ready})
                import export_atif
                result=export_atif.export_actor(root,'natural','actor')
                self.assertTrue(result['native_continuity_passed'])
                self.assertEqual(result['tool_results'],1)
                raw=[json.loads(p.read_text()) for p in (folder/'codex/native').glob('*.json')]
                self.assertFalse(any(x.get('message',{}).get('params',{}).get('item',{}).get('type')=='additional_tools' for x in raw))
                self.assertEqual(len(server.captures),2)
                for request in server.captures:
                    self.assertFalse(any(x.get('type')=='additional_tools' for x in request['input']))
                    self.assertEqual({t['name'] for t in request['tools'] if t['type']=='function'},set(codex_gateway.NATIVE_TOOLS))
                    namespaces=[t for t in request['tools'] if t['type']=='namespace']
                    self.assertEqual([t['name'] for t in namespaces],['mcp__work'])
                    self.assertEqual([t['name'] for t in namespaces[0]['tools']],['confirm_service'])
                    self.assertTrue(all(t['type'] in ('function','namespace') for t in request['tools']))
        finally:server.shutdown();server.server_close()

    def test_native_trace_preparation_freezes_harness_and_gateway(self):
        for model,harness,goal in [('anthropic/claude-haiku-5.5','claude-code','off'),('anthropic/claude-haiku-5.5','claude-code','claude_goal'),('openai/gpt-5.6-sol','codex','off')]:
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as d:
                root=Path(d).resolve(); key=root/'host-key';key.write_text('offline-fixture');key.chmod(0o600)
                registration=root/'registrations'/'native'
                with patch.object(run,'REGISTRATIONS',registration.parent), patch.object(run,'MODELS',{'model':model}), patch.object(run,'UPSTREAM_MODELS',{'model':model}), patch.object(run,'verify_routes',return_value={}), patch.object(run.claude_agent,'gateway_catalog',return_value={'model':model,'native_goal_available':True}):
                    run.prepare(root/'output',registration,key,run_controls=False,
                        scenario='knowledge-work',study_mode='phase2-component',
                        component_family='trace-integrity',harness_kind=harness,goal_mode=goal)
                prepared=json.loads((registration/'registration.json').read_text())
                self.assertEqual(prepared['harness']['kind'],harness)
                self.assertEqual(prepared['harness']['authentication'],'axonhub')
                if goal=='claude_goal':
                    self.assertEqual(prepared['native_subject_goal']['condition'],'native_claude_goal')
                    self.assertEqual(prepared['native_subject_goal']['settings']['goal_progress_guard'],
                                     run.claude_agent.GOAL_PROGRESS_GUARD)
                    self.assertEqual(prepared['harness']['input_delivery'],'atomic-sdk-goal-v1')
                    self.assertEqual(prepared['harness']['goal_evaluator']['model'],model)
                    self.assertIn('Claude native goal versus reference Codex native goal', prepared['reproduction']['harness_differences'])
                    self.assertNotIn('Claude goal off versus reference Codex native goal', prepared['reproduction']['harness_differences'])
                self.assertEqual(prepared['api_base'],codex_gateway.AXONHUB_BASE)
                self.assertTrue(prepared['live_collection_permitted'])
                if harness == 'codex':
                    self.assertIn('observed native response groups', prepared['harness']['request_count_scope'])
                    self.assertIn('native response completion', prepared['harness']['request_timeout_scope'])
                self.assertEqual(prepared['component_truth']['native_record_harness'],harness)
                self.assertNotIn('offline-fixture',(registration/'registration.json').read_text())

class CheckedControlsReuse(unittest.TestCase):
    def test_reuse_rejects_modified_result_source_and_runtime(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import run
        with TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source'; source.mkdir()
            controls={'passed':True,'prompt_contract_passed':True,'model_calls':0,'test_methods':1}
            run.save(source/'controls.json',controls)
            harness={'kind':'claude-code','installed':{'sdk':'fixture'},'goal_mode':'off'}
            reg={'code_hashes':{},'image':run.lab.IMAGE,'runtime':{'harbor_version':run.HARBOR_VERSION,
                 'python':run.sys.version.split()[0]},'harness':harness,'input_hashes':{'controls.json':run.sha(source/'controls.json')}}
            run.save(source/'registration.json',reg)
            run.save(source/'registration-seal.json',{'sha256':run.sha(source/'registration.json')})
            with patch.object(run,'code_paths',return_value=[]):
                self.assertTrue(run.reuse_checked_controls(source,harness)['passed'])
                with self.assertRaisesRegex(RuntimeError,'harness differs'):
                    run.reuse_checked_controls(source,{**harness,'goal_mode':'changed'})
                run.save(source/'controls.json',{**controls,'passed':False})
                with self.assertRaisesRegex(RuntimeError,'results changed'):
                    run.reuse_checked_controls(source,harness)
                run.save(source/'controls.json',controls)
                reg['code_hashes']={'different.py':'unmatched'}
                run.save(source/'registration.json',reg)
                run.save(source/'registration-seal.json',{'sha256':run.sha(source/'registration.json')})
                with self.assertRaisesRegex(RuntimeError,'source differs'):
                    run.reuse_checked_controls(source,harness)
