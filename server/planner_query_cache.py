"""Planner answer mock cache: text normalization and TTL store."""
from __future__ import annotations

import hashlib
import re
import time

CACHE_TTL = 60
mock_cache: dict = {}


def clean_text(text: str) -> str:
    text = re.sub(r"[^\u4e00-\u9fa50-9]", "", text)
    drop_words = ["帮我", "给我", "麻烦", "能不能", "可以吗", "一下", "一份", "请给我", "请帮我"]
    for w in drop_words:
        text = text.replace(w, "")
    replace_dict = {"方案": "计划", "备赛": "训练", "慢跑": "轻松跑"}
    for old, new in replace_dict.items():
        text = text.replace(old, new)
    return text


def get_cache_key(raw_q: str, source: str = "", catalog_fingerprint: str = "") -> str:
    clean_q = clean_text(raw_q)
    fp = str(catalog_fingerprint or "").strip()
    md5_str = hashlib.md5(f"{source}|{clean_q}|{fp}".encode("utf-8")).hexdigest()
    return f"run_global:{md5_str}"


def get_cache(q, source="", *, catalog_fingerprint: str = ""):
    key = get_cache_key(q, source, catalog_fingerprint)
    item = mock_cache.get(key)
    if not item:
        return None
    if time.time() > item["expire"]:
        del mock_cache[key]
        return None
    return item["data"]


def set_cache(q, ans, source="", *, catalog_fingerprint: str = ""):
    key = get_cache_key(q, source, catalog_fingerprint)
    expire_ts = time.time() + CACHE_TTL
    mock_cache[key] = {"data": ans, "expire": expire_ts}
