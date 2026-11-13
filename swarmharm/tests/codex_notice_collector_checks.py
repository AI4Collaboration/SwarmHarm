"""Concurrent Codex collector tests with a loopback scripted provider only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import codex_gateway
import export_atif
import run
from phase1 import lab
from phase2 import unified_delivery


class ScriptedNoticeResponses(BaseHTTPRequestHandler):
    def log_message(self, *unused):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        users = [(i, item) for i, item in enumerate(request['input']) if item.get('role') == 'user']
        first = '\n'.join(part.get('text', '') for _, row in users for part in row['content'])
        actor = next((name for name in ('Northline', 'Aster', 'Harbor', 'Meridian') if name in first), None)
        last_index, last = users[-1]
        text = '\n'.join(part.get('text', '') for part in last['content'])
        outputs = sum(item.get('type') == 'function_call_output' for item in request['input'][last_index+1:])
        is_notice = '"source": "platform_status"' in text
        mode = self.server.mode
        call = None
        if actor is None and 'confirm_service' in json.dumps(request.get('tools',[])):
            if outputs == 0:call=('confirm_service',{})
        elif actor == 'Northline':
            if not is_notice and outputs == 0:
                call = ('bash', {'command': 'printf tool-finished'})
            elif not is_notice and mode == 'read' and outputs == 1:
                call = ('delivery_desk', {})
            elif is_notice and mode == 'race' and outputs == 0:
                self.server.notice_started.set()
                if not self.server.second_change.wait(30):
                    raise RuntimeError('Timed out awaiting peer change')
                call = ('delivery_desk', {})
        elif actor == 'Aster' and not is_notice:
            if outputs == 0:
                if not self.server.tool_started.wait(30):
                    raise RuntimeError('Timed out awaiting active tool')
                if mode == 'reverted':
                    call = ('bash', {'command': "printf update > /registry/reporting/cache/test.md"})
                else:
                    call = ('execute_dispatch', {'revision': 1})
            elif mode == 'reverted' and outputs == 1:
                call = ('bash', {'command': 'rm /registry/reporting/cache/test.md'})
            elif mode == 'race' and outputs == 1:
                if not self.server.notice_started.wait(30):
                    raise RuntimeError('Timed out awaiting notice request')
                call = ('cancel_dispatch_item', {'item':'summary'})
        with self.server.guard:
            self.server.sequence += 1
            identity = self.server.sequence
        if call:
            name, args = call
            item = {'type':'function_call','name':name,'namespace':'mcp__work',
                    'call_id':f'fixture-{identity}','arguments':json.dumps(args)}
        else:
            item = {'type':'message','id':f'message-{identity}','role':'assistant',
                    'phase':'final_answer','content':[{'type':'output_text','text':'Fixture complete.'}]}
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
        for event in ({'type':'response.created','response':{'id':f'response-{identity}'}},
                      {'type':'response.output_item.done','output_index':0,'item':item},
                      {'type':'response.completed','response':{'id':f'response-{identity}',
                       'status':'completed','model':'openai/gpt-6.1-sol','output':[item],
                       'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}}):
            self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n').encode())
            self.wfile.flush()


class CodexNoticeCollectorChecks(unittest.TestCase):
    def run_fixture(self, mode):
        server=ThreadingHTTPServer(('127.0.0.1',0),ScriptedNoticeResponses)
        server.mode=mode;server.sequence=0;server.guard=threading.Lock()
        server.tool_started=threading.Event();server.first_change=threading.Event()
        server.notice_started=threading.Event();server.second_change=threading.Event()
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original_config=codex_gateway.write_config
        native=run.codex_agent.CodexAgent
        execute=lab.World.execute_bash
        call=lab.World.call
        continuation_call=unified_delivery.Continuation.call
        confirm=run.codex_notice_echo
        skipped=set()

        def local_config(home,*args):
            original_config(home,*args);p=home/'config.toml'
            p.write_text(p.read_text().replace(codex_gateway.AXONHUB_BASE,
                f'http://127.0.0.1:{server.server_port}/v1').replace('requires_openai_auth=false',
                'requires_openai_auth=false\nsupports_websockets=false\nrequest_max_retries=0\nstream_max_retries=0'))
        def local_agent(*args,**kwargs):
            kwargs['api_base']=codex_gateway.AXONHUB_BASE
            return native(*args,**kwargs)
        def shell(transaction):
            if transaction['actor']=='job-northline':
                server.tool_started.set()
                if not server.first_change.wait(30):
                    raise RuntimeError('Timed out awaiting committed business change')
            return execute(transaction)
        def world_call(self, actor, step, name, args, **kwargs):
            result=call(self,actor,step,name,args,**kwargs)
            if actor=='job-aster' and name=='bash' and args['command'].startswith('rm '):
                server.first_change.set()
            return result
        def business_call(self,actor,step,name,args,**kwargs):
            result=continuation_call(self,actor,step,name,args,**kwargs)
            if getattr(self.world,'operator',None) is not None and actor=='job-aster':
                if name=='execute_dispatch':server.first_change.set()
                if name=='cancel_dispatch_item':server.second_change.set()
            return result
        def confirmation(folder, request, text, previous, count=0):
            if mode=='missing':return None
            if mode=='race' and 'job-northline' in str(folder) and not skipped:
                skipped.add('first');return None
            return confirm(folder,request,text,previous,count)
        try:
            with TemporaryDirectory() as directory, patch.object(codex_gateway,'write_config',local_config):
                root=Path(directory); output=root/'output'; registration=root/'registration'; key=root/'key'
                key.write_text('offline-fixture')
                world={'observation':{'status_scope':'reporting_close'},
                       'coupling':{'communication_format':'work_files'}}
                with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                        patch.object(run,'verify_routes',return_value={}), \
                        patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                        patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                    run.prepare(output,registration,key,run_controls=False,study_mode='unified',
                                harness_kind='codex',goal_mode='off',scenario='engineering-capacity',
                                binding_preset='control',world_config=world)
                reg=run.load(output/'registration.json')
                reg['api_base']=f'http://127.0.0.1:{server.server_port}/v1'
                reg['budget'].update(max_batch_seconds=90,max_actor_seconds=90)
                run.save(output/'registration.json',reg)
                run.save(output/'registration-seal.json',{'sha256':run.sha(output/'registration.json')})
                with patch.object(run,'verify_collection_freeze'), \
                        patch.object(run,'registration_path',side_effect=lambda p:Path(p)), \
                        patch.object(run.codex_agent,'CodexAgent',side_effect=local_agent), \
                        patch.object(run,'AXONHUB_KEY_FILE',key), \
                        patch.object(lab.World,'execute_bash',staticmethod(shell)), \
                        patch.object(lab.World,'call',world_call), \
                        patch.object(unified_delivery.Continuation,'call',business_call), \
                        patch.object(run,'codex_notice_echo',side_effect=confirmation):
                    run.collect(output,registration,offline_transport_test=True)
                actor=output/'natural/job-northline'; trace=actor/'trace'
                notices=sorted(trace.glob('*-platform-update.json'))
                confirmed=sorted(trace.glob('*-platform-update-confirmed.json'))
                missing=sorted(trace.glob('*-platform-update-unconfirmed.json'))
                result=run.load(actor/'result.json')
                events=run.load(output/'natural/world.json')['events']
                self.assertTrue(server.tool_started.is_set() and server.first_change.is_set())
                self.assertTrue(any(e['actor']=='job-northline' and e['operation']=='bash'
                                    and e['result'].get('exit_code')==0 for e in events))
                if mode=='reverted':
                    changes=[e for e in events if e['actor']=='job-aster' and e['operation']=='bash']
                    self.assertEqual(len(changes),2)
                    self.assertTrue(all(e['result'].get('exit_code')==0 for e in changes))
                    self.assertTrue(all(e.get('shared_changes') for e in changes))
                if mode in ('read','reverted'):
                    self.assertEqual(notices,[])
                    self.assertEqual(confirmed,[])
                elif mode=='missing':
                    self.assertEqual(len(notices),1);self.assertEqual(len(missing),1)
                    self.assertEqual(confirmed,[])
                    self.assertEqual(result['status'],'unconfirmed_platform_notice')
                    self.assertNotEqual(run.load(output/'completion.json').get('termination_reason'),'business_complete')
                else:
                    self.assertEqual(len(notices),1);self.assertEqual(len(confirmed),1)
                    receipt=run.load(confirmed[0]);request=run.load(trace/f"{receipt['request_step']:04d}.request.json")
                    self.assertIn(receipt['native_echo'],request['native_input_records'])
                    self.assertEqual(receipt['baseline_advanced'],mode!='race')
                    if mode=='race':
                        self.assertTrue(server.second_change.is_set())
                        original=run.load(notices[0])['notice']['work_revision']
                        self.assertNotEqual(result['last_observed_work_revision'],original)
                # Export validates real native records; scripted responses are not behavioral evidence.
                self.assertEqual(len(export_atif.export(output)),4)
                self.assertTrue(all(row['native_continuity_passed'] for row in
                                    run.load(output/'atif-validation.json')['trajectories']))
        finally:
            server.first_change.set();server.notice_started.set();server.second_change.set()
            server.shutdown();server.server_close()

    def test_changed_state_delivered_after_active_tool(self):self.run_fixture('changed')
    def test_exact_tool_read_avoids_repeated_notice(self):self.run_fixture('read')
    def test_reverted_shared_change_does_not_notify(self):self.run_fixture('reverted')
    def test_missing_confirmation_cannot_finish_successfully(self):self.run_fixture('missing')
    def test_tool_read_racing_echo_preserves_newer_observation(self):self.run_fixture('race')


if __name__=='__main__':unittest.main()
