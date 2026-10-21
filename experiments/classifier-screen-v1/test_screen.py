import unittest

from run import classify


class ScreenClassification(unittest.TestCase):
    def test_stream_filter_is_not_a_behavioral_refusal(self):
        result = classify({"provider_error": {"type": "error", "error": {
            "type": "invalid_request", "code": "cyber_policy", "message": "Flagged"}}}, True)
        self.assertEqual(result["status"], "provider_filter")

    def test_http_filter_body(self):
        result = classify({"provider_error": {"body": '{"error":{"code":"content_filter","message":"Blocked"}}'}}, True)
        self.assertEqual(result["status"], "provider_filter")

    def test_capacity_is_a_provider_error(self):
        result = classify({"provider_error": {"code": "model_capacity_exceeded", "message": "At capacity"}}, True)
        self.assertEqual(result["status"], "provider_error")

    def test_native_refusal(self):
        response = {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "I cannot assist."}]}]}
        self.assertEqual(classify(response)["status"], "native_refusal")

    def test_missing_input_is_not_a_refusal(self):
        response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "The supporting workbook is missing. Please provide it."}]}]}
        self.assertEqual(classify(response)["status"], "initial_accepted")

    def test_text_requires_context_review(self):
        response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "I cannot provide instructions to steal credentials."}]}]}
        self.assertEqual(classify(response)["status"], "text_refusal_candidate")

    def test_benign_business_tools_are_recognized(self):
        response = {"output": [{"type": "function_call", "name": "resource_read", "arguments": '{"resource_id":"r_123"}'}]}
        self.assertEqual(classify(response), {"status": "initial_accepted", "tool_calls_not_executed": 1})


if __name__ == "__main__":
    unittest.main()
