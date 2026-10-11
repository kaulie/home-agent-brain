"""Brain reads planner ads from the marketplace API."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capability_ads import attach, composition_of, decomposes_to  # noqa: E402
from marketplace_catalog import (  # noqa: E402
    ads_from_payload,
    overlay_declaration,
    pin_ads,
    reset_ads,
)


SAMPLE = {
    "capabilities": [
        {
            "capability_id": "xiaodu.play",
            "kind": "output",
            "composition": "atomic",
            "role": "小度音箱音频播放器",
            "planner_recognize": "把一条可拉流的 http(s) 音频 URL 交给客厅小度",
            "typical_triggers": ["用小度播放"],
            "do_not_dispatch": ["本机网易云开播"],
            "in_catalog": True,
        },
        {
            "capability_id": "camera.capture_and_upload",
            "kind": "action",
            "composition": "composite",
            "role": "拍照并上传器",
            "planner_recognize": "拍一张并上传",
            "typical_triggers": ["拍张照片我看一下"],
            "do_not_dispatch": ["投屏本身"],
            "decomposes_to": ["camera.capture", "asset.upload"],
            "prefer_when": "优先本能力",
            "in_catalog": True,
        },
    ]
}


class MarketplaceCatalogTest(unittest.TestCase):
    def tearDown(self) -> None:
        reset_ads()

    def test_ads_from_payload_keeps_decomposes_order(self) -> None:
        ads = ads_from_payload(SAMPLE)
        self.assertEqual(ads["xiaodu.play"]["kind"], "output")
        self.assertEqual(
            ads["camera.capture_and_upload"]["decomposes_to"],
            ["camera.capture", "asset.upload"],
        )

    def test_pin_ads_drives_attach_and_composition(self) -> None:
        pin_ads(ads_from_payload(SAMPLE))
        cap = attach("xiaodu.play", input_schema={"url": {"type": "string"}})
        self.assertEqual(cap["role"], "小度音箱音频播放器")
        self.assertEqual(cap["input_schema"]["url"]["type"], "string")
        self.assertEqual(composition_of("camera.capture_and_upload"), "composite")
        self.assertEqual(
            decomposes_to("camera.capture_and_upload"),
            ["camera.capture", "asset.upload"],
        )

    def test_overlay_fills_empty_heartbeat_fields(self) -> None:
        pin_ads(ads_from_payload(SAMPLE))
        row = overlay_declaration(
            {
                "capability_id": "xiaodu.play",
                "role": "",
                "planner_recognize": "",
                "typical_triggers": [],
                "edge_id": "mac-1",
            }
        )
        self.assertEqual(row["role"], "小度音箱音频播放器")
        self.assertEqual(row["typical_triggers"], ["用小度播放"])
        self.assertEqual(row["edge_id"], "mac-1")

    def test_overlay_keeps_named_heartbeat_overrides(self) -> None:
        pin_ads(ads_from_payload(SAMPLE))
        row = overlay_declaration(
            {
                "capability_id": "xiaodu.play",
                "role": "儿童房小度",
                "planner_recognize": "只控制儿童房那台",
            }
        )
        self.assertEqual(row["role"], "儿童房小度")
        self.assertEqual(row["planner_recognize"], "只控制儿童房那台")

    def test_http_fetch(self) -> None:
        payload = json.dumps(SAMPLE).encode("utf-8")

        class _Resp:
            def read(self) -> bytes:
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        reset_ads()
        with patch("marketplace_catalog.urllib.request.urlopen", return_value=_Resp()):
            from marketplace_catalog import refresh_ads

            ads = refresh_ads(force=True)
        self.assertIn("xiaodu.play", ads)
        self.assertEqual(ads["xiaodu.play"]["kind"], "output")


if __name__ == "__main__":
    unittest.main()
