# 发布细节

一次发布 = 部署平台对某个 git ref 跑仓库根 `build.sh`，得到 `outputs/`，再 rsync 到 runtime。

调用方只有：

- `POST :4220/api/deploy-notify {serviceId:"home-agent-brain", ref}`
- 平台 `release.sh home-agent-brain [ref]`

本仓库没有「本地一键上线」脚本。`outputs/` gitignore。`VERSION` / `COMMIT` / `GIT_REPO_URL` 由调用方写入，本脚本不写。

## `build.sh` 约定

- cwd = 仓库根；`APP_VERSION` = 8 位短 hash。
- 必须产出 `outputs/`，且含 `scripts/restart.sh`。
- 不进包：`.venv`、`.env`、`data/`、`logs/`、`llm_logs/`、`uploads/`、`__pycache__`。
- 产物：`outputs/{home_brain.py, README.md, .gitignore, scripts/*.sh, server/**}`。
- Python 依赖由目标机 `start.sh` 装，不把 venv 打进包。

合入 `main` ≠ 已上线。
