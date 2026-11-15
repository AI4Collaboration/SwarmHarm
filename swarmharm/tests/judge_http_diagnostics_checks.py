"""HTTP and SSE failure fixtures only; no provider request is made."""
from email.message import Message
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import urllib.error

from scripts import judge_unified_transcript as judge


def error(body, *, code=502, reason='Bad Gateway', headers=None):
    return urllib.error.HTTPError('https://example.invalid/v1/responses',code,reason,headers or Message(),BytesIO(body))


class Checks(unittest.TestCase):
    def test_http_error_stores_only_enums_hash_and_request_id_digest(self):
        secret='unknown.segmented.upstream.token';caller_key='known.key.value'
        headers=Message();headers['Content-Type']='application/json'
        headers['X-Request-Id']='fbd416b2-2a86-4ef5-9b2b-e5add12c94b8'
        headers['Authorization']='Bearer '+secret
        body=json.dumps({'error':{'type':'provider_error','code':'upstream_unavailable',
            'message':'Unexpected '+secret+' '+caller_key,'provider':secret,
            'metadata':{'status':'invalid_request_error','api_key':secret}},'authorization':secret}).encode()
        value=judge.provider_http_diagnostic(error(body,headers=headers),caller_key)
        rendered=json.dumps(value)
        self.assertEqual(value['status'],502);self.assertEqual(value['body_format'],'json')
        self.assertEqual(value['body_prefix_sha256'],sha256(body).hexdigest())
        self.assertEqual(value['error_categories'],['provider_error','upstream_unavailable'])
        self.assertTrue(value['request_id_present'])
        uuid_secret='fbd416b2-2a86-4ef5-9b2b-e5add12c94b8'
        self.assertEqual(value['request_id_sha256'],sha256(uuid_secret.encode()).hexdigest())
        self.assertNotIn(uuid_secret,rendered)
        self.assertNotIn(secret,rendered);self.assertNotIn(caller_key,rendered)
        self.assertNotIn('message',rendered);self.assertNotIn('authorization',rendered.lower())
        headers.replace_header('X-Request-Id',secret)
        invalid=judge.provider_http_diagnostic(error(body,headers=headers),caller_key)
        self.assertTrue(invalid['request_id_present']);self.assertIsNone(invalid['request_id_sha256'])
        self.assertNotIn(secret,json.dumps(invalid))
        headers.replace_header('X-Request-Id','fbd416b2-2a86-4ef5-9b2b-e5add12c94b8')
        self.assertIsNone(judge.provider_http_diagnostic(error(body,headers=headers),headers['X-Request-Id'])['request_id_sha256'])
        absent=judge.provider_http_diagnostic(error(body))
        self.assertFalse(absent['request_id_present']);self.assertIsNone(absent['request_id_sha256'])

    def test_explicit_policy_refusal_is_classified_without_storing_message(self):
        token='unknown.short.dotted.provider.token'
        messages=[
            'This request violates our content policy. '+token,
            'The request was rejected by the safety policy. '+token,
            'Request blocked by moderation. '+token,
            'Your request was blocked due to content policy. '+token,
            'This request was refused because of our safety policy. '+token,
        ]
        for message in messages:
            with self.subTest(message=message):
                body=json.dumps({'error':{'message':message}}).encode()
                value=judge.provider_http_diagnostic(error(body))
                self.assertEqual(value['policy_status'],'provider_stated_refusal')
                self.assertNotIn(token,json.dumps(value));self.assertNotIn(message,json.dumps(value))
        value=judge.provider_http_diagnostic(error(b'Request violates content policy.'))
        self.assertEqual(value['policy_status'],'provider_stated_refusal')
        value=judge.provider_http_diagnostic(error(json.dumps({'error':{'code':'content_policy_violation'}}).encode()))
        self.assertEqual(value['policy_status'],'provider_stated_refusal')

    def test_policy_mentions_without_explicit_refusal_remain_unknown(self):
        for message in ('The request was not blocked by safety policy.',
                        'Safety policy information is unavailable.',
                        'Upstream timeout occurred; content filtering is enabled.',
                        'If a request violates the content policy it may be rejected.',
                        'Gateway error.',
                        'This request timed out. A previous request violated content policy.',
                        'This request timed out; the previous request violated content policy.',
                        'The previous request was blocked by content policy.',
                        'Your request was accepted while the unrelated profile violated content policy.',
                        'Your request was blocked due to service failure while a profile violated content policy.',
                        'Your request was blocked by a service outage affecting the content policy.',
                        'This request was rejected because a policy database was unavailable.',
                        'The request was blocked by content policy service failure.',
                        'This request completed and an account violated the safety policy.',
                        'Your request succeeded while the unrelated request violated the content policy.'):
            with self.subTest(message=message):
                value=judge.provider_http_diagnostic(error(json.dumps({'error':{'message':message}}).encode()))
                self.assertEqual(value['policy_status'],'unknown')
        value=judge.provider_http_diagnostic(error(b'{"error":{"code":"content_filter"}}'),secret='content_filter')
        self.assertEqual(value['policy_status'],'unknown');self.assertEqual(value['error_categories'],[])

    def test_nested_metadata_cannot_turn_timeout_into_refusal(self):
        body=json.dumps({'error':{'code':'upstream_timeout','message':'This request timed out.',
            'metadata':{'type':'content_filter','message':'Request blocked by content policy.'}}}).encode()
        value=judge.provider_http_diagnostic(error(body))
        self.assertEqual(value['policy_status'],'unknown')
        self.assertEqual(value['error_categories'],['upstream_timeout'])

    def test_incomplete_content_filter_requires_exact_current_event(self):
        token='unknown.provider.secret'
        for event,expected in [
            ({'type':'response.incomplete','response':{'incomplete_details':{'reason':'content_filter'},'note':token}},'provider_stated_refusal'),
            ({'type':'response.incomplete','response':{'incomplete_details':{'reason':'timeout'},'metadata':{'type':'content_filter'},'note':token}},'unknown'),
            ({'type':'response.incomplete','response':{'metadata':{'incomplete_details':{'reason':'content_filter'}},'note':token}},'unknown'),
        ]:
            body=('data: '+json.dumps(event)+'\n\n').encode();capture=BytesIO()
            with self.assertRaises(judge.StreamFailure) as caught:judge.read_stream(BytesIO(body),capture)
            self.assertEqual(caught.exception.policy_status,expected)
            self.assertEqual(capture.getvalue(),b'');self.assertNotIn(token,str(caught.exception))

    def test_stream_refusal_is_classified_without_persisting_provider_text(self):
        token='unknown.other.secret.token'
        body=(f'data: {{"type":"response.failed","response":{{"error":{{"message":'
              f'"Request blocked by content policy. {token}"}}}}}}\n\n').encode()
        capture=BytesIO()
        with self.assertRaises(judge.StreamFailure) as caught:judge.read_stream(BytesIO(body),capture)
        self.assertEqual(caught.exception.policy_status,'provider_stated_refusal')
        self.assertEqual(capture.getvalue(),b'');self.assertNotIn(token,str(caught.exception))

    def test_completed_standard_refusal_is_detected_without_persisting_text(self):
        token='unknown.provider.secret.token'
        content={'type':'refusal','refusal':'I cannot help with this request. '+token}
        response={'status':'completed','model':'offline','output':[{'type':'message','role':'assistant','content':[content]}]}
        self.assertTrue(judge.completed_response_refusal(response))
        for fake in [
            {'status':'completed','output':[{'type':'message','role':'user','content':[content]}]},
            {'status':'completed','output':[{'type':'tool_call','role':'assistant','content':[content]}]},
            {'status':'completed','output':[{'type':'message','role':'assistant','metadata':{'content':[content]},'content':[]}]},
            {'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'refusal'}]}]},
            {'status':'failed','output':response['output']},
        ]:self.assertFalse(judge.completed_response_refusal(fake))
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'transcript-judge-input.json').write_text('{}');(root/'action-monitor.json').write_text('{}');(root/'registration.json').write_text('{}');(root/'natural').mkdir();(root/'natural/world.json').write_text('{}')
            key=root/'key';key.write_text('caller.secret.token')
            def completed(request,secret,capture):
                capture.write(('data: '+json.dumps(response)+'\n\n').encode())
                return response
            with patch.object(judge,'post',side_effect=completed):
                with self.assertRaisesRegex(RuntimeError,'did not complete'):
                    judge.main(['--output',str(root),'--key-file',str(key)])
            folder=root/'transcript-judge-attempts'
            saved=json.loads((folder/'0001-error.json').read_text())
            self.assertEqual(saved['stream_state'],'refusal')
            self.assertEqual(saved['policy_status'],'provider_stated_refusal')
            self.assertFalse((folder/'0001-stream.sse').exists())
            self.assertFalse((folder/'0001-response.json').exists())
            for path in folder.iterdir():self.assertNotIn(token,path.read_text())

    def test_completed_refusal_through_actual_sse_and_json_paths(self):
        token='provider.secret.unknown'
        response={'status':'completed','output':[{'type':'message','role':'assistant',
            'content':[{'type':'refusal','refusal':token}]}]}
        for streaming in (False,True):
            with self.subTest(streaming=streaming), TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'transcript-judge-input.json').write_text('{}');(root/'action-monitor.json').write_text('{}');(root/'registration.json').write_text('{}');(root/'natural').mkdir();(root/'natural/world.json').write_text('{}')
                key=root/'key';key.write_text('caller.secret.token')
                payload=json.dumps(response).encode()
                if streaming:payload=b'data: '+json.dumps({'type':'response.completed','response':response}).encode()+b'\n\n'
                class Response(BytesIO):
                    def __init__(self):
                        super().__init__(payload)
                        self.headers={'Content-Type':'text/event-stream' if streaming else 'application/json'}
                with patch.object(judge.guardrails,'open_url',return_value=Response()):
                    with self.assertRaisesRegex(RuntimeError,'did not complete'):
                        judge.main(['--output',str(root),'--key-file',str(key)])
                folder=root/'transcript-judge-attempts'
                saved=json.loads((folder/'0001-error.json').read_text())
                self.assertEqual(saved['policy_status'],'provider_stated_refusal')
                self.assertEqual(saved['stream_state'],'refusal')
                for path in folder.iterdir():self.assertNotIn(token,path.read_text())

    def test_http_text_and_large_body_are_not_written(self):
        secret='a.dotted.unknown.provider.token'
        body=('gateway error '+secret+'\n'+'x'*(judge.MAX_ERROR_BYTES+200)).encode()
        value=judge.provider_http_diagnostic(error(body))
        self.assertTrue(value['body_truncated']);self.assertEqual(value['body_format'],'other')
        self.assertEqual(value['body_prefix_bytes'],judge.MAX_ERROR_BYTES)
        self.assertNotIn(secret,json.dumps(value))
        self.assertEqual(value['body_prefix_sha256'],sha256(body[:judge.MAX_ERROR_BYTES]).hexdigest())

    def test_sse_error_is_not_written_even_if_prefix_contains_secret(self):
        token='unknown.segmented.provider.key'
        body=(f'data: {{"type":"response.created","note":"{token}"}}\n\n'
              f'data: {{"type":"response.failed","error":"{token}"}}\n\n').encode()
        capture=BytesIO()
        with self.assertRaises(judge.StreamFailure) as caught:judge.read_stream(BytesIO(body),capture)
        self.assertEqual(capture.getvalue(),b'');self.assertEqual(caught.exception.state,'failed')
        self.assertEqual(caught.exception.digest,sha256(body).hexdigest())
        self.assertNotIn(token,str(caught.exception))

    def test_post_keeps_failed_sse_file_empty(self):
        token='upstream.short.dotted.token'
        body=(f'data: {{"type":"response.created","note":"{token}"}}\n\n'
              f'data: {{"type":"response.failed","error":"{token}"}}\n\n').encode()
        class Response(BytesIO):
            def __init__(self):
                super().__init__(body);self.headers={'Content-Type':'text/event-stream'}
        with patch.object(judge.guardrails,'open_url',return_value=Response()):
            capture=BytesIO()
            with self.assertRaises(judge.StreamFailure):judge.post({'model':'offline'},'caller.key',capture)
            self.assertEqual(capture.getvalue(),b'')

    def test_sse_interruption_records_only_digest(self):
        token=b'unknown.dot.segmented.token'
        def broken():
            yield b'data: '+token+b'\n'
            raise OSError('disconnected '+token.decode())
        capture=BytesIO()
        with self.assertRaises(judge.StreamFailure) as caught:judge.read_stream(broken(),capture)
        self.assertEqual(caught.exception.state,'interrupted')
        self.assertEqual(caught.exception.digest,sha256(b'data: '+token+b'\n').hexdigest())
        self.assertEqual(capture.getvalue(),b'');self.assertNotIn(token.decode(),str(caught.exception))

    def test_http_200_noncompleted_response_is_not_saved(self):
        token='provider.short.dotted.key'
        body=json.dumps({'status':'failed','error':token}).encode()
        class Response(BytesIO):
            def __init__(self):
                super().__init__(body);self.headers={'Content-Type':'application/json'}
        with patch.object(judge.guardrails,'open_url',return_value=Response()):
            capture=BytesIO()
            with self.assertRaises(judge.StreamFailure) as caught:judge.post({'model':'offline'},'caller.key',capture)
            self.assertEqual(caught.exception.state,'nonstream_incomplete')
            self.assertNotIn(token,str(caught.exception));self.assertEqual(capture.getvalue(),b'')

    def test_sse_success_is_unchanged(self):
        body=(b': heartbeat\n\ndata: {"type":"response.created"}\n\n'
              b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
              b'data: [DONE]\n\n')
        capture=BytesIO();self.assertEqual(judge.read_stream(BytesIO(body),capture)['status'],'completed')
        self.assertEqual(capture.getvalue(),body)

    def test_main_preserves_http_failure_without_error_body_or_key(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'transcript-judge-input.json').write_text('{}');(root/'action-monitor.json').write_text('{}');(root/'registration.json').write_text('{}');(root/'natural').mkdir();(root/'natural/world.json').write_text('{}')
            caller='current.secret.key';unknown='other.secret.key';key=root/'key';key.write_text(caller)
            body=json.dumps({'error':{'message':unknown+' '+caller,'type':'server_error'}}).encode()
            with patch.object(judge,'post',side_effect=error(body)):
                with self.assertRaisesRegex(RuntimeError,'HTTP Error 502'):
                    judge.main(['--output',str(root),'--key-file',str(key)])
            saved=json.loads((root/'transcript-judge-attempts/0001-error.json').read_text())
            self.assertEqual(saved['provider_response']['status'],502)
            self.assertEqual(saved['provider_response']['error_categories'],['server_error'])
            for p in (root/'transcript-judge-attempts').iterdir():
                self.assertNotIn(caller,p.read_text());self.assertNotIn(unknown,p.read_text())

    def test_failed_completed_response_keeps_only_hashes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'transcript-judge-input.json').write_text('{}');(root/'action-monitor.json').write_text('{}');(root/'registration.json').write_text('{}');(root/'natural').mkdir();(root/'natural/world.json').write_text('{}')
            token='unknown.short.dotted.secret';key=root/'key';key.write_text('current.secret.key')
            def complete_bad(request,secret,capture):
                capture.write(('data: '+token+'\n\n').encode())
                return {'model':'wrong-model','status':'completed','output':[token]}
            with patch.object(judge,'post',side_effect=complete_bad):
                with self.assertRaisesRegex(RuntimeError,'validation failed'):
                    judge.main(['--output',str(root),'--key-file',str(key)])
            folder=root/'transcript-judge-attempts'
            saved=json.loads((folder/'0001-validation-error.json').read_text())
            self.assertEqual(saved['validation_stage'],'model_identity')
            self.assertEqual(saved['stream_sha256'],sha256(('data: '+token+'\n\n').encode()).hexdigest())
            self.assertFalse((folder/'0001-response.json').exists())
            self.assertFalse((folder/'0001-stream.sse').exists())
            for path in folder.iterdir():self.assertNotIn(token,path.read_text())

    def test_main_preserves_stream_failure_without_body_or_key(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'transcript-judge-input.json').write_text('{}');(root/'action-monitor.json').write_text('{}');(root/'registration.json').write_text('{}');(root/'natural').mkdir();(root/'natural/world.json').write_text('{}')
            token='other.segmented.secret';key=root/'key';key.write_text('current.secret.key')
            failure=judge.StreamFailure('failed',token.encode(),'provider_stated_refusal')
            with patch.object(judge,'post',side_effect=failure):
                with self.assertRaisesRegex(RuntimeError,'did not complete'):
                    judge.main(['--output',str(root),'--key-file',str(key)])
            saved=json.loads((root/'transcript-judge-attempts/0001-error.json').read_text())
            self.assertEqual(saved['stream_state'],'failed');self.assertEqual(saved['policy_status'],'provider_stated_refusal')
            self.assertEqual(saved['stream_prefix_sha256'],sha256(token.encode()).hexdigest())
            self.assertNotIn(token,json.dumps(saved))

    def test_chat_completions_protocol_normalizes_content_and_refusals(self):
        request_value = {
            'model': 'offline-judge',
            'reasoning': {'effort': 'high'},
            'input': [
                {'role': 'system', 'content': [{'type': 'input_text', 'text': 'sys'}]},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'usr'}]},
            ],
            'text': {'format': {'type': 'json_schema', 'name': 'test', 'strict': True, 'schema': {'type': 'object'}}},
        }
        payload = judge.chat_completions_request(request_value)
        self.assertEqual(payload['messages'], [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'usr'}])
        self.assertEqual(payload['reasoning_effort'], 'high')
        body = json.dumps({'id': 'cc-1', 'model': 'offline-judge', 'choices': [
            {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"ok":true}'}}]}).encode()
        class Response(BytesIO):
            def __init__(self, raw):
                super().__init__(raw); self.headers = {'Content-Type': 'application/json'}
        with patch.object(judge.guardrails, 'open_url', return_value=Response(body)) as opened:
            normalized = judge.post(request_value, 'caller.key', BytesIO(),
                                    api_base='https://example.invalid/v1', protocol='chat-completions')
            self.assertEqual(opened.call_args.args[0].full_url, 'https://example.invalid/v1/chat/completions')
            self.assertEqual(judge.claim_evidence.response_text(normalized), '{"ok":true}')
        filtered = json.dumps({'model': 'offline-judge', 'choices': [
            {'finish_reason': 'content_filter', 'message': {'role': 'assistant', 'content': None}}]}).encode()
        with patch.object(judge.guardrails, 'open_url', return_value=Response(filtered)):
            with self.assertRaises(judge.StreamFailure) as caught:
                judge.post(request_value, 'caller.key', BytesIO(),
                           api_base='https://example.invalid/v1', protocol='chat-completions')
            self.assertEqual(caught.exception.policy_status, 'provider_stated_refusal')

if __name__=='__main__':unittest.main()
