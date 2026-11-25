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
    def test_notice_confirmation_requires_new_matching_native_echo_in_request(self):
        from copy import deepcopy
        from tempfile import TemporaryDirectory
        text = '{"source":"platform_status","status":"The workspace state has changed."}'
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = 'native/000002.json'
            echo = {'direction': 'server', 'message': {
                'method': 'rawResponseItem/completed', 'params': {
                    'threadId': 'thread', 'turnId': 'turn', 'item': {
                        'type': 'message', 'role': 'user',
                        'content': [{'type': 'input_text', 'text': text}]}}}}
            run.save(folder/source, echo)
            request = {'session_id': 'thread', 'native_turn_id': 'turn',
                       'native_record': 'native/000003.json', 'native_input_records': [source],
                       'input': [{'role': 'user', 'content': text}]}
            self.assertEqual(run.codex_notice_echo(folder, request, text, set()), source)
            self.assertIsNone(run.codex_notice_echo(folder, request, text, {source}))
            self.assertIsNone(run.codex_notice_echo(folder, request, text, set(), 1))
            for field, value in [('session_id', 'other-thread'), ('native_turn_id', 'other-turn'),
                                 ('input', []), ('native_input_records', []),
                                 ('native_record', 'native/000001.json')]:
                changed = deepcopy(request); changed[field] = value
                self.assertIsNone(run.codex_notice_echo(folder, changed, text, set()))
            for field, value in [('direction', 'client'), ('method', 'turn/start')]:
                changed = deepcopy(echo)
                if field == 'method': changed['message'][field] = value
                else: changed[field] = value
                run.save(folder/source, changed)
                self.assertIsNone(run.codex_notice_echo(folder, request, text, set()))
            run.save(folder/source, echo)
            self.assertIsNone(run.codex_notice_echo(folder, request, 'another notice', set()))
            request['native_input_records'] = ['../escape.json']
            self.assertIsNone(run.codex_notice_echo(folder, request, text, set()))

    def test_queued_notice_never_acknowledges_missing_echo_or_rolls_back_reads(self):
        from copy import deepcopy
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            folder = Path(directory); text = 'status update'
            queued = {'step': 2, 'kind': 'relevant_platform_change', 'text': text,
                      'previous_inputs': [], 'previous_text_count': 0,
                      'previous_revision': 'old', 'signal': {'revision': 'new'},
                      'work_revision': 'work-new'}
            base = {'queued_platform_notice': queued,
                    'platform_notifications': [{'step': 2, 'delivery': 'queued'}]}
            request = {'session_id': 't', 'native_turn_id': 'u', 'native_record': 'native/000003.json',
                       'native_input_records': ['native/000002.json'], 'input': [{'role':'user','content':text}]}
            state=deepcopy(base); delivered={'revision':'old'}
            got, receipt = run.confirm_queued_codex_notice(state, delivered, folder, request)
            self.assertEqual(got, delivered);self.assertIsNone(receipt)
            self.assertIn('queued_platform_notice', state)
            self.assertNotIn('last_observed_work_revision', state)
            run.save(folder/'native/000002.json', {'direction':'server','message':{
                'method':'rawResponseItem/completed','params':{'threadId':'t','turnId':'u',
                    'item':{'type':'message','role':'user','content':[{'text':text}]}}}})
            got, receipt = run.confirm_queued_codex_notice(state, delivered, folder, request)
            self.assertEqual(got, {'revision':'new'});self.assertTrue(receipt['baseline_advanced'])
            self.assertNotIn('queued_platform_notice',state)
            self.assertEqual(state['platform_notifications'][0]['delivery'],'confirmed')
            self.assertEqual(state['last_observed_work_revision'],'work-new')
            state=deepcopy(base);state['last_observed_work_revision']='work-newer-read'
            state['last_followup_revision']='work-newer-read';delivered={'revision':'newer-read'}
            got, receipt=run.confirm_queued_codex_notice(state, delivered, folder, request)
            self.assertEqual(got,delivered);self.assertFalse(receipt['baseline_advanced'])
            self.assertEqual(state['last_observed_work_revision'],'work-newer-read')
            self.assertEqual(state['last_followup_revision'],'work-newer-read')

    def test_context_failure_keeps_raw_tail_without_projecting_summary_or_reset_usage(self):
        import threading
        from copy import deepcopy
        from codex_session import CodexAgent
        from codex_rpc import CodexRpc
        cases=[(boundary,closing) for boundary in ('item/started', 'item/completed', 'thread/compacted')
               for closing in (False,True)]
        for boundary,closing in cases:
            with self.subTest(boundary=boundary,closing=closing), tempfile.TemporaryDirectory() as directory:
                with patch('threading.Thread.start'):
                    agent=CodexAgent('actor',queue.Queue(),folder=directory,
                        model='openai/gpt-6.1-sol',thinking_level='high',tools=[],active_tools=[],
                        goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture')
                agent.thread_id='thread';agent.native_turn='turn'
                agent.stopping=closing
                pending_reply=queue.Queue();agent.replies['pending']=pending_reply
                rpc=CodexRpc.__new__(CodexRpc)
                rpc.folder=Path(directory);(rpc.folder/'native').mkdir()
                rpc.native_lock=threading.Lock();rpc.sequence=0
                history=deepcopy(agent.history)
                messages=[
                    {'method':boundary,'params':{'threadId':'thread','item':{'type':'contextCompaction'}}},
                    {'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'last':{'inputTokens':300000}}}},
                    {'method':'rawResponseItem/completed','params':{'item':{'type':'message','role':'assistant',
                        'content':[{'type':'output_text','text':'Private context summary.'}]}}},
                    {'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'last':{'inputTokens':0}}}},
                    {'method':'turn/completed','params':{'turn':{'id':'turn','status':'completed'}}},
                ]
                for message in messages:
                    source=rpc.record('server',message)
                    agent._notification(message,source)
                emitted=[]
                while not agent.events.empty():emitted.append(agent.events.get_nowait()[1])
                self.assertEqual([x['type'] for x in emitted],['native_context_transition','fatal'])
                self.assertEqual(emitted[0]['native_record'],'native/000001.json')
                self.assertEqual(agent.history,history)
                self.assertEqual(agent.turn,0)
                self.assertEqual(pending_reply.get_nowait(),{'aborted':True})
                self.assertTrue(pending_reply.empty())
                self.assertEqual([json.loads(p.read_text())['message']
                    for p in sorted((rpc.folder/'native').glob('*.json'))],messages)

    def test_normal_shutdown_still_projects_late_usage(self):
        from codex_session import CodexAgent
        with tempfile.TemporaryDirectory() as directory, patch('threading.Thread.start'):
            agent=CodexAgent('actor',queue.Queue(),folder=directory,
                model='openai/gpt-6.1-sol',thinking_level='high',tools=[],active_tools=[],
                goal_mode='off',api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture')
            agent.stopping=True
            agent._notification({'method':'thread/tokenUsage/updated','params':{
                'tokenUsage':{'last':{'inputTokens':19,'outputTokens':2}}}},'native/000001.json')
            values=[]
            while not agent.events.empty():values.append(agent.events.get_nowait()[1])
            response=next(x for x in values if x['type']=='provider_response')
            self.assertEqual(response['event']['response']['usage']['input_tokens'],19)
            self.assertFalse(agent.failed)

    def test_codex_long_response_progress_does_not_extend_hard_completion_limit(self):
        import threading
        from codex_session import CodexAgent
        agent=CodexAgent.__new__(CodexAgent)
        agent.context=None
        agent.lock=threading.RLock();agent.active=True
        agent.timeout=1800;agent.idle_timeout=600
        agent.last_progress=agent.last_activity=0
        for now in (400,800,1200,1600):
            with patch('codex_session.time.monotonic',return_value=now):
                agent._observe_response_activity('item/reasoning/textDelta',{'delta':'new content'})
                agent._check_response_deadline()
        self.assertEqual(agent.last_progress,0)
        with patch('codex_session.time.monotonic',return_value=1801):
            agent._observe_response_activity('item/reasoning/textDelta',{'delta':'still streaming'})
            with self.assertRaisesRegex(TimeoutError,'completion timed out'):
                agent._check_response_deadline()

    def test_codex_idle_watchdog_ignores_empty_deltas_retries_and_heartbeats(self):
        import threading
        from codex_session import CodexAgent
        agent=CodexAgent.__new__(CodexAgent)
        agent.context=None
        agent.lock=threading.RLock();agent.active=True
        agent.timeout=1800;agent.idle_timeout=600
        agent.last_progress=agent.last_activity=0
        with patch('codex_session.time.monotonic',return_value=601):
            for method,params in [('item/reasoning/textDelta',{'delta':''}),
                                  ('error',{'willRetry':True}),('heartbeat',{})]:
                agent._observe_response_activity(method,params)
            with self.assertRaisesRegex(TimeoutError,'progress timed out'):
                agent._check_response_deadline()
            agent.idle_timeout=None
            agent._check_response_deadline()  # Historical completion-only behavior.

    def test_codex_exception_cleanup_retains_native_bytes_and_original_failure(self):
        from unittest.mock import Mock
        from codex_session import CodexAgent
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);agent=CodexAgent.__new__(CodexAgent)
            agent.context=None
            agent.home=root/'home';(agent.home/'sessions').mkdir(parents=True)
            native=agent.home/'sessions/rollout-thread.jsonl';native.write_text('{"partial":true}\n')
            agent.folder=root/'retained';agent.folder.mkdir()
            workspace=root/'workspace';workspace.mkdir();(workspace/'partial.txt').write_text('work')
            agent.actor='actor';agent.events=queue.Queue();agent.commands=queue.Queue()
            agent.replies={};agent.failed=agent.stopping=False
            agent.thread_id='thread';agent.native_turn='turn';agent.active=True
            agent.rpc=Mock();agent.rpc.request.side_effect=RuntimeError('transport unavailable')
            self.assertFalse(agent._export_on_exit(workspace,TimeoutError('original deadline')))
            self.assertEqual(agent.events.get_nowait()[1]['message'],'original deadline')
            self.assertEqual((agent.folder/'session.jsonl').read_bytes(),native.read_bytes())
            self.assertEqual((agent.folder/'workspace/partial.txt').read_text(),'work')
            report=json.loads((agent.folder/'export-status.json').read_text())
            self.assertEqual(set(report['errors']),{'interrupt','thread'})

    def test_codex_reconnect_keeps_turn_history_and_original_deadline(self):
        from copy import deepcopy
        import threading
        from codex_session import CodexAgent
        agent = CodexAgent.__new__(CodexAgent)
        agent.context = None
        agent.lock = threading.RLock()
        agent.actor, agent.thread_id, agent.turn = 'actor', 'thread', 3
        agent.events, agent.commands = queue.Queue(), queue.Queue()
        agent.active, agent.failed, agent.stopping = True, False, False
        agent.last_progress, agent.response_open = 123, False
        agent.goal_mode, agent.final_text = 'off', 'Finished after reconnection.'
        agent.history = [{'role':'user','content':'Prepare the report.'}]
        before = deepcopy(agent.history)
        agent._notification({'method':'error','params':{
            'threadId':'thread','willRetry':True,'error':{
                'codexErrorInfo':{'responseStreamDisconnected':{'httpStatusCode':None}},
                'message':'Reconnecting... waiting for network','misalignment':None}}},
            'native/000042.json')
        _, notice = agent.events.get_nowait()
        self.assertEqual(notice['type'], 'native_transport_error')
        self.assertTrue(notice['recovering'])
        self.assertEqual(notice['native_record'], 'native/000042.json')
        self.assertTrue(agent.active)
        self.assertFalse(agent.failed)
        self.assertEqual(agent.history, before)
        self.assertEqual(agent.last_progress, 123)
        self.assertTrue(agent.commands.empty())
        agent._notification({'method':'turn/completed','params':{
            'threadId':'thread','turn':{'id':'turn','status':'completed'}}},
            'native/000043.json')
        self.assertEqual(agent.events.get_nowait()[1]['type'], 'settled')
        self.assertFalse(agent.active)

    def test_codex_terminal_and_non_network_errors_still_stop(self):
        import threading
        from codex_session import CodexAgent
        for retry, info, flag in (
            (False, {'responseStreamDisconnected':{}}, None),
            (True, 'unauthorized', None),
            (True, 'badRequest', None),
            (True, {'responseStreamDisconnected':{}}, {'category':'flagged'}),
        ):
            with self.subTest(retry=retry, info=info, flag=flag):
                agent = CodexAgent.__new__(CodexAgent)
                agent.context = None
                agent.lock = threading.RLock()
                agent.actor, agent.thread_id, agent.turn = 'actor', 'thread', 1
                agent.events, agent.commands = queue.Queue(), queue.Queue()
                agent.failed, agent.stopping, agent.replies = False, False, {}
                agent._notification({'method':'error','params':{
                    'threadId':'thread','willRetry':retry,'error':{
                        'codexErrorInfo':info,'misalignment':flag}}},
                    'native/000007.json')
                self.assertFalse(agent.events.get_nowait()[1]['recovering'])
                self.assertEqual(agent.events.get_nowait()[1]['type'], 'fatal')
                self.assertTrue(agent.failed)
                self.assertEqual(agent.commands.get_nowait(), ('close', None))

    def test_native_gateway_recovers_interrupted_stream_without_repeating_tools(self):
        from http.server import ThreadingHTTPServer
        import socket
        import threading
        from tests.codex_collect_checks import ScriptedResponses, NativeCodex
        class InterruptedOnce(ScriptedResponses):
            def do_POST(self):
                # Interrupt the next response after the business tool has run.
                if len(self.server.captures) == 1 and not self.server.disconnected:
                    self.server.disconnected = True
                    self.server.failed_request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    self.wfile.write(b'event: response.created\ndata: {"type":"response.created","response":{"id":"interrupted"}}\n\n')
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                super().do_POST()
        server = ThreadingHTTPServer(('127.0.0.1',0), InterruptedOnce)
        server.disconnected, server.captures, server.capture_lock = False, [], threading.Lock()
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original = codex_gateway.write_config
        def local_config(home,*args):
            original(home,*args)
            path = home/'config.toml'
            text = path.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1')
            path.write_text(text.replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=1'))
        try:
            with tempfile.TemporaryDirectory() as d, patch.object(codex_gateway,'write_config',local_config):
                folder = Path(d)/'actor'; folder.mkdir()
                events = queue.Queue()
                tools = [{'type':'function','name':'confirm_service','description':'Read service status.',
                          'parameters':{'type':'object','properties':{}}}]
                agent = run.codex_agent.CodexAgent('actor',events,folder=folder/'codex',
                    model='openai/gpt-5.6-sol',thinking_level='high',tools=tools,
                    active_tools=['confirm_service'],goal_mode='off',
                    api_base=codex_gateway.AXONHUB_BASE,api_key='offline-fixture')
                try:
                    run.codex_agent.wait_ready(events,['actor'])
                    agent.prompt('Service fixture request.')
                    result = NativeCodex().drain(agent,events,folder)
                    self.assertFalse(result['aborted'])
                finally: agent.close()
                raw = [json.loads(p.read_text()) for p in (folder/'codex/native').glob('*.json')]
                errors = [x['message']['params'] for x in raw if x['message'].get('method')=='error']
                self.assertTrue(any(x['willRetry'] for x in errors))
                self.assertEqual(len(server.captures),2)
                self.assertEqual(server.failed_request['input'],server.captures[1]['input'])
                self.assertTrue(any(item.get('type') == 'function_call_output'
                                    for item in server.failed_request['input']))
                self.assertEqual(len(list((folder/'trace').glob('*-tool-*.json'))),1)
        finally: server.shutdown(); server.server_close()

    def test_codex_default_uses_path_and_reports_a_missing_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'codex'
            binary.write_text('fixture executable')
            with patch.dict('os.environ', {}, clear=True), \
                    patch('shutil.which', return_value=str(binary)) as which:
                self.assertEqual(codex_gateway.codex_binary(), str(binary.resolve()))
                which.assert_called_once_with('codex')
                binary.unlink()
                with self.assertRaisesRegex(RuntimeError, 'install codex on PATH'):
                    codex_gateway.codex_binary()

    def test_explicit_codex_override_does_not_silently_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'codex'
            binary.write_text('fixture executable')
            with patch.dict('os.environ', {'SWARMHARM_NATIVE_CODEX': str(binary)}):
                self.assertEqual(codex_gateway.codex_binary(), str(binary.resolve()))
                binary.unlink()
                with self.assertRaisesRegex(RuntimeError, 'missing'):
                    codex_gateway.codex_binary()

    def test_npm_codex_launcher_resolves_to_the_native_process(self):
        for layout in ('nested', 'hoisted', 'bundled'):
            with tempfile.TemporaryDirectory() as directory:
                packages = Path(directory) / 'node_modules/@openai'
                pkg_root = packages / 'codex'
                launcher = pkg_root / 'bin/codex.js'
                launcher.parent.mkdir(parents=True)
                launcher.write_text('fixture launcher')
                for system, machine, package, triple in (
                    ('Darwin', 'arm64', 'darwin-arm64', 'aarch64-apple-darwin'),
                    ('Darwin', 'x86_64', 'darwin-x64', 'x86_64-apple-darwin'),
                    ('Linux', 'aarch64', 'linux-arm64', 'aarch64-unknown-linux-musl'),
                    ('Linux', 'x86_64', 'linux-x64', 'x86_64-unknown-linux-musl'),
                ):
                    vendor = {
                        'nested': pkg_root / f'node_modules/@openai/codex-{package}/vendor',
                        'hoisted': packages / f'codex-{package}/vendor',
                        'bundled': pkg_root / 'vendor',
                    }[layout]
                    binary = vendor / f'{triple}/bin/codex'
                    with self.subTest(layout=layout, platform=package), patch.dict('os.environ', {'SWARMHARM_NATIVE_CODEX': str(launcher)}), \
                            patch.object(codex_gateway.platform, 'system', return_value=system), \
                            patch.object(codex_gateway.platform, 'machine', return_value=machine):
                        with self.assertRaisesRegex(RuntimeError, 'package is missing'):
                            codex_gateway.codex_binary()
                        binary.parent.mkdir(parents=True, exist_ok=True)
                        binary.write_text('fixture executable')
                        self.assertEqual(codex_gateway.codex_binary(), str(binary.resolve()))
                        binary.unlink()

    def test_malformed_call_does_not_block_a_valid_retry_or_count_as_execution(self):
        import threading
        from codex_session import CodexAgent, argument_value
        for raw in ('{', 'null', '[]', '"text"', '42'):
            with self.subTest(arguments=raw):
                agent = CodexAgent.__new__(CodexAgent)
                agent.context = None
                agent.stopping = False
                agent.thread_id = 'fixture'
                agent.active_tools = {'read_status'}
                agent.call_ready = threading.Condition()
                agent.calls = {
                    'invalid': {'business': True, 'claimed': False,
                        'item': {'name': 'read_status', 'arguments': raw}},
                    'valid': {'business': True, 'claimed': False,
                        'item': {'name': 'read_status', 'arguments': '{}'}},
                }
                with agent.call_ready:
                    identity, call = agent._match_call({'name': 'read_status', 'arguments': {}})
                    self.assertEqual(identity, 'valid')
                    self.assertFalse(agent.calls['invalid']['claimed'])
                    with self.assertRaisesRegex(RuntimeError, 'differs from'):
                        agent._match_call({'name': 'read_status', 'arguments': {},
                                          '_meta': {'callId': 'invalid'}})
                self.assertIsInstance(json.dumps(argument_value(raw)), str)
        self.assertNotEqual(argument_value('{'), argument_value('"{"'))
        self.assertEqual(argument_value('{"a":1,"b":2}'), argument_value('{"b":2,"a":1}'))

    def test_goal_defaults_off_and_preserves_explicit_historical_modes(self):
        for harness, goal in [('codex','codex_goal'),('claude-code','claude_goal'),('pi-sdk','goal_command')]:
            self.assertEqual(run.guardrails.resolve_goal_mode(harness),'off')
            self.assertEqual(run.guardrails.resolve_goal_mode(harness,'off'),'off')
            self.assertEqual(run.guardrails.resolve_goal_mode(harness,goal),goal)
            self.assertEqual(run.guardrails.resolve_goal_mode(harness,offline_fixture=True),'off')
            self.assertEqual(run.guardrails.resolve_goal_mode(harness,goal,offline_fixture=True),goal)
            wrong = 'claude_goal' if harness != 'claude-code' else 'codex_goal'
            with self.assertRaisesRegex(ValueError,'does not match'):
                run.guardrails.resolve_goal_mode(harness,wrong)
        with self.assertRaisesRegex(ValueError,'Unknown agent harness'):
            run.guardrails.resolve_goal_mode('unregistered')

    @patch.object(run.pi_agent, 'installed_versions', return_value={
        '@earendil-works/pi-coding-agent': run.pi_agent.PI_VERSION,
        run.pi_agent.GOAL_PACKAGE: run.pi_agent.GOAL_VERSION})
    @patch.object(run.claude_agent, 'installed_versions', return_value={
        '@anthropic-ai/claude-agent-sdk': run.claude_agent.SDK_VERSION})
    @patch.object(run.claude_agent, 'cli_identity', return_value={
        'version': '2.1.304 (offline settings fixture)', 'sha256': '0'*64})
    def test_all_harnesses_reject_registered_settings_drift(self, *_installation_fixtures):
        # Settings validation is independent of optional Pi/Claude installation.
        # Their actual binaries are checked by their own selected harness suites.
        from copy import deepcopy
        registrations = [
            (run.pi_agent,run.pi_agent.harness_registration('goal_command'),'goal_settings'),
            (run.claude_agent,run.claude_agent.gateway_registration('anthropic/claude-haiku-5.5','claude_goal'),'settings'),
            (codex_gateway,codex_gateway.harness_registration('codex_goal','openai/gpt-5.6-sol'),'tool_profile'),
        ]
        for adapter, original, field in registrations:
            with self.subTest(adapter=adapter.__name__):
                adapter.verify_runtime(original)
                prepared=run.guardrails.controller_harness(original)
                adapter.verify_runtime(prepared)
                prepared['input_projection']['business_task']='system'
                with self.assertRaisesRegex(RuntimeError,'Harness settings changed'):
                    adapter.verify_runtime(prepared)
                changed=deepcopy(original);changed[field]['unregistered_setting']=True
                with self.assertRaisesRegex(RuntimeError,'Harness settings changed'):
                    adapter.verify_runtime(changed)
                changed=deepcopy(original);changed['unregistered_field']=True
                with self.assertRaisesRegex(RuntimeError,'Harness settings changed'):
                    adapter.verify_runtime(changed)

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

    def test_family_defaults_never_fall_back_to_pi(self):
        self.assertEqual(run.guardrails.native_harness({'model':'openai/gpt-5.6-sol'}),'codex')
        self.assertEqual(run.guardrails.native_harness({'model':'anthropic/claude-haiku-5.5'}),'claude-code')
        with self.assertRaises(ValueError):
            run.guardrails.native_harness({'model':'unsupported/model'})
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run.save(root/'registration.json',{'models':{'model':'unsupported/model'},'harness':{'kind':'pi-sdk'}})
            with patch.object(run,'REGISTRATIONS',root/'regs'), self.assertRaisesRegex(ValueError,'explicit Sol 5.6 Pi comparison'):
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
        custom = codex_gateway.gateway_env('/tmp/isolated-test','https://other.example/v1','fixture-key')
        self.assertEqual(custom['SWARMHARM_AXONHUB_KEY'], 'fixture-key')
        self.assertNotIn('OPENAI_API_KEY', custom)
        with self.assertRaises(ValueError):
            codex_gateway.gateway_env('/tmp/isolated-test','https://user:secret@other.example/v1','fixture-key')

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

class CheckedControlsReuse(unittest.TestCase):
    def test_mechanism_preparation_selects_current_paths_and_registered_adapter(self):
        selected = {p.stem for p in run.preparation_check_paths('codex', mechanism='shared-capacity')}
        self.assertTrue({'mechanism_inputs_checks', 'mechanism_review_checks',
                         'codex_collect_checks', 'unified_runtime_checks'} <= selected)
        self.assertFalse({'pi_collect_checks', 'claude_collect_checks', 'live_checks',
                          'native_goal_checks', 'engineering_checks'} & selected)
        retained = {p.stem for p in run.preparation_check_paths('codex')}
        self.assertTrue(selected < retained)

    def test_controls_normalize_only_declared_model_selectors(self):
        from copy import deepcopy
        first={'kind':'claude-code','environment':{'ANTHROPIC_MODEL':'haiku','DISABLE_COMPACT':'1'},
               'accepted_native_model_ids':['haiku'], 'goal_evaluator':{'model':'haiku','implementation':'native'},
               'goal_progress_guard':{'turns':2}}
        second=deepcopy(first);second['environment']['ANTHROPIC_MODEL']='sonnet'
        second['accepted_native_model_ids']=['sonnet'];second['goal_evaluator']['model']='sonnet'
        self.assertEqual(run.control_harness_contract(first),run.control_harness_contract(second))
        second['environment']['DISABLE_COMPACT']='0'
        self.assertNotEqual(run.control_harness_contract(first),run.control_harness_contract(second))


    def test_reuse_rejects_modified_result_source_and_runtime(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import run
        with TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source'; source.mkdir()
            controls={'passed':True,'prompt_contract_passed':True,'model_calls':0,'test_methods':1,
                      'check_modules':['tests/format_checks.py','tests/unified_runtime_checks.py']}
            run.save(source/'controls.json',controls)
            harness={'kind':'claude-code','installed':{'sdk':'fixture'},'goal_mode':'off'}
            reg={'code_hashes':{},'image':run.lab.IMAGE,'runtime':{'harbor_version':run.HARBOR_VERSION,
                 'python':run.sys.version.split()[0]},'harness':harness,'input_hashes':{'controls.json':run.sha(source/'controls.json')}}
            run.save(source/'registration.json',reg)
            run.save(source/'registration-seal.json',{'sha256':run.sha(source/'registration.json')})
            with patch.object(run,'code_paths',return_value=[]):
                self.assertTrue(run.reuse_checked_controls(source,harness,[run.HERE/'tests/format_checks.py'])['passed'])
                with self.assertRaisesRegex(RuntimeError,'lack required modules'):
                    run.reuse_checked_controls(source,harness,[run.HERE/'tests/engineering_target_collector_checks.py'])
                with self.assertRaisesRegex(RuntimeError,'coverage is missing'):
                    run.reuse_checked_controls(source,harness,[])
                with self.assertRaisesRegex(RuntimeError,'harness differs'):
                    run.reuse_checked_controls(source,{**harness,'goal_mode':'changed'},[run.HERE/'tests/format_checks.py'])
                for field in ('codex_cli','goal_progress_guard','goal_settings','settings','tool_profile','native_catalog_sha256'):
                    with self.subTest(field=field), self.assertRaisesRegex(RuntimeError,'harness differs'):
                        run.reuse_checked_controls(source,{**harness,field:{'changed':True}},[run.HERE/'tests/format_checks.py'])
                run.save(source/'controls.json',{**controls,'passed':False})
                with self.assertRaisesRegex(RuntimeError,'results changed'):
                    run.reuse_checked_controls(source,harness,[run.HERE/'tests/format_checks.py'])
                run.save(source/'controls.json',controls)
                reg['code_hashes']={'different.py':'unmatched'}
                run.save(source/'registration.json',reg)
                run.save(source/'registration-seal.json',{'sha256':run.sha(source/'registration.json')})
                with self.assertRaisesRegex(RuntimeError,'source differs'):
                    run.reuse_checked_controls(source,harness,[run.HERE/'tests/format_checks.py'])
