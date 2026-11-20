import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_transport import chat_request, responses_reply, response_events, messages_reply, message_events
from model_lineup import selection
from guardrails import native_harness
import claude_agent


class TransportChecks(unittest.TestCase):
    def test_all_eleven_have_matching_harness_and_claude_accepts_external_endpoint(self):
        rows = selection()
        self.assertEqual(len(rows), 11)
        for row in rows:
            self.assertEqual(native_harness({'model': row['model']}), row['harness'])
        env = claude_agent.gateway_env('https://example.test/proxy/v1', 'local-test',
                                     'anthropic/claude-haiku-5.5', '/tmp/private-test')
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'https://example.test/proxy')
        self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'], 'local-test')

    def test_namespaces_history_and_reasoning_survive_tool_roundtrip(self):
        body = {'instructions': 'Original instructions', 'reasoning': {'effort': 'high'},
            'tools': [{'type': 'namespace', 'name': 'work', 'description': 'Business tools',
                       'tools': [{'type': 'function', 'name': 'read', 'parameters': {'type': 'object'}}]}],
            'input': [{'role': 'user', 'content': 'Original task'},
                      {'type': 'function_call', 'namespace': 'work', 'name': 'read', 'call_id': 'c1', 'arguments': '{}'},
                      {'type': 'function_call_output', 'call_id': 'c1', 'output': 'Exact result'}]}
        cache = {'c1': {'reasoning_content': 'retained', 'reasoning_details': [{'signature': 'original'}]}}
        request = chat_request(body, 'responses', 'served-id', cache)
        self.assertEqual(request['model'], 'served-id')
        self.assertEqual(request['reasoning_effort'], 'high')
        self.assertEqual(request['tools'][0]['function']['name'], 'work__read')
        self.assertEqual(request['messages'][-2]['tool_calls'][0]['function']['name'], 'work__read')
        self.assertEqual(request['messages'][-2]['reasoning_details'], cache['c1']['reasoning_details'])
        self.assertEqual(request['messages'][-1]['content'], 'Exact result')

    def test_messages_preserves_multiple_calls_and_exact_results(self):
        body = {'system': [{'type': 'text', 'text': 'System'}], 'messages': [
            {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'a', 'name': 'read', 'input': {'x': 1}},
                                              {'type': 'tool_use', 'id': 'b', 'name': 'read', 'input': {'x': 2}}]},
            {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'a', 'content': 'one'},
                                        {'type': 'tool_result', 'tool_use_id': 'b', 'content': 'two'}]}]}
        request = chat_request(body, 'messages', 'same-model', {})
        self.assertEqual([m['tool_call_id'] for m in request['messages'][-2:]], ['a', 'b'])
        self.assertEqual(len(request['messages'][1]['tool_calls']), 2)

    def test_finish_and_usage_are_preserved(self):
        data = {'choices': [{'message': {'content': 'done'}, 'finish_reason': 'length'}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
        response = responses_reply(data, 'model')
        self.assertEqual(response['status'], 'incomplete')
        self.assertEqual(list(response_events(response))[-1]['type'], 'response.incomplete')
        message = messages_reply(data, 'model')
        self.assertEqual(message['stop_reason'], 'max_tokens')
        self.assertEqual(list(message_events(message))[-2]['usage']['output_tokens'], 5)

    def test_unimplemented_content_is_rejected_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            chat_request({'input': [{'role': 'user', 'content': [{'type': 'input_image'}]}]}, 'responses', 'm', {})
        with self.assertRaises(ValueError):
            chat_request({'previous_response_id': 'opaque'}, 'responses', 'm', {})

    def test_nullable_integer_and_null_strings_coerce_without_touching_string_fields(self):
        schemas = {'execute_dispatch': {'type': 'object', 'properties': {
            'revision': {'type': 'integer'},
            'batch_size': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 4},
            'note': {'type': ['string', 'null']}}}}
        data = {'choices': [{'message': {'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {
                'name': 'execute_dispatch', 'arguments': '{"batch_size":"4","revision":"8","note":"4"}'}}]},
            'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}}
        resp = responses_reply(data, 'z-ai/glm-5.3', schemas)
        parsed = json.loads(resp['output'][0]['arguments'])
        self.assertEqual(parsed, {'batch_size': 4, 'revision': 8, 'note': '4'})
        null_data = {'choices': [{'message': {'tool_calls': [
            {'id': 'c2', 'type': 'function', 'function': {
                'name': 'execute_dispatch', 'arguments': '{"batch_size":"null","revision":8,"note":"null"}'}}]},
            'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}}
        parsed_null = json.loads(responses_reply(null_data, 'z-ai/glm-5.3', schemas)['output'][0]['arguments'])
        self.assertEqual(parsed_null, {'batch_size': None, 'revision': 8, 'note': 'null'})


if __name__ == '__main__':
    unittest.main()
