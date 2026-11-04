"""DeepSeek client and default LLM provider wiring."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import deepseek_client as ds
import llm_provider as llm


class DeepSeekClientTests(unittest.TestCase):
    def test_build_planner_payload_has_json_object_not_extra_body(self):
        payload = ds.build_planner_payload("sys", "user", model="deepseek-v4-pro")
        self.assertEqual(payload["model"], "deepseek-v4-pro")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertNotIn("extra_body", payload)

    def test_post_chat_completions_success(self):
        raw = json.dumps(
            {"choices": [{"message": {"content": '{"plan":[]}'}}]}
        ).encode("utf-8")

        def fake_urlopen(_req, timeout=180):
            return MagicMock(read=lambda: raw)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = ds.post_chat_completions({"model": "m", "messages": []}, timeout=5)
        self.assertEqual(resp.content, '{"plan":[]}')
        self.assertGreaterEqual(resp.cost_ms, 0)

    def test_default_provider_is_deepseek(self):
        llm.configure_from_env()
        self.assertEqual(llm.active_planner_provider_id(), "deepseek")
        self.assertEqual(llm.planner_cloud_service_id(), "deepseek.planner")
        payload = llm.build_planner_payload("s", "u", model="deepseek-v4-pro")
        self.assertNotIn("extra_body", payload)
        self.assertEqual(payload["thinking"]["type"], "disabled")

    def test_volcano_ark_payload_via_provider_swap(self):
        llm.set_planner_transport(None, provider_id="volcano_ark")
        try:
            self.assertEqual(llm.active_planner_provider_id(), "volcano_ark")
            self.assertEqual(llm.planner_cloud_service_id(), "ark.planner")
            payload = llm.build_planner_payload("s", "u", model="ep-test")
            self.assertEqual(payload["extra_body"]["thinking"]["type"], "disabled")
        finally:
            llm.configure_from_env()


if __name__ == "__main__":
    unittest.main()
