# AGENT.md — 后续 Agent 对本仓库的说明与向导

你是来改 **home-agent-brain** 的。先读本文，再按 [`docs/project_map/`](docs/project_map/README.md) 展开理解。  
能力**声明**不在本仓：读集市 [`kaulie/home-agent-capabilty-marketplace`](https://github.com/kaulie/home-agent-capabilty-marketplace) 的 `GET /api/v1/export`。  
[`kaulie/home-agent-os`](https://github.com/kaulie/home-agent-os) 已归档只读，不要往 os 写代码。

协议原文仍在 [`server/README.md`](server/README.md)。`server/README.md` 回答「API 长什么样」；`docs/project_map/` 回答「这个仓库现在怎么跑、怎么改」。

## 1. 对本项目的理解（必须从 docs/project_map 展开）

把下面当成工作假设；每一条的细节在对应文档里，不在这段摘要里发明第二套说法。

| 你应建立的判断 | 展开阅读 |
|---|---|
| 这是家庭意图的 **Brain 控制面**：理解、规划、选边、入队、组装 presentation。不是 Edge，不是发出窗 | [positioning.md](docs/project_map/positioning.md) |
| 唯一进程 `server/home_brain.py`（Flask），监听 **`:9527`**；根 `home_brain.py` 只是 shim | [architecture.md](docs/project_map/architecture.md) |
| 规划器广告来自集市 export；心跳只表示「谁在线」+ 实例覆盖。不要在本仓维护第二份能力目录 | 同上 |
| `kind=system` 步在 Brain 就地执行；设备 I/O 在 Gateway / 手机 | 同上 |
| 部署走平台 `:4220`（`build.sh` + `scripts/{start,stop,restart}.sh`）。合入 `main` ≠ 已上线 | [deployment.md](docs/project_map/deployment.md)、[release.md](docs/project_map/release.md) |
| OCR 是 HTTP sidecar，默认 `OCR_SERVICE_URL=http://127.0.0.1:9188`（[kaulie/ocr-service](https://github.com/kaulie/ocr-service)） | [architecture.md](docs/project_map/architecture.md) |
| 栈是 Flask + SQLite + 方舟；无 Docker 一等路径 | [tech-stack.md](docs/project_map/tech-stack.md) |

Runtime / planner 初始化会要求：**优先读目标仓库根目录的 `AGENT.md`**。你正在读的就是那份文件。

**禁止**只凭拆分说明里的「纯搬迁」理解现状：集市广告、OCR 独立仓已经进本仓。与代码不符时以 `docs/project_map` + 代码为准，并履行第 3、4 节。

## 2. 开工前清单

1. 确认你在简报给出的 **workspace** 里，origin 是 `https://github.com/kaulie/home-agent-brain`。
2. 从最新 `main` 开 `feat|fix|chore/<简述>`。
3. 读 `docs/project_map/` 里与本次改动相关的维度，再打开将改的 `server/*.py`、prompt、`server/sql/`。
4. 对照代码核对地图：路由在 `server/home_brain.py` 的 `@app.route`；规划广告在 `server/marketplace_catalog.py`。
5. 本地验证：`cd server && python3 -m unittest discover -s tests -t .`（部分用例依赖本机库表，失败先看是否本仓引入）。
6. 不要占用线上 **9527** 做开发，除非你清楚该实例已停。
7. 不要在本进程里执行部署 / 重启 runtime 的脚本。不要改 `/Users/gaolei/runtime/**`。不要改已归档的 home-agent-os。

## 3. 滞后信息：有义务更新

发现下列任一情况，**这次任务里就要改文档**，不要留给下一个人：

- `docs/project_map/` 写的路径、端口、env、启停脚本与当前代码不一致。
- README 仍写「能力广告在本仓硬编码」或「OCR 源码在 os / 本仓 sibling」。
- 默认值变了（`HOME_AGENT_MARKETPLACE_URL`、`OCR_SERVICE_URL`、`BRAIN_DATA_DIR`）。

更新规则：运行事实 → 改 `docs/project_map/` 对应维度，并在 [`docs/project_map/README.md`](docs/project_map/README.md) 的「已核对异议」里写清；需要人读的协议 → 改 README / `.env.example`。行为是你这次改出来的 → 同一 PR 改文档。只改代码、让地图变假，算没做完。过期异议删掉或改写。

## 4. 与事实不符：必须提出异议，禁止默认处理

| 你看到的 | 你不该做的 | 你该做的 |
|---|---|---|
| 任务要求改 `plugins/` 里的能力声明 | 在本仓新建 plugins | 异议：声明在 marketplace |
| 任务要求「在本仓库里部署上线」或 rsync runtime | 跑 `restart.sh` / 改 `/Users/gaolei/runtime/**` | 异议：发版入口在 `:4220` |
| 任务要求直推 `main` 或改 os | 照做 | 异议：走 PR；os 已归档 |
| 地图说某文件在 A，仓库里只有 B | 在 A 新建一份「对齐」 | 异议 + 改 `docs/project_map/` |

异议写在 PR 正文或任务回复里：

```
异议：<文档路径> 声称 <原句>
事实：<文件:符号 或 命令输出>
处理：<已改文档 / 已改代码 / 需要人决定>
```

## 5. 改动落点

| 要改的东西 | 去哪 |
|---|---|
| HTTP 路由 / intent / presentation | `server/home_brain.py` |
| 规划输出解析 / 执行计划规范化 | `server/planner_output.py`、`server/plan_normalization.py` |
| 展示策略 / Asset 值处理 / 实例匹配 | `server/presentation_policy.py`、`server/asset_values.py`、`server/provider_selection.py` |
| 规划器广告 / 组合分解 | `server/capability_ads.py`、`server/marketplace_catalog.py` |
| 系统能力（clock 等） | `server/system_capabilities.py` |
| 心跳 / 在线服务表 | `server/edge_services.py` |
| 规划 prompt / shortcut | `server/prompts/`、`server/shortcut_mode/` |
| schema | `server/sql/`、`server/db.py` |
| OCR 客户端 | `server/sdk/image_ocr.py` |
| 启停 | `scripts/{start,stop,restart}.sh` |
| 发版包装 | `build.sh` |
| 给后续 agent 的地图 | [`docs/project_map/`](docs/project_map/README.md) + 本文 |

契约与路由必须一起改。Vision/LLM 原始 JSON 即为契约，禁止拆包兜底。

## 6. 交付

- 提交信息说清为什么。
- `git push -u origin HEAD`，`gh pr create`（或网关开 PR），回写 `prUrl`。
- 已有 `prUrl` 不再开第二个 PR。
- 合入 / `:4220` 发版只听从任务 `goal` 与人的明确指令。本仓库合入 `main` ≠ 已上线。

## 7. 安全

不要打印或提交 `ARK_API_KEY`、`BRAIN_ADMIN_TOKEN`、`server/.env`。库在 `BRAIN_DATA_DIR`（生产常在 `/Users/gaolei/database/home-agent-brain`），不要把库文件打进 git 或发版包。
