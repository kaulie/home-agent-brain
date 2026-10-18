"""Admin display values extracted from home_brain keep their historical output."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

os.environ.setdefault("BRAIN_SKIP_LLM_WORKER", "1")

import admin_values as admin

try:
    import flask  # noqa: F401
except ImportError:  # pragma: no cover
    flask = None  # type: ignore


class AdminValuesTests(unittest.TestCase):
    def test_policy_summary_wording(self):
        tv = {"display_name": "客厅电视", "location": "客厅"}
        phone = {"display_name": "iPhone", "room": "卧室"}
        cases = [
            (dict(participant_id="p1", target_kind="role", target_id="runtime",
                  enabled=False, rec=tv), "关掉 客厅电视 的 执行 Runtime"),
            (dict(participant_id="p1", target_kind="capability",
                  target_id="camera.capture", enabled=True, rec=phone),
             "打开 卧室 · iPhone 的 camera.capture"),
            (dict(participant_id="p1", action="policy_replace"), "改写 p1 的调度策略"),
            (dict(target_kind="role", target_id="x", rec={}), "改 节点 的 x"),
            ({}, "管理 节点"),
            (dict(participant_id="p2", target_kind="role", target_id="endpoint",
                  enabled=True, error="boom"), "打开 p2 的 呈现 Endpoint 失败：boom"),
        ]
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(admin.admin_policy_summary(**kwargs), expected)

    def test_node_title_fallbacks(self):
        self.assertEqual(admin.admin_node_title({"edge_id": "e9"}), "e9")
        self.assertEqual(admin.admin_node_title(None, "pid"), "pid")
        self.assertEqual(
            admin.admin_node_title({"display_name": "客厅电视", "location": "客厅"}),
            "客厅电视",
        )
        self.assertEqual(admin.admin_target_title("ROLE", "observer"), "观察 Observer")
        self.assertEqual(admin.admin_target_title("capability", " a.b "), "a.b")

    def test_policy_items_from_body(self):
        body = {
            "roles": {"runtime": 0},
            "capabilities": {"a.b": 1},
            "items": [{"target_kind": "role"}, "bad"],
        }
        self.assertEqual(
            admin.policy_items_from_body(body),
            [
                {"target_kind": "role", "target_id": "runtime", "enabled": False},
                {"target_kind": "capability", "target_id": "a.b", "enabled": True},
                {"target_kind": "role"},
            ],
        )
        self.assertEqual(admin.policy_items_from_body({"roles": ["x"], "items": {}}), [])

    def test_step_status_text(self):
        steps = [{"status": 2}, {"status": "success"}, {"status": 3}, {"status": "1"},
                 {"status": None}, {}, "x", {"status": "queued"}, {"status": 0}]
        self.assertEqual(
            [admin.step_status_text(s) for s in steps],
            ["succeeded", "succeeded", "failed", "running", "", "", "", "queued", ""],
        )


@unittest.skipUnless(flask is not None, "flask not installed in this interpreter")
class HomeBrainReexportTests(unittest.TestCase):
    def test_historical_names_are_the_extracted_helpers(self):
        import home_brain as hb

        self.assertIs(hb._ADMIN_ROLE_LABELS, admin.ADMIN_ROLE_LABELS)
        self.assertIs(hb._admin_node_title, admin.admin_node_title)
        self.assertIs(hb._admin_target_title, admin.admin_target_title)
        self.assertIs(hb._admin_policy_summary, admin.admin_policy_summary)
        self.assertIs(hb._policy_items_from_body, admin.policy_items_from_body)
        self.assertIs(hb._step_status_text, admin.step_status_text)


if __name__ == "__main__":
    unittest.main()
