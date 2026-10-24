import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
import io
from unittest.mock import patch
import run
from transport import DurableChat, fold
from design import emit, fixture, FAMILIES
from durability import pending, save


def frame(value): return 'data: ' + json.dumps(value)


class RecoveryTests(unittest.TestCase):
    def test_split_tool_and_reasoning_stream_roundtrip(self):
        frames = [frame({'id':'gen-test','model':'test','provider':'Novita','choices':[{'delta':{
            'reasoning_details':[{'index':0,'type':'reasoning.text','id':'r1','text':'Check '}],
            'tool_calls':[{'index':0,'id':'c1','function':{'name':'bash','arguments':'{"command":'}}]}}]}),
            frame({'choices':[{'delta':{'reasoning_details':[{'index':0,'type':'reasoning.text','id':'r1','text':'records.'}],
                'tool_calls':[{'index':0,'function':{'arguments':'"office records"}'}}]},'finish_reason':'tool_calls'}]}),
            frame({'choices':[],'usage':{'completion_tokens':20,'cost':.01}}), 'data: [DONE]']
        result = fold(frames)
        self.assertEqual(result['choices'][0]['message']['reasoning_details'][0]['text'], 'Check records.')
        self.assertEqual(json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments']),{'command':'office records'})
        with self.assertRaises(ValueError): fold(frames[:-1])

    def test_provider_identity_durable_before_stream_disconnect_no_retry(self):
        class Response:
            headers = {'Content-Type':'text/event-stream','x-request-id':'provider-request'}
            status=200
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def __iter__(self):
                yield (frame({'id':'gen-partial','model':'test','provider':'Novita','choices':[{'delta':{'content':'partial'}}]})+'\n').encode()
                raise TimeoutError('disconnect')
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'case/agents/worker';folder.mkdir(parents=True)
            with patch.dict('os.environ',{'OPENROUTER_API_KEY':'test-only'}): chat=DurableChat('test','novita/fp8')
            chat.journal=folder/'journal.jsonl'
            with patch('urllib.request.urlopen',return_value=Response()) as call:
                with self.assertRaises(RuntimeError): chat([{'role':'user','content':'Current queue.'}])
                self.assertEqual(call.call_count,1)
            events=[json.loads(l) for l in chat.journal.read_text().splitlines()]
            self.assertTrue(any(e['kind']=='response_headers' and e['headers']['x-request-id']=='provider-request' for e in events))
            self.assertTrue(any(e['kind']=='stream_identity' and e['provider_generation_id']=='gen-partial' for e in events))
            self.assertEqual(len(pending(folder)),1)
            request=next(e for e in events if e['kind']=='request_prepared')
            self.assertEqual(request['body']['user'],request['request_id'])
            self.assertTrue(request['body']['session_id'].startswith('v3:'))

    def test_stage_can_finish_after_old_eight_call_limit(self):
        class Model:
            body={}; calls=0
            def __call__(self,messages):
                self.calls+=1
                message={'role':'assistant','content':'Finished.'}
                if self.calls<=9:message={'role':'assistant','content':None,'tool_calls':[{'id':'c'+str(self.calls),'function':{'name':'bash','arguments':'{"command":"office overview"}'}}]}
                return message,{'usage':{'completion_tokens':1},'finish_reason':'tool_calls' if self.calls<=9 else 'stop'}
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);model=Model();run.native.UNRESOLVED.clear()
            run.BACKUP=folder/'backup';run.CURRENT.campaign='test'
            state=fixture(FAMILIES[0],'correct')[0]
            with patch.object(run,'read_state',return_value=copy.deepcopy(state)),patch.object(run,'snapshot',return_value=copy.deepcopy(state)),patch.object(run.native,'bash',return_value={'exit_code':0,'stdout':'{}','stderr':''}),patch.object(run,'export'):
                stop=run.stage(model,'ctr',[],'Prepare current worksheet.',folder,'solo',1,0,{'remaining':131072,'calls_remaining':120})
            self.assertEqual(stop,'final_answer');self.assertEqual(model.calls,10)

    def test_http_error_keeps_generation_identity_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'case/agents/solo'; folder.mkdir(parents=True)
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-only'}): chat = DurableChat('test', 'novita/fp8')
            chat.journal = folder / 'journal.jsonl'
            error = urllib.error.HTTPError('https://example.invalid', 503, 'unavailable',
                                          {'x-generation-id': 'gen-error', 'x-request-id': 'req-error'}, io.BytesIO(b'upstream unavailable'))
            with patch('urllib.request.urlopen', side_effect=error) as call:
                with self.assertRaises(RuntimeError): chat([{'role': 'user', 'content': 'Current queue.'}])
                self.assertEqual(call.call_count, 1)
            events = [json.loads(line) for line in chat.journal.read_text().splitlines()]
            headers = next(e for e in events if e['kind'] == 'response_headers')
            self.assertEqual(headers['headers']['x-generation-id'], 'gen-error')
            self.assertEqual(len(pending(folder)), 1)

    def test_unfinished_stage_does_not_advance_or_run_later_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tasks=root/'tasks';emit(tasks)
            out=root/'out';out.mkdir();run.BACKUP=root/'backup'
            case={'id':'test','family':FAMILIES[0],'intake':'correct','snapshot':'new','arm':'team','repeat':0}
            index={'test':{'id':'test','dir':'test','status':'pending'}}
            state=fixture(FAMILIES[0],'correct')[0]
            def snapshot(ctr,path):save(path,state);return copy.deepcopy(state)
            run.native.UNRESOLVED.clear()
            with patch.object(run.native,'image_for',return_value='tag'),patch.object(run.native,'sh',return_value=SimpleNamespace(stdout='test-id\n',returncode=0)),patch.object(run,'read_state',return_value=copy.deepcopy(state)),patch.object(run,'snapshot',side_effect=snapshot),patch.object(run,'stage',return_value='max_turns') as stage,patch.object(run,'advance',side_effect=AssertionError('unfinished wave advanced')):
                run.collect(case,out,tasks,index)
            self.assertEqual(stage.call_count,1)
            meta=json.loads((out/'test/meta.json').read_text())
            self.assertEqual(meta['grading_status'],'incomplete_stage')
            self.assertFalse(meta['episode_complete'])
            self.assertFalse((out/'test/wave2-state-in.json').exists())

    def test_grader_crash_is_distinct_from_stage_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tasks=root/'tasks';emit(tasks)
            out=root/'out';out.mkdir();run.BACKUP=root/'backup'
            case={'id':'test','family':FAMILIES[0],'intake':'correct','snapshot':'new','arm':'team','repeat':0}
            index={'test':{'id':'test','dir':'test','status':'pending'}}
            state=fixture(FAMILIES[0],'correct')[0]
            def snapshot(ctr,path):save(path,state);return copy.deepcopy(state)
            run.native.UNRESOLVED.clear()
            with patch.object(run.native,'image_for',return_value='tag'),patch.object(run.native,'sh',return_value=SimpleNamespace(stdout='test-id\n',returncode=0)),patch.object(run,'read_state',return_value=copy.deepcopy(state)),patch.object(run,'snapshot',side_effect=snapshot),patch.object(run,'stage',return_value='final_answer'),patch.object(run,'score',side_effect=ValueError('missing evidence')),patch.object(run,'advance',side_effect=AssertionError('bad grade advanced')):
                run.collect(case,out,tasks,index)
            meta=json.loads((out/'test/meta.json').read_text())
            self.assertEqual(meta['grading_status'],'grading_error')
            self.assertEqual(meta['grades'][0]['grading_status'],'grading_error')
            self.assertNotIn('any_overpayment',meta['grades'][0])


if __name__=='__main__':unittest.main()
