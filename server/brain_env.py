"""Brain process paths and environment loading (no Flask, no DB)."""
from __future__ import annotations

import os
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, val = text.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def bootstrap_dotenv() -> None:
    # .env order: backend/.env, server/.env, repo root .env (first wins).
    load_dotenv(SERVER_DIR.parent / "backend" / ".env")
    load_dotenv(SERVER_DIR / ".env")
    if SERVER_DIR.name == "server":
        load_dotenv(SERVER_DIR.parent / ".env")


def default_log_dir() -> Path:
    env = (os.environ.get("BRAIN_LOG_DIR") or "").strip()
    if env:
        return Path(env)
    parent_logs = SERVER_DIR.parent / "llm_logs"
    if SERVER_DIR.name == "server" and parent_logs.is_dir():
        return parent_logs
    return SERVER_DIR / "llm_logs"


def default_upload_dir() -> Path:
    candidate = SERVER_DIR / "gopropics"
    if not candidate.is_dir() and SERVER_DIR.name == "server":
        candidate = SERVER_DIR.parent / "gopropics"
    if not candidate.is_dir():
        candidate = SERVER_DIR / "uploads" / "gopro"
    return Path(os.environ.get("BRAIN_UPLOAD_DIR") or candidate)


bootstrap_dotenv()

MODEL_ID = os.environ.get("ARK_MODEL_ID", "ep-20260712174403-5jcgs")
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_URL = os.environ.get(
    "ARK_URL",
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
)
ARK_RESPONSES_URL = os.environ.get(
    "ARK_RESPONSES_URL",
    "https://ark.cn-beijing.volces.com/api/v3/responses",
)
PROMPT_FILE = SERVER_DIR / "prompts" / "task_planner_system_prompt.md.en"
QWEN_PROMPT_FILE = SERVER_DIR / "prompts" / "task_planner_system_prompt.qwen-small.md.en"
QWEN_PLANNER_URL = (
    os.environ.get("QWEN_PLANNER_URL") or "http://115.190.153.53:8090/chat"
).strip()
QWEN_PLANNER_MODEL = (os.environ.get("QWEN_PLANNER_MODEL") or "Qwen2.5-0.5B-Instruct").strip()
QWEN_PLANNER_TIMEOUT_SEC = float(os.environ.get("QWEN_PLANNER_TIMEOUT_SEC") or "180")

DUEROS_PUSH_URL = "https://api.dueros.com/skill/v1/push"
SKILL_APP_ID = "25ca93b5-40b6-8ce7-8b37-78a03afb9606"
SKILL_ACCESS_TOKEN = "技能服务AccessToken"

LOG_DIR = default_log_dir()
