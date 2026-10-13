"""web-cursor feedback task client."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import web_cursor_feedback as wc  # noqa: E402


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class WebCursorFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        wc.reset_project_cache()
        self._env = {
            key: os.environ.get(key)
            for key in (
                "WEB_CURSOR_BASE_URL",
                "WEB_CURSOR_FEEDBACK_PROJECT",
                "WEB_CURSOR_FEEDBACK_PROJECT_ID",
                "WEB_CURSOR_FEEDBACK_GOAL",
                "WEB_CURSOR_FEEDBACK_TASK_TYPE",
            )
        }
        for key in self._env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        wc.reset_project_cache()
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_create_task_resolves_project_by_name(self) -> None:
        calls: list[tuple[str, dict | None]] = []

        def fake_urlopen(req, timeout=0):
            body = req.data.decode("utf-8") if req.data else None
            payload = json.loads(body) if body else None
            calls.append((req.full_url, payload))
            if req.full_url.endswith("/api/projects"):
                raw = json.dumps(
                    [
                        {"projectId": "project-other", "name": "home-agent"},
                        {"projectId": "project-fb", "name": "home-agent-feedback"},
                    ]
                ).encode()
            else:
                raw = json.dumps(
                    {"taskId": "task-abc", "projectId": payload["projectId"]}
                ).encode()
            return _Resp(raw)

        with patch("web_cursor_feedback.urllib.request.urlopen", side_effect=fake_urlopen):
            created = wc.create_feedback_task(title="用户反馈", description="修一下")
        self.assertEqual(created["task_id"], "task-abc")
        self.assertEqual(created["project_id"], "project-fb")
        self.assertEqual(created["task_url"], "http://127.0.0.1:4211/api/tasks/task-abc")
        self.assertEqual(calls[1][1]["projectId"], "project-fb")
        self.assertEqual(calls[1][1]["taskType"], "bugfix")
        self.assertEqual(calls[1][1]["goal"], "merge")
        self.assertEqual(calls[1][1]["description"], "修一下")

        calls.clear()
        with patch("web_cursor_feedback.urllib.request.urlopen", side_effect=fake_urlopen):
            again = wc.create_feedback_task(title="第二条", description="还是修")
        self.assertEqual(again["task_id"], "task-abc")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith("/api/tasks"))

    def test_project_id_override_skips_lookup(self) -> None:
        os.environ["WEB_CURSOR_FEEDBACK_PROJECT_ID"] = "project-explicit"
        os.environ["WEB_CURSOR_FEEDBACK_GOAL"] = "deploy"
        calls: list[str] = []

        def fake_urlopen(req, timeout=0):
            calls.append(req.full_url)
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["projectId"], "project-explicit")
            self.assertEqual(payload["goal"], "deploy")
            return _Resp(json.dumps({"taskId": "task-explicit"}).encode())

        with patch("web_cursor_feedback.urllib.request.urlopen", side_effect=fake_urlopen):
            created = wc.create_feedback_task(title="t", description="d")
        self.assertEqual(created["task_id"], "task-explicit")
        self.assertEqual(calls, ["http://127.0.0.1:4211/api/tasks"])

    def test_http_error_surfaces_message(self) -> None:
        os.environ["WEB_CURSOR_FEEDBACK_PROJECT_ID"] = "project-missing"

        def fake_urlopen(req, timeout=0):
            raise urllib.error.HTTPError(
                req.full_url,
                400,
                "bad",
                hdrs=None,
                fp=io.BytesIO(json.dumps({"error": "project project-missing not found"}).encode()),
            )

        with patch("web_cursor_feedback.urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(wc.WebCursorError) as caught:
                wc.create_feedback_task(title="t", description="d")
        self.assertIn("project-missing not found", str(caught.exception))

    def test_missing_project_name(self) -> None:
        def fake_urlopen(req, timeout=0):
            return _Resp(json.dumps([{"projectId": "project-other", "name": "home-agent"}]).encode())

        with patch("web_cursor_feedback.urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(wc.WebCursorError) as caught:
                wc.resolve_feedback_project_id()
        self.assertIn("home-agent-feedback", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
