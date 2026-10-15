"""Volcano Ark client and LLM provider swap boundary."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import llm_provider as llm
import volcano_ark_client as ark


class VolcanoArkClientTests(unittest.TestCase):
    def test_build_planner_payload_json_object(self):
        payload = ark.build_planner_payload("sys", "user", model="ep-test")
        self.assertEqual(payload["model"], "ep-test")
        self.assertEqual(payload["messages"][0]["content"], "sys")
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_extract_assistant_content(self):
        body = {"choices": [{"message": {"content": '{"plan":[]}'}}]}
        self.assertEqual(ark.extract_assistant_content(body), '{"plan":[]}')

    def test_post_chat_completions_success(self):
        raw = json.dumps(
            {"choices": [{"message": {"content": "hello"}}]}
        ).encode("utf-8")

        def fake_urlopen(_req, timeout=180):
            return MagicMock(read=lambda: raw)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = ark.post_chat_completions({"model": "m", "messages": []}, timeout=5)
        self.assertEqual(resp.content, "hello")
        self.assertIsInstance(resp.response_json, dict)
        self.assertGreaterEqual(resp.cost_ms, 0)
        self.assertNotIn("Authorization", json.dumps(resp.request_payload))

    def test_planner_transport_swap(self):
        seen = []

        def stub_transport(payload, timeout):
            seen.append((payload.get("model"), timeout))
            return ark.ChatCompletionResponse(
                content="stub",
                response_json={"ok": True},
                cost_ms=1,
                request_payload=payload,
            )

        llm.set_planner_transport(stub_transport, provider_id="stub")
        try:
            self.assertEqual(llm.active_planner_provider_id(), "stub")
            out = llm.get_planner_transport()({"model": "x"}, 3.0)
            self.assertEqual(out.content, "stub")
            self.assertEqual(seen, [("x", 3.0)])
        finally:
            llm.set_planner_transport(None)


if __name__ == "__main__":
    unittest.main()
