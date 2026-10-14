"""Contracts for model responses and execution values, without Brain startup."""
import copy
import io
from pathlib import Path
import sys
import unittest
import urllib.error

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import model_response as model
import execution_step_values as steps


class ModelResponseTests(unittest.TestCase):
    def test_request_redaction_is_recursive_and_does_not_mutate_payload(self):
        payload = {"Authorization": "secret", "messages": [
            {"text": "hello", "nested": {"API_KEY": "secret", "safe": 1}}]}
        before = copy.deepcopy(payload)
        result = model._ark_result(request_payload=payload, cost_ms="12", cache_hit=1)
        self.assertEqual(result["request_payload"], {
            "messages": [{"text": "hello", "nested": {"safe": 1}}]})
        self.assertEqual(payload, before)
        self.assertEqual(result["cost_ms"], 12)
        self.assertIs(result["cache_hit"], True)

    def test_http_error_parsing_preserves_provider_contract(self):
        for body, expected in [
            (b'{"error":{"code":"AccountOverdueError"}}',
             {"http_status": 403, "error": {"code": "AccountOverdueError"}}),
            (b'x' * 9000, {"http_status": 403, "body": "x" * 8000}),
            (b'[]', {"http_status": 403, "body": "[]"}),
        ]:
            with self.subTest(body=body[:20]):
                with urllib.error.HTTPError("https://example.test", 403, "error",
                                            {}, io.BytesIO(body)) as error:
                    self.assertEqual(model._ark_http_error_json(error), expected)
        self.assertIn("欠费", model._ark_http_error_msg({
            "http_status": 403, "error": {"code": "AccountOverdueError"}}))
        self.assertIsNone(model._ark_http_error_msg({"http_status": "invalid"}))
        self.assertLessEqual(len(model._ark_http_error_msg({
            "http_status": 500, "body": "x" * 9000})), 240)

    def test_provider_reply_shapes_and_fallbacks_remain_distinct(self):
        self.assertEqual(model.get_model_answer({"output": [{
            "type": "message", "content": [{"text": "answer"}]}]}), "answer")
        self.assertEqual(model.get_model_answer({}), "暂时无法获取回答")
        self.assertEqual(model.get_model_answer(None), "数据解析失败")
        for payload in ["answer", {"reply": "answer"},
                        {"output": {"content": "answer"}},
                        {"message": {"text": "answer"}}]:
            self.assertEqual(model._qwen_reply_text(payload), "answer")
        self.assertEqual(model._qwen_reply_text({}), "")


class ExecutionStepValueTests(unittest.TestCase):
    def test_terminal_status_is_separate_from_successful_predecessor(self):
        self.assertFalse(steps._plan_steps_all_terminal([]))
        self.assertTrue(steps._plan_steps_all_terminal([{"status": "2"}, {"status": 3}]))
        self.assertFalse(steps._plan_steps_all_terminal([{"status": "bad"}]))
        plan = [{"step": 1, "status": "2"}, {"step": 2, "status": 0}]
        self.assertTrue(steps._system_predecessors_succeeded(plan, 2))
        plan[0]["status"] = 3
        self.assertFalse(steps._system_predecessors_succeeded(plan, 2))
        plan[0]["status"] = "bad"
        self.assertFalse(steps._system_predecessors_succeeded(plan, 2))

    def test_upload_failure_only_claims_capture_success_when_it_precedes_upload(self):
        plan = [{"step": 1, "capability": "camera.capture", "status": 2}]
        failure = {"step": 2}
        message = steps._upload_failure_msg(plan, failure, "network error")
        self.assertEqual(message, "拍照成功，照片已保存在本机；但上传失败：network error")
        self.assertEqual(steps._upload_failure_msg(plan, failure, message), message)
        self.assertEqual(steps._upload_failure_msg(plan, {"step": 1}, "error"), "error")
        plan[0]["status"] = 3
        self.assertEqual(steps._upload_failure_msg(plan, failure, "error"), "error")

    def test_context_resolution_preserves_missing_tokens_and_false_values(self):
        raw = {"zero": "$zero", "flag": "$flag", "missing": "$missing",
               "none": "$none", "literal": "prefix $zero", "nested": {"x": "$zero"}}
        before = copy.deepcopy(raw)
        context = {"zero": 0, "flag": False, "none": None}
        expected = dict(raw, zero=0, flag=False)
        self.assertEqual(steps._resolve_system_params(raw, {"ctx_param": context}), expected)
        self.assertEqual(steps._resolve_system_params(raw, {"context": context}), expected)
        self.assertEqual(steps._resolve_system_params(raw, {"context": "invalid"}), raw)
        self.assertEqual(raw, before)


if __name__ == "__main__":
    unittest.main()
