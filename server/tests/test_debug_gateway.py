"""Agent Debug Gateway API tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

os.environ["BRAIN_SKIP_LLM_WORKER"] = "1"
os.environ["BRAIN_ENABLE_DEV_TASK_POLLER"] = "1"

try:
    import flask  # noqa: F401
except ImportError:  # pragma: no cover
    flask = None  # type: ignore

if flask is not None:
    import agent_task_store  # noqa: E402
    import debug_gateway  # noqa: E402
    import debug_issue_store  # noqa: E402
    import db as brain_db  # noqa: E402
    import home_brain as hb  # noqa: E402
else:
    agent_task_store = None  # type: ignore
    debug_issue_store = None  # type: ignore
    brain_db = None  # type: ignore
    hb = None  # type: ignore


def _created_task(task_id: str = "task-feedback-1") -> dict:
    return {
        "task_id": task_id,
        "project_id": "project-cc557f77f1ac40a4",
        "task_url": f"http://127.0.0.1:4211/api/tasks/{task_id}",
    }


@unittest.skipUnless(flask is not None, "flask not installed in this interpreter")
class DebugGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        assert hb is not None
        assert brain_db is not None
        assert agent_task_store is not None
        assert debug_issue_store is not None
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "brain.sqlite3"
        brain_db.reset(path=self.path)
        brain_db.init_db()
        agent_task_store.reset_store(Path(self.tmp.name) / "agent_tasks.json")
        debug_issue_store.reset_store(Path(self.tmp.name) / "debug_issues.json")
        hb._REGISTERED_edges = brain_db.registration_ids()

    def _seed_intent(self, *, edge_id: str = "living-room-android") -> int:
        assert hb is not None
        intent_id = hb.new_intent(
            {
                "status": "failed",
                "text": "用GoPro拍张照片",
                "source": "text",
                "edge_id": edge_id,
                "msg": "家里有多台同能力设备",
            }
        )
        return int(intent_id)

    def test_post_debug_report_creates_issue_and_web_cursor_task(self) -> None:
        assert hb is not None
        intent_id = self._seed_intent()
        client = hb.app.test_client()
        with patch(
            "debug_gateway.create_feedback_task",
            return_value=_created_task(),
        ) as created, patch("dev_task.bridge.submit_command") as bridge_submit:
            resp = client.post(
                "/api/v1/debug/report",
                json={
                    "intent_id": intent_id,
                    "participant_id": "living-room-android",
                    "client_snapshot": {"journey": "test logistics"},
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("message"), "已提交反馈，正在分析。")
        self.assertEqual(body.get("intent_id"), intent_id)
        self.assertEqual(body.get("web_cursor_task_id"), "task-feedback-1")
        self.assertEqual(body.get("status"), "queued")
        created.assert_called_once()
        kwargs = created.call_args.kwargs
        self.assertIn("用GoPro拍张照片", kwargs["description"])
        self.assertIn("按 web-cursor 任务处理", kwargs["description"][:2000])
        self.assertLessEqual(len(kwargs["description"]), 4000)
        bridge_submit.assert_not_called()
        issue_id = int(body["issue_id"])
        detail = client.get(f"/api/v1/admin/debug/issue/{issue_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else payload
        snap = (issue.get("context") or {}).get("client_snapshot") or {}
        self.assertEqual(snap.get("journey"), "test logistics")
        self.assertEqual(issue.get("web_cursor_task_id"), "task-feedback-1")
        self.assertEqual(issue.get("status"), "queued")

    def test_post_debug_report_rejects_wrong_participant(self) -> None:
        assert hb is not None
        intent_id = self._seed_intent(edge_id="edge-a")
        client = hb.app.test_client()
        resp = client.post(
            "/api/v1/debug/report",
            json={"intent_id": intent_id, "participant_id": "edge-b"},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("ok"))

    def test_post_debug_report_pickup_without_intent(self) -> None:
        assert hb is not None
        client = hb.app.test_client()
        with patch("debug_gateway.create_feedback_task", return_value=_created_task()):
            resp = client.post(
                "/api/v1/debug/report",
                json={
                    "intent_id": 0,
                    "participant_id": "pickup-iphone-test",
                    "source": "pickup_terminal",
                    "problem_type": "execution_error",
                    "user_summary": "显示正在听但电平不动",
                    "client_snapshot": {
                        "source": "pickup_terminal",
                        "device_id": "pickup-iphone-test",
                        "user_listening": True,
                        "audio_level": 0,
                        "capture_state": "采集中",
                    },
                },
            )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("intent_id"), 0)
        issue_id = int(body["issue_id"])
        detail = client.get(f"/api/v1/admin/debug/issue/{issue_id}")
        issue = detail.get_json().get("issue") or detail.get_json()
        self.assertEqual(issue.get("source"), "pickup_terminal")
        snap = (issue.get("context") or {}).get("client_snapshot") or {}
        self.assertEqual(snap.get("device_id"), "pickup-iphone-test")

    def test_post_debug_report_rejects_zero_intent_for_console(self) -> None:
        assert hb is not None
        client = hb.app.test_client()
        resp = client.post(
            "/api/v1/debug/report",
            json={
                "intent_id": 0,
                "participant_id": "living-room-android",
                "source": "user_console",
            },
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("ok"))

    def test_post_debug_report_with_other_problem_type(self) -> None:
        assert hb is not None
        intent_id = self._seed_intent()
        client = hb.app.test_client()
        with patch("debug_gateway.create_feedback_task", return_value=_created_task()):
            resp = client.post(
                "/api/v1/debug/report",
                json={
                    "intent_id": intent_id,
                    "participant_id": "living-room-android",
                    "problem_type": "other",
                    "user_summary": "语音识别错了，我说的是客厅不是卧室",
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        issue_id = int(body["issue_id"])
        detail = client.get(f"/api/v1/admin/debug/issue/{issue_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else payload
        self.assertEqual(issue.get("problem_type"), "other")
        self.assertEqual(issue.get("problem_type_label"), "其他")
        self.assertIn("语音识别错了", issue.get("user_summary") or "")

    def test_post_debug_report_with_attachments(self) -> None:
        assert hb is not None
        intent_id = self._seed_intent()
        client = hb.app.test_client()
        with patch("debug_gateway.create_feedback_task", return_value=_created_task()):
            resp = client.post(
                "/api/v1/debug/report",
                json={
                    "intent_id": intent_id,
                    "participant_id": "living-room-android",
                    "problem_type": "execution_error",
                    "attachments": [
                        {"asset_id": "asset_abc123", "kind": "image", "mime_type": "image/jpeg"},
                        {"asset_id": "asset_abc123", "kind": "image"},
                        {"asset_id": "asset_def456", "kind": "file", "filename": "log.txt"},
                    ],
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        issue_id = int(body["issue_id"])
        detail = client.get(f"/api/v1/admin/debug/issue/{issue_id}")
        issue = detail.get_json().get("issue") or detail.get_json()
        attachments = issue.get("attachments") or []
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0]["asset_id"], "asset_abc123")
        self.assertEqual(attachments[0]["kind"], "image")
        self.assertEqual(attachments[1]["kind"], "file")
        self.assertEqual(issue.get("attachment_asset_ids"), ["asset_abc123", "asset_def456"])

    def test_admin_list_debug_issues(self) -> None:
        assert hb is not None
        intent_id = self._seed_intent()
        client = hb.app.test_client()
        with patch("debug_gateway.create_feedback_task", return_value=_created_task()):
            client.post(
                "/api/v1/debug/report",
                json={"intent_id": intent_id, "participant_id": "living-room-android"},
            )
        resp = client.get("/api/v1/admin/debug/issues?limit=10")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        issues = body.get("issues") or []
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["intent_id"], intent_id)
        self.assertEqual(issues[0].get("web_cursor_task_id"), "task-feedback-1")
        self.assertIn("/api/tasks/task-feedback-1", issues[0].get("web_cursor_task_url") or "")
        self.assertNotIn("dev_task", issues[0])

    def test_post_debug_report_marks_failed_when_web_cursor_errors(self) -> None:
        assert hb is not None
        import web_cursor_feedback

        intent_id = self._seed_intent()
        client = hb.app.test_client()
        with patch(
            "debug_gateway.create_feedback_task",
            side_effect=web_cursor_feedback.WebCursorError("web-cursor 连不上"),
        ):
            resp = client.post(
                "/api/v1/debug/report",
                json={"intent_id": intent_id, "participant_id": "living-room-android"},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get("ok"))
        self.assertIn("web-cursor", body.get("error") or "")
        issue_id = int(body["issue_id"])
        detail = client.get(f"/api/v1/admin/debug/issue/{issue_id}")
        issue = detail.get_json().get("issue") or detail.get_json()
        self.assertEqual(issue.get("status"), "failed")
        self.assertNotIn("web_cursor_task_id", issue)

    def test_build_feedback_description_asks_for_a_fix(self) -> None:
        assert debug_gateway is not None
        issue = debug_issue_store.DebugIssue(
            issue_id=1,
            intent_id=42,
            session_id="sess-1",
            source="user_console",
            participant_id="living-room-android",
            status="queued",
            user_summary="执行失败",
            problem_type="execution_error",
            attachments=[{"asset_id": "asset_abc", "kind": "image"}],
            task_id=None,
            error="",
            context={
                "user_input": "开灯",
                "intent_status": "failed",
                "error": "timeout",
                "execution_plan": ["x" * 3000],
                "step_log": ["y" * 3000],
            },
            created_at=1.0,
            updated_at=1.0,
        )
        text = debug_gateway.build_feedback_description(issue, issue.context)
        self.assertLessEqual(len(text), 4000)
        self.assertIn("按 web-cursor 任务处理", text[:2000])
        self.assertIn("开灯", text[:2000])
        self.assertIn("asset_abc", text[:2000])
        self.assertNotIn("## 修复建议", text)
        title = debug_gateway.feedback_task_title(issue)
        self.assertIn("intent #42", title)
        self.assertIn("执行报错", title)


if __name__ == "__main__":
    unittest.main()
