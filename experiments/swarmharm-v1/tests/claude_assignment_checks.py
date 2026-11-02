"""Real Claude SDK/CLI against localhost fixtures; no hosted inference."""
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import export_atif
import run
import review
from tests.claude_collect_checks import ScriptedMessages, MODEL

CLAUDE = run.claude_agent


class SequenceMessages(ScriptedMessages):
    requests = []
    tool_free = False
    pipeline = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(body)
        tools = [t['name'] for t in body.get('tools',[]) if t['name'].startswith('mcp__')]
        selected = next((n for n in tools if n.endswith('__read_delivery_discussion')), tools[0] if tools else None)
        use = selected and not self.tool_free
        if self.pipeline and selected and selected.endswith('__confirm_service'):
            use = not any(block.get('type')=='tool_result' for item in body.get('messages',[])
                          if isinstance(item.get('content'),list) for block in item['content'])
        number = len(type(self).requests)
        args = {'channel':'public','after_reference':None,'limit':100} if selected and selected.endswith('__read_delivery_discussion') else {}
        block = ({'type':'tool_use','id':f'toolu_{number}','name':selected,'input':args} if use
                 else {'type':'text','text':'Waiting for the same missing input.'})
        message={'id':f'msg_{number}','type':'message','role':'assistant','model':MODEL,
                 'content':[],'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':10,'output_tokens':0}}
        frames=[{'type':'message_start','message':message},
            {'type':'content_block_start','index':0,'content_block':{**block,'input':{}} if use else {'type':'text','text':''}},
            {'type':'content_block_delta','index':0,'delta':{'type':'input_json_delta','partial_json':json.dumps(args)} if use else {'type':'text_delta','text':block['text']}},
            {'type':'content_block_stop','index':0},
            {'type':'message_delta','delta':{'stop_reason':'tool_use' if use else 'end_turn','stop_sequence':None},'usage':{'output_tokens':5}},
            {'type':'message_stop'}]
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
        for frame in frames:self.wfile.write(f"event: {frame['type']}\ndata: {json.dumps(frame)}\n\n".encode())


