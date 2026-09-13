# home-agent-brain

Home Agent OS 的 **Brain 控制面**独立仓库。

代码自 [`kaulie/home-agent-os`](https://github.com/kaulie/home-agent-os) 拆分而来（源 commit
`5f5c0c6048f34f357ce1abddae2df0b74b45d051`），是一次**纯搬迁**：上游的 `server/` 与根入口
`home_brain.py` 原样复制到本仓库，未修改任何逻辑。上游 `home-agent-os` 在拆分时保持不动。

## 内容

| 路径 | 说明 |
|------|------|
| [`server/`](server/) | Brain 控制面：意图理解、能力路由、心跳、`execution_timing`、Asset、Admin API |
| [`server/home_brain.py`](server/home_brain.py) | 唯一 Brain 进程（Flask app，`:9527`） |
| [`home_brain.py`](home_brain.py) | systemd / 项目根入口 shim，转调 `server/home_brain.py` |
| [`server/README.md`](server/README.md) | 协议 / 路由 / 能力契约原文 |
| [`server/prompts/`](server/prompts/) | 规划器 system prompt（方舟） |
| [`server/sql/`](server/sql/) | SQLite schema 迁移 |
| [`server/tests/`](server/tests/) | Brain 单测 |

## 运行

```bash
export ARK_API_KEY=...
cd server && python home_brain.py   # 等价：python brain_app.py
```

Python 3.10+，无第三方依赖。协议、路由、能力契约详见 [`server/README.md`](server/README.md)。

## 边界

- 本仓库只承载 **Brain 控制面**。Edge 端的 Brain 客户端（`mac/`、`android/`、`ios/`）不在此仓库。
- `server/` 内的 sidecar（`main.py`、`photo_upload_*`、`vision_analyze_flask.py`、`audio_pickup.py`）
  与 Admin/dev 辅助模块随本次搬迁一并带入，保持目录结构与 import 不变。
