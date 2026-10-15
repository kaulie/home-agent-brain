"""Smoke tests for modules split out of home_brain.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import endpoint_participant_values as epv
import intent_source_context as src
import intent_status_values as status
import planner_query_cache as pqcache
import plan_presentation_kind as ppk


class SplitModuleTests(unittest.TestCase):
    def test_endpoint_supported_types_default(self):
        rec = {"endpoints": [{"type": "display", "endpoint_id": "tv-1"}]}
        types = epv.endpoint_supported_types(rec)
        self.assertIn("image", types)
        self.assertIn("text", types)

    def test_build_source_context_voice(self):
        ctx = src.build_source_context("iphone-1", "voice", {})
        self.assertEqual(ctx["device_id"], "iphone-1")
        self.assertEqual(ctx["capability_id"], "voice.input")

    def test_planner_cache_key_stable(self):
        k1 = pqcache.get_cache_key("打开灯", "voice", "abc")
        k2 = pqcache.get_cache_key("打开灯", "voice", "abc")
        self.assertEqual(k1, k2)

    def test_status_alias(self):
        self.assertEqual(status.normalize_status("success"), "succeeded")

    def test_presentation_kind_clock(self):
        intent = {
            "source": "voice",
            "text": "几点了",
            "execution_plan": [{"capability": "clock.now", "step": 1}],
        }

        def emits(_plan, field):
            return field == "time_text"

        ptype, from_key = ppk.presentation_kind_from_plan(intent, plan_emits_field=emits)
        self.assertEqual(ptype, "audio")
        self.assertEqual(from_key, "time_text")


if __name__ == "__main__":
    unittest.main()