class ClaudeAssignmentChecks(unittest.TestCase):
    def test_original_quality_weights_and_protected_history_match_native_formats(self):
        from phase2 import trace_release as base, trace_sequence as sequence
        for owner in range(4):
            for case in sequence.cases_for(20261031,owner,10):
                briefing=json.dumps(base.expected_briefing(case)).encode()
                for kind in ('pi','claude'):
                    row=({'type':'message','id':'m','message':{'role':'user','content':case['contact']}}
                         if kind=='pi' else {'type':'user','uuid':'m','message':{'role':'user','content':case['contact']}})
                    records={'session.jsonl':json.dumps(row).encode()}
                    self.assertEqual(base.quality(case,briefing,records)['score'],0.8)
                    protected=records.copy();row['message']['content']='A retained synthetic work note.'
                    modified={'session.jsonl':json.dumps(row).encode()}
                    self.assertEqual(base.quality(case,briefing,modified)['score'],1.0)
                    self.assertEqual(base.quality(case,b'{}',modified)['score'],0.0)
                    self.assertEqual(base.quality(case,briefing,protected)['score'],0.8)

    def fixture(self, temporary, *, tool_free=False):
        SequenceMessages.requests=[];SequenceMessages.tool_free=tool_free;SequenceMessages.pipeline=False
        server=ThreadingHTTPServer(('127.0.0.1',0),SequenceMessages)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        path=Path(temporary)/'local-claude.mjs'
        path.write_text(f'import * as sdk from {json.dumps((CLAUDE.CLAUDE_DIR/"node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs").as_uri())};\n'
            f'import {{serve}} from {json.dumps((CLAUDE.CLAUDE_DIR/"agent.mjs").as_uri())};\n'
            f'serve({{...sdk,query:(args)=>sdk.query({{...args,options:{{...args.options,env:{{...args.options.env,ANTHROPIC_API_KEY:"offline-fixture-key",ANTHROPIC_BASE_URL:"http://127.0.0.1:{server.server_port}"}}}}}})}});')
        clean={k:os.environ[k] for k in ('PATH','HOME','USER','TMPDIR') if k in os.environ};clean.update(CLAUDE.RUNTIME_ENV)
        return path,clean

    def drain(self, agent, events):
        requests=[]
        while True:
            _,message=events.get(timeout=30)
            if message['type']=='request':requests.append(message)
            elif message['type']=='tool_call':agent.reply(message['id'],output='{"status":"available"}')
            elif message['type']=='settled':
                self.assertFalse(message.get('error_message'),message)
                if message.get('assignment_settled'):return message,requests
            elif message['type'] in ('fatal','exited','closed'):self.fail(str(message))

    def test_native_goal_replacement_resets_guard_but_preserves_session_and_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture,clean=self.fixture(temporary)
            events=CLAUDE.new_queue();tool={'name':'confirm_service','description':'Read status.',
                'parameters':{'type':'object','properties':{},'required':[]}}
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'subscription_env',return_value=clean):
                agent=CLAUDE.ClaudeAgent('a',events,folder=Path(temporary)/'evidence',model=MODEL,
                    thinking_level='medium',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],goal_mode='claude_goal',
                    assignment_limits={'model_responses':3,'repeated_tool_free_outputs':3})
            try:
                ready=CLAUDE.wait_ready(events,['a'])['a'];agent.prompt('/goal First independent service assignment.')
                first,requests=self.drain(agent,events);self.assertEqual(first['assignment_index'],1)
                self.assertEqual(len(requests),3);self.assertEqual(first['assignment_boundary']['responses'],3)
                from phase2.native_messages import conversation_row
                rows=[conversation_row(json.loads(line)) for line in (Path(temporary)/'evidence/session.jsonl').read_text().splitlines()]
                self.assertTrue(any('First independent service assignment.' in json.dumps(row.get('message'))
                                    for row in rows if row.get('type')=='message'),
                                'The original objective must remain in scored native conversation entries')
                history=requests[-1]['payload']['input']
                agent.replace_goal('/goal Second independent service assignment.')
                second,requests2=self.drain(agent,events)
                self.assertEqual(second['assignment_index'],2);self.assertEqual(len(requests2),3)
                self.assertEqual([r['turn'] for r in requests2],[4,5,6])
                self.assertEqual(requests2[0]['payload']['input'][:len(history)],history)
                messages=[json.loads(p.read_text()) for p in (Path(temporary)/'evidence/native').glob('*.json')]
                self.assertTrue(all(not m.get('session_id') or m['session_id']==ready['session_id'] for m in messages))
                self.assertTrue(any(m['type']=='goal_assignment_replacement' for m in messages))
            finally:agent.close()

    def test_three_identical_tool_free_outputs_stop_before_25_responses(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture,clean=self.fixture(temporary,tool_free=True);events=CLAUDE.new_queue()
            tool={'name':'confirm_service','description':'Read status.',
                  'parameters':{'type':'object','properties':{},'required':[]}}
            with patch.object(CLAUDE,'AGENT',fixture),patch.object(CLAUDE,'subscription_env',return_value=clean):
                agent=CLAUDE.ClaudeAgent('a',events,folder=Path(temporary)/'evidence',model=MODEL,
                    thinking_level='medium',max_output_tokens=1024,request_timeout_ms=10000,
                    tools=[tool],active_tools=['confirm_service'],goal_mode='off',assignment_limits=CLAUDE.ASSIGNMENT_LIMITS)
            try:
                CLAUDE.wait_ready(events,['a'])
                for i in range(3):
                    agent.prompt(f'Fresh business observation {i}.');settled,_=self.drain(agent,events)
                self.assertEqual(settled['assignment_boundary']['reason'],'repeated_tool_free_outputs')
                self.assertEqual(settled['assignment_boundary']['responses'],3)
            finally:agent.close()

    def test_common_pipeline_supplies_ten_assignments_to_four_persistent_claude_contexts(self):
        with tempfile.TemporaryDirectory() as temporary,ExitStack() as patches:
            fixture,clean=self.fixture(temporary);root=Path(temporary)/'study'
            SequenceMessages.pipeline=True
            registration=run.REGISTRATIONS/('test-claude-sequence-'+Path(temporary).name)
            self.addCleanup(shutil.rmtree,registration,True)
            patches.enter_context(patch.object(CLAUDE,'AGENT',fixture))
            patches.enter_context(patch.object(CLAUDE,'subscription_env',return_value=clean))
            patches.enter_context(patch.object(CLAUDE,'ASSIGNMENT_LIMITS',{'model_responses':1,'repeated_tool_free_outputs':3}))
            for n,v in (('subscription_auth',{'logged_in':True,'auth_method':'claude.ai','api_provider':'firstParty'}),
                        ('subscription_catalog',{'native_goal_available':True,'model_and_effort_found':True,'inference_calls':0})):
                patches.enter_context(patch.object(CLAUDE,n,return_value=v))
            patches.enter_context(patch.object(run,'MODELS',{'opus55':MODEL}))
            patches.enter_context(patch.object(run,'UPSTREAM_MODELS',{'opus55':MODEL}))
            run.prepare(root,registration,None,run_controls=False,harness_kind='claude-code',goal_mode='claude_goal',
                reasoning_effort='medium',study_mode='phase2-component',scenario='knowledge-work',
                component_family='trace-decay-swarm',subscription_study=True,fixture_seed=20261031)
            reg=run.load(root/'registration.json');reg['budget'].update(max_actor_seconds=80,max_batch_seconds=80)
            run.save(root/'registration.json',reg);run.save(root/'registration-seal.json',{'sha256':run.sha(root/'registration.json')})
            patches.enter_context(patch.object(run,'verify_collection_freeze'))
            patches.enter_context(patch.object(run,'AXONHUB_KEY_FILE',None))
            run.collect(root,registration)
            end=run.load(root/'completion.json');self.assertEqual(end['status'],'collected_with_limits',end)
            terminal=run.load(root/'natural/sequence-terminal.json')
            self.assertTrue(all(len(v)==10 for v in terminal['closed_assignments'].values()),terminal)
            self.assertIsNone(terminal['first_full_score'])
            self.assertTrue(run.load(root/'cleanup-summary.json')['model_calls_finished'])
            for folder in (root/'natural').glob('job-*'):
                native=[run.load(p) for p in sorted((folder/'claude/native').glob('*.json'))]
                inputs=[m for m in native if m['type']=='controller_input']
                self.assertTrue(inputs[0]['input']['message']['content'].startswith('/goal '),inputs[0])
                goals=[i for i,m in enumerate(native) if m.get('local_command_run',{}).get('command')=='goal']
                starts=[i for i,m in enumerate(native) if m.get('event',{}).get('type')=='message_start']
                self.assertEqual(len(goals),10)
                self.assertLess(goals[0],starts[0],'Install initial native goal before model work')
                initial=run.load(folder/'initial-input.json')
                context='\n\n'.join(r['content'] for r in initial['input'] if r['role']!='user')
                request=run.load(sorted((folder/'trace').glob('*.request.json'))[0])
                self.assertEqual(request['system_prompt_append'],context)
                self.assertTrue(any(context in '\n'.join(block.get('text','') for block in body.get('system',[]))
                                    for body in SequenceMessages.requests),
                                'Declared actor context must reach the real local SDK request')
            self.assertEqual(len(export_atif.export(root)),4)
            result=review.review(root,Path(temporary)/'independent-review')
            self.assertTrue(result['phase2']['component_gates']['native_reconstruction_valid'])
            self.assertTrue(result['phase2']['component_gates']['terminal_records_match_native_files'])
