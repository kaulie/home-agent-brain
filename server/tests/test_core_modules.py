"""Regression coverage for the dependency boundaries extracted from home_brain."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import asset_values as assets
import plan_normalization as plans
import planner_output as output
import presentation_policy as presentation
import provider_selection as providers


class CoreModuleTests(unittest.TestCase):
    def test_helpers_import_without_starting_brain_in_both_layouts(self):
        modules = ("asset_values", "plan_normalization", "planner_output",
                   "presentation_policy", "provider_selection",
                   "model_response", "execution_step_values")
        for prefix, cwd in (("", SERVER), ("server.", SERVER.parent)):
            with self.subTest(prefix=prefix):
                script = (
                    "import importlib, sys, threading; "
                    "before = threading.active_count(); "
                    f"[importlib.import_module({prefix!r} + n) for n in {modules!r}]; "
                    "assert threading.active_count() == before; "
                    "assert not any(n in sys.modules for n in "
                    "('home_brain', 'server.home_brain', 'flask', 'db', 'server.db'))"
                )
                subprocess.run([sys.executable, "-c", script], cwd=cwd, check=True)

    def test_live_provider_lookup_is_not_cached_and_input_is_not_mutated(self):
        plan = [
            {"step": 1, "capability": "camera.capture", "input_constrict": {}},
            {"step": 2, "capability": "asset.upload",
             "input_constrict": {"capture_ref": "$capture_ref"}},
        ]
        before = copy.deepcopy(plan)
        lookup = Mock(side_effect=[[], [{"edge_id": "camera-one"}]])
        first = plans.sanitize_execution_plan(plan, online_capability_providers=lookup)
        second = plans.sanitize_execution_plan(plan, online_capability_providers=lookup)
        self.assertEqual(len(first), 2)
        self.assertEqual(second[0]["capability"], "camera.capture_and_upload")
        self.assertEqual(second[0]["assigned_edge_id"], "camera-one")
        self.assertEqual(len(second), 1)
        self.assertEqual(plan, before)
        self.assertEqual(lookup.call_count, 2)

    def test_shortcut_preserves_speech_but_planner_filters_it(self):
        plan = [{"capability": "notify.speak", "input_constrict": {"text": "hello"}}]
        lookup = Mock(return_value=[])
        self.assertEqual(plans.sanitize_execution_plan(plan, online_capability_providers=lookup), [])
        shortcut = plans._prepare_shortcut_execution_plan(plan, online_capability_providers=lookup)
        self.assertEqual(shortcut[0]["capability"], "notify.speak")
        self.assertEqual(shortcut[0]["step"], 1)

    def test_strict_planner_and_relaxed_shadow_json_remain_distinct(self):
        raw = '```json\n{"plan": []}\n```'
        self.assertEqual(output.extract_llm_output(raw), {})
        self.assertEqual(output.extract_llm_output_relaxed(raw), {"plan": []})
        notes = output.extract_llm_capability_notes(
            {"missing_capabilities": ["ac.set", "new.capability"]},
            [{"capability_id": "climate.set"}],
        )
        self.assertEqual(notes["missing_capabilities"], [{"capability": "new.capability", "reason": ""}])

    def test_voice_symmetry_preserves_explicit_image_request(self):
        intent = {"source": "voice", "text": "现在几点", "execution_plan": []}
        self.assertEqual(presentation._voice_symmetric_presentation_kind(
            intent, "text", "time_text"), ("audio", "time_text"))
        intent["text"] = "给我看那张照片"
        self.assertEqual(presentation._voice_symmetric_presentation_kind(
            intent, "text", "time_text"), ("text", "time_text"))

    def test_asset_views_keep_storage_out_of_public_contract(self):
        record = {
            "asset_id": "asset-one", "type": "document", "mime_type": "application/pdf",
            "storage": {"key": "original.pdf", "preview_key": "preview.jpg", "url": "private"},
            "metadata": {"url_target": "https://example.com/private", "label": "report"},
        }
        before = copy.deepcopy(record)
        public = assets._asset_public_view(record, include_storage=True)
        self.assertNotIn("storage", public)
        self.assertNotIn("url_target", public["metadata"])
        endpoint = assets._asset_endpoint_view(record, "intent-one")
        self.assertNotIn("storage", endpoint)
        self.assertEqual(endpoint["stream"]["href"],
                         "/api/v1/assets/asset-one/content?intent_id=intent-one&representation=preview")
        self.assertNotIn("url", assets._asset_runtime_view(record)["storage"])
        self.assertEqual(record, before)
        self.assertEqual(assets._parse_asset_refs_list(json.dumps([record]))[0]["asset_id"], "asset-one")

    def test_named_device_matching_prefers_longest_specific_name(self):
        groups = {"卧室": [{"edge_id": "one"}], "主卧室": [{"edge_id": "two"}]}
        self.assertEqual(providers._matched_instance_groups(groups, "打开主卧室相机"),
                         [("主卧室", [{"edge_id": "two"}])])


if __name__ == "__main__":
    unittest.main()
