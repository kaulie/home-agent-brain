# 技术栈

以 `server/requirements.txt`、`scripts/start.sh`、`build.sh` 为准。不列计划中的栈。

| 项 | 事实 |
|---|---|
| 语言 | Python 3.10+ |
| Web | **Flask**（唯一写进 requirements 的三方库） |
| 进程入口 | `server/home_brain.py`；shim `home_brain.py` |
| 规划 LLM | 火山方舟（`ARK_API_KEY`），prompt 文件在 `server/prompts/` |
| 库 | SQLite（stdlib） |
| 单测 | `unittest`，`server/tests/` |

## 构建

| 工具 | 用途 |
|---|---|
| `build.sh` | 发版包装 → `outputs/`（必须含 `scripts/restart.sh`） |
| `scripts/start.sh` | 目标机建 venv、按 requirements 装 Flask、起进程 |

无 Docker 作为一等部署路径。无根 `package.json`。本检出无 `.github/workflows`。

## 本仓库没有的东西

- 无 Mac plugin、无 iOS/Android 工程
- 无 Paddle / MediaPipe（OCR / 指字在 sidecar）
- 无应用内发版 API
