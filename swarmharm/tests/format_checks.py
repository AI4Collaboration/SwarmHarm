import json
from pathlib import Path
import tempfile
import unittest

import harbor_input
from phase1 import lab
from phase1 import schedule
import export_atif


class FormatChecks(unittest.TestCase):
    def incomplete_pi_fixture(self, root):
        folder=root/'natural/actor';trace=folder/'trace'
        session=folder/'pi/session/session.jsonl'
        inputs=[{'role':'system','content':'Workstation context'},
                {'role':'user','content':'Prepare the delivery.'}]
        raw={'type':'function_call','id':'fc-one','call_id':'call-one',
             'name':'bash','arguments':'{"command":"read delivery'}
        projected={**raw,'arguments':'{"command":"read delivery"}'}
        error='Tool call was not executed: output token limit.'
        observation={'type':'function_call_output','call_id':'call-one','output':error}
        final={'type':'message','role':'assistant','content':[{'type':'output_text','text':'Release remains blocked.'}]}
        request={'model':'fixture','input':inputs,'tools':[]}
        native_id='call-one|fc-one'
        records={
            root/'registration.json':{'harness':{'kind':'pi-sdk'},'study_mode':'unified',
                                       'plan':{'natural':{'actor':{}}}},
            root/'completion.json':{'status':'collected_with_limits'},
            trace/'0001.request.json':request,
            trace/'transport-attempts/0001/0001.request.json':request,
            trace/'transport-attempts/0001/0001.error.json':{'type':'response.incomplete',
                'response':{'id':'response-one','model':'fixture','status':'incomplete',
                    'incomplete_details':{'reason':'max_output_tokens'},'output':[raw]}},
            trace/'0002.request.json':{**request,'input':inputs+[projected,observation]},
            trace/'0002.response.json':{'model':'fixture','status':'completed','output':[final]},
            folder/'history.json':inputs+[projected,observation,final],
            folder/'result.json':{'status':'quiescent','pi_session':{
                'session_file':str(session),'session_id':'session-one'},
                'harness_rejected_tool_calls':[{'turn':1,'call_id':native_id,'name':'bash',
                    'result':{'content':[{'type':'text','text':error}]}}]},
        }
        for path,value in records.items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        session.parent.mkdir(parents=True)
        rows=[{'type':'session','id':'session-one'},
              {'type':'message','id':'assistant-one','parentId':None,'message':{
                  'role':'assistant','model':'fixture','responseId':'response-one','stopReason':'length',
                  'content':[{'type':'toolCall','id':native_id,'name':'bash',
                              'arguments':{'command':'read delivery'}}]}},
              {'type':'message','id':'result-one','parentId':'assistant-one','message':{
                  'role':'toolResult','toolCallId':native_id,'toolName':'bash','isError':True,
                  'content':[{'type':'text','text':error}]}}]
        session.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return folder,session,records,rows

    def test_atif_continues_after_a_native_pi_output_cutoff_without_executing_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            folder,session,records,rows=self.incomplete_pi_fixture(root)
            originals={path:path.read_bytes() for path in [*records,session]}
            results=export_atif.export(root)
            value=json.loads((folder/'agent/trajectory.json').read_text())
            agent_steps=[step for step in value['steps'] if step['source']=='agent']
            self.assertEqual(len(agent_steps),2)
            failed=agent_steps[0]
            self.assertEqual(failed['extra']['native_status'],'incomplete')
            self.assertEqual(failed['extra']['native_response'],'trace/transport-attempts/0001/0001.error.json')
            self.assertEqual(failed['tool_calls'][0]['arguments'],{'command':'read delivery'})
            self.assertEqual(failed['tool_calls'][0]['extra']['raw_provider_arguments'],'{"command":"read delivery')
            self.assertEqual(failed['tool_calls'][0]['extra']['execution_status'],'rejected_by_harness')
            self.assertTrue(failed['observation']['results'][0]['extra']['is_error'])
            self.assertEqual(agent_steps[1]['message'],'Release remains blocked.')
            self.assertEqual(results[0]['tool_results'],0)
            self.assertEqual(value['extra']['missing_response_records'],['trace/0001.response.json'])
            self.assertIn('pi/session/session.jsonl',value['extra']['source_sha256'])
            self.assertIn('exporter_source_sha256',json.loads((root/'atif-validation.json').read_text()))
            self.assertTrue(export_atif.export_actor(root,'natural','actor')['preserved_existing_export'])
            for path,original in originals.items():self.assertEqual(path.read_bytes(),original)
            self.assertFalse((folder/'trace/0001.response.json').exists())

    def test_atif_rejects_unproven_pi_cutoff_history(self):
        for change in ('history','session_arguments','session_result','session_chain',
                       'controller_rejection','provider_call','executed_call','missing_evidence'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                folder,session,records,rows=self.incomplete_pi_fixture(root)
                if change=='history':
                    path=folder/'trace/0002.request.json';records[path]['input'][3]['output']='Invented result'
                elif change=='session_arguments':rows[1]['message']['content'][0]['arguments']={'command':'different'}
                elif change=='session_result':rows[2]['message']['content'][0]['text']='Invented result'
                elif change=='session_chain':rows[2]['parentId']='unrelated'
                elif change=='controller_rejection':records[folder/'result.json']['harness_rejected_tool_calls']=[]
                elif change=='provider_call':
                    records[folder/'trace/transport-attempts/0001/0001.error.json']['response']['output'][0]['name']='different'
                elif change=='executed_call':records[folder/'trace/0001-tool-1.json']={}
                elif change=='missing_evidence':
                    records[folder/'trace/transport-attempts/0001/0001.error.json']={'type':'error'}
                for path,value in records.items():path.write_text(json.dumps(value))
                session.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises(AssertionError):export_atif.export_actor(root,'natural','actor')
                self.assertFalse((folder/'agent/trajectory.json').exists())

    def test_atif_preserves_rejections_before_executed_pi_tool_results(self):
        for change in (None, 'session_result', 'session_chain', 'arguments', 'controller_result', 'executed_rejection'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                folder,session,records,rows=self.incomplete_pi_fixture(root)
                trace=folder/'trace'
                request=records[trace/'0001.request.json']
                call=records[trace/'0002.request.json']['input'][2]
                second={**call,'id':'fc-two','call_id':'call-two','arguments':'{"command":"read second"}'}
                result={'stdout':'Original workstation result'}
                response={'id':'response-one','model':'fixture','status':'completed','output':[call,second]}
                records[trace/'0001.response.json']=response
                records[trace/'0001-tool-1.json']={'call_id':'call-two','name':'bash',
                    'arguments':second['arguments'],'result':result}
                rejection=records[trace/'0002.request.json']['input'][3]
                observed={'type':'function_call_output','call_id':'call-two','output':json.dumps(result)}
                incoming=request['input']+[call,second,rejection,observed]
                records[trace/'0002.request.json']['input']=incoming
                records[folder/'history.json']=incoming+records[trace/'0002.response.json']['output']
                rows[1]['message']['stopReason']='toolUse'
                rows[1]['message']['content'].append({'type':'toolCall','id':'call-two|fc-two',
                    'name':'bash','arguments':{'command':'read second'}})
                rows.append({'type':'message','id':'result-two','parentId':'result-one','message':{
                    'role':'toolResult','toolCallId':'call-two|fc-two','toolName':'bash','isError':False,
                    'content':[{'type':'text','text':json.dumps(result)}]}})
                if change=='session_result':rows[2]['message']['content'][0]['text']='Invented rejection'
                elif change=='session_chain':rows[3]['parentId']='unrelated'
                elif change=='arguments':rows[1]['message']['content'][0]['arguments']={'command':'different'}
                elif change=='controller_result':
                    records[folder/'result.json']['harness_rejected_tool_calls'][0]['result']['content'][0]['text']='Invented rejection'
                elif change=='executed_rejection':
                    records[trace/'0001-tool-2.json']={'call_id':'call-one','name':'bash','arguments':call['arguments'],'result':result}
                for path,value in records.items():path.write_text(json.dumps(value))
                session.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                originals={path:path.read_bytes() for path in [*records,session]}
                if change:
                    with self.assertRaises(AssertionError):export_atif.export_actor(root,'natural','actor')
                    self.assertFalse((folder/'agent/trajectory.json').exists())
                else:
                    exported=export_atif.export_actor(root,'natural','actor')
                    value=json.loads((folder/'agent/trajectory.json').read_text())
                    step=next(step for step in value['steps'] if step.get('tool_calls'))
                    self.assertEqual([r['source_call_id'] for r in step['observation']['results']],['call-one','call-two'])
                    self.assertTrue(step['observation']['results'][0]['extra']['is_error'])
                    self.assertEqual(step['tool_calls'][0]['extra']['execution_status'],'rejected_by_harness')
                    self.assertEqual(exported['tool_results'],1)
                for path,original in originals.items():self.assertEqual(path.read_bytes(),original)

    def test_identical_platform_notices_bind_to_their_own_request(self):
        message = {'role': 'user', 'content': 'The workspace state has changed.'}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            trace = folder / 'trace'
            trace.mkdir()
            for label in ('0011', '0013', '0015'):
                (trace / f'{label}-platform-update.json').write_text(json.dumps({'input_message': message}))
            for label in ('0011', '0013', '0015'):
                self.assertEqual(export_atif.platform_record_for_request(folder, label, message),
                                 trace / f'{label}-platform-update.json')
            self.assertIsNone(export_atif.platform_record_for_request(folder, '0012', message))
            self.assertIsNone(export_atif.platform_record_for_request(
                folder, '0013', {'role': 'user', 'content': 'Other content'}))
            self.assertIsNone(export_atif.platform_record_for_request(
                folder, '0013', {'role': 'developer', 'content': message['content']}))

    def test_harbor_runtime_metadata_matches_registered_execution(self):
        plan = schedule.compile_plan(4, 'control', iter(('a', 'b', 'c', 'd')).__next__)[0]
        runtime = {'image': 'sha256:' + 'a'*64, 'timeout_seconds': 900,
                   'allowed_hosts': ['library.reporting.test']}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            harbor_input.write(root, plan, **runtime)
            harbor_input.initial_audit(root, plan, **runtime)
            for change in ({'image': 'sha256:' + 'b'*64}, {'timeout_seconds': 1200},
                           {'allowed_hosts': []}):
                with self.subTest(change=change), self.assertRaises(AssertionError):
                    harbor_input.initial_audit(root, plan, **{**runtime, **change})

    def test_harbor_packages_are_actual_runtime_inputs(self):
        counter = iter(range(10))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = harbor_input.write(root, plan)
            audit = harbor_input.initial_audit(root, plan)
            self.assertEqual(sum(len(value) for value in hashes.values()), 4)
            for phase, actors in plan.items():
                for actor, item in actors.items():
                    self.assertEqual(audit[phase][actor]["input"][-1]["content"], lab.task(item))

    def test_claim_levels_are_explicit(self):
        contract = json.loads((Path(__file__).parents[1] / "format-contract.json").read_text())
        self.assertEqual(contract["input"]["schema"], "1.4")
        self.assertEqual(contract["output"]["trajectory"], "ATIF-v1.8")
        self.assertTrue(contract["output"]["formation_communication_graph_reconstructed_independently"])
        self.assertTrue(contract["output"]["one_continuous_trajectory_per_agent"])
        self.assertTrue(contract["output"]["current_unified_track_is_continuous"])
        self.assertTrue(contract["output"]["same_trajectory_outcomes"])
        self.assertTrue(contract["output"]["formation_is_not_consequence_gate"])
        self.assertTrue(contract["output"]["business_effects_recomputed_independently"])
        self.assertFalse(contract["execution"]["generic_harbor_job_scheduler"])

    def test_atif_export_accepts_append_only_platform_updates(self):
        initial = [{"role": "user", "content": "Complete the filing."}]
        update = {
            "role": "developer",
            "content": '{"source":"platform_status","status":"Customer filing state has changed."}',
        }
        self.assertEqual(
            export_atif.appended_input(initial, initial + [update]),
            [update],
        )
        self.assertEqual(export_atif.completion_feedback_message({"input_message": update}), update)
        step = export_atif.input_step(update, kind="relevant_platform_change")
        self.assertEqual(step["source"], "system")
        self.assertEqual(step["extra"]["native_role"], "developer")
        self.assertEqual(step["message"], update["content"])
        self.assertEqual(export_atif.input_step(initial[0])["source"], "user")
        with self.assertRaisesRegex(AssertionError, "rewrote prior history"):
            export_atif.appended_input(initial, [update])

    def test_atif_export_accepts_system_prompt_rerendered_for_new_tools(self):
        before = [{"role": "developer", "content": "<tools>\n- bash\n</tools>"}]
        after = {"role": "developer", "content": "<tools>\n- bash\n- open_funding_plan\n</tools>"}
        self.assertIsNone(export_atif.system_prompt_update(before, before, True))
        self.assertEqual(export_atif.system_prompt_update(before, [after], True), after)
        with self.assertRaisesRegex(AssertionError, "rewrote prior history"):
            export_atif.system_prompt_update(before, [after], False)

    def test_atif_export_compares_rebuilt_items_by_meaning(self):
        response_call = {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                         "name": "bash", "arguments": '{"command": "ls"}', "status": "completed"}
        rebuilt_call = {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                        "name": "bash", "arguments": '{"command":"ls"}'}
        self.assertEqual(export_atif.canonical(response_call), export_atif.canonical(rebuilt_call))
        message = {"type": "message", "role": "assistant", "id": "msg_1", "status": "completed",
                   "content": [{"type": "output_text", "text": "Done.", "annotations": []}]}
        self.assertEqual(export_atif.canonical(message), export_atif.canonical(
            {"role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}))
        changed = dict(rebuilt_call, arguments='{"command":"pwd"}')
        self.assertNotEqual(export_atif.canonical(response_call), export_atif.canonical(changed))

    def test_atif_existing_export_must_match_native_reconstruction_and_study_scope(self):
        for mode in ('phase1', 'phase2-component', 'connected'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                folder = root / 'natural/actor'
                trace = folder / 'trace'
                trace.mkdir(parents=True)
                inputs = [{'role': 'system', 'content': 'Workstation context'},
                          {'role': 'user', 'content': 'Prepare the delivery.'}]
                output = [{'type': 'message', 'role': 'assistant',
                           'content': [{'type': 'output_text', 'text': 'Actual model text'}]}]
                records = {
                    root / 'registration.json': {'harness': {'kind': 'pi-sdk'}, 'study_mode': mode},
                    trace / '0001.request.json': {'model': 'fixture', 'input': inputs,
                        'tools': [{'type': 'function', 'name': 'read_delivery_record',
                                   'description': 'Read a record.', 'parameters': {'type': 'object'}}]},
                    trace / '0001.response.json': {'status': 'completed', 'output': output},
                    folder / 'history.json': inputs + output,
                    folder / 'result.json': {'status': 'completed'},
                }
                for path, value in records.items():
                    path.write_text(json.dumps(value))
                export_atif.export_actor(root, 'natural', 'actor')
                dest = folder / 'agent/trajectory.json'
                original = dest.read_bytes()
                value = json.loads(original)
                self.assertEqual(value['extra']['study_mode'], mode)
                self.assertEqual(value['extra']['phase2_tools_seen'], mode == 'phase2-component')
                self.assertNotIn('spans both phases', value['extra']['conversion'])
                self.assertNotIn('spans Phase 1 and Phase 2', value['extra']['conversion'])
                self.assertTrue(export_atif.export_actor(root, 'natural', 'actor')['preserved_existing_export'])
                self.assertEqual(dest.read_bytes(), original)
                value['steps'][-1]['message'] = 'This text is absent from the native record.'
                dest.write_text(json.dumps(value))
                altered = dest.read_bytes()
                with self.assertRaisesRegex(AssertionError, 'differs from native reconstruction'):
                    export_atif.export_actor(root, 'natural', 'actor')
                self.assertEqual(dest.read_bytes(), altered)

    def test_atif_binds_undelivered_execution_without_fabricating_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'natural/actor'
            trace = folder / 'trace'
            trace.mkdir(parents=True)
            inputs = [{'role': 'system', 'content': 'Workstation context'},
                      {'role': 'user', 'content': 'Prepare the delivery.'}]
            call = {'type': 'function_call', 'name': 'bash', 'call_id': 'shell-one',
                    'arguments': '{"command":"write local report"}'}
            pending = trace / '0001-tool-1-undelivered.json'
            records = {
                root / 'registration.json': {'harness': {'kind': 'pi-sdk'}, 'study_mode': 'phase1'},
                trace / '0001.request.json': {'model': 'fixture', 'input': inputs, 'tools': []},
                trace / '0001.response.json': {'status': 'completed', 'output': [call]},
                folder / 'history.json': inputs + [call],
                folder / 'result.json': {'status': 'operator_interrupted'},
                pending: {'call_id': 'shell-one', 'delivery_status': 'not_delivered',
                          'shared_commit_applied': False, 'execution': {'reply': {'stdout': 'written'}}},
            }
            for path, value in records.items():
                path.write_text(json.dumps(value))
            result = export_atif.export_actor(root, 'natural', 'actor')
            value = json.loads((folder / 'agent/trajectory.json').read_text())
            relative = str(pending.relative_to(folder))
            self.assertEqual(value['extra']['undelivered_tool_records'], [relative])
            self.assertEqual(value['extra']['source_sha256'][relative], export_atif.sha(pending))
            self.assertFalse(value['steps'][-1].get('observation'))
            self.assertEqual(result['tool_results'], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
