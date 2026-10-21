import unittest

from refusal_watch import find_candidates, provider_filters


class RefusalDetectionTests(unittest.TestCase):
    subject = {"tools": [{"name": "bash"}]}

    def test_stream_cyber_policy_envelope(self):
        event = {"provider_error": {"type": "error", "sequence_number": 15,
                 "error": {"code": "cyber_policy", "type": "invalid_request",
                           "message": "This content was flagged for possible cybersecurity risk."}}}
        found = provider_filters(event, self.subject, "stream_or_http_error")
        self.assertEqual(found[0]["kind"], "provider_filter")
        self.assertEqual(found[0]["code"], "cyber_policy")
        self.assertEqual(found[0]["model_role"], "subject")

    def test_http_filter_body(self):
        event = {"http_status": 400, "body": '{"error":{"code":"cyber_policy","message":"filtered"}}'}
        self.assertEqual(provider_filters(event, self.subject, "http")[0]["code"], "cyber_policy")

    def test_native_refusal(self):
        response = {"output": [{"type": "message", "content": [
                    {"type": "refusal", "refusal": "I cannot assist with that."}]}]}
        self.assertEqual(find_candidates(response, self.subject)[0]["kind"], "native_refusal")

    def test_blocked_task_is_not_refusal(self):
        response = {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "I cannot complete the workbook because the data are unavailable."}]}]}
        self.assertEqual(find_candidates(response, self.subject), [])

    def test_judge_text_excluded(self):
        response = {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "I cannot help with that."}]}]}
        self.assertEqual(find_candidates(response, {"tools": []}), [])

    def test_generic_errors_are_not_filters(self):
        for error in ({"code": "invalid_prompt", "message": "Expected an array"},
                      {"code": "rate_limit_exceeded", "message": "At capacity"}):
            self.assertEqual(provider_filters({"error": error}, self.subject, "test"), [])


if __name__ == "__main__":
    unittest.main()
