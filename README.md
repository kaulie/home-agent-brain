# home-agent-brain

Home Agent OS 的 **Brain 控制面**独立仓库。

代码自 [`kaulie/home-agent-os`](https://github.com/kaulie/home-agent-os) 拆分而来（源 commit
`5f5c0c6048f34f357ce1abddae2df0b74b45d051`），是一次**纯搬迁**：上游的 `server/` 与根入口
`home_brain.py` 原样复制到本仓库，未修改任何逻辑。上游 `home-agent-os` 在拆分时保持不动。

## 同步记录

拆分之后上游 Brain 侧的改动按下表搬入本仓库（`server/` + 根 `home_brain.py` 与上游逐字节一致）：

| 日期 | 上游范围 | 内容 |
|------|----------|------|
| 2026-09-18 | `5f5c0c6..37d9537` | `pdf.reader` / `paper.read` 能力广告与 schema；网易云登录失效的人类可读失败文案（仅 iPhone 发起端带登录链接）；`display.audio`（已有音频交给小米电视 DLNA 出声）及其 shortcut 规则、presentation、asset 盘点量词 |

同步口径：只搬 `server/**` 与根 `home_brain.py`（本仓库既有边界），不带上游的
`mac/`、`ios/`、`plugins/`、`docs/`、`agent_plans/` 等 Edge / 文档资产。

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
# 一次性：.env（含 ARK_API_KEY，不入 git）+ 依赖
cp server/.env.example server/.env   # 填 ARK_API_KEY
python3 -m venv server/.venv && server/.venv/bin/pip install -r server/requirements.txt

# 启动（runtime 目录里就是这套脚本，部署平台也按它调）
bash scripts/start.sh      # 或 bash scripts/restart.sh / bash scripts/stop.sh
# 等价的手工方式：cd server && BRAIN_ORIGIN=lan python home_brain.py
```

Python 3.10+，唯一三方依赖是 **Flask**（`server/requirements.txt`，`start.sh` 会自动装）。
协议、路由、能力契约详见 [`server/README.md`](server/README.md)。

### runtime 布局与端口（部署平台契约）

```
<runtime>/                     部署平台 runtimeDir（本仓 clone，只放代码）
├── scripts/{start,stop,restart}.sh   平台调用的启停脚本
└── server/
    ├── .venv/  .env  logs/          运行期（.gitignore，平台部署时保留）
    ├── uploads/                     本机上传的 Asset 原始字节（.gitignore）
    └── data/                        仅当没设 BRAIN_DATA_DIR 时的历史默认库位置
```

| 项 | 值 |
|----|-----|
| 监听 | `0.0.0.0:9527`（唯一端口：Mac Edge / iPhone / 小度 与 mDNS `_ha-brain._tcp` 都按它连） |
| 健康 | `GET http://127.0.0.1:9527/health` —— 平台服务设置里的 `port`/`healthUrl` 必须是 **9527**，被注入别的端口时 `start.sh` 会响亮告警 |
| 数据 | `BRAIN_DATA_DIR`（本机生产：`/Users/gaolei/database/home-agent-brain`）= 库文件目录，见下 |
| 日志 | `server/llm_logs/`（`BRAIN_LOG_DIR` 可覆盖）；启停日志 `server/logs/brain.log` |

### 部署（agent-control-plane-deployment 规范）

本仓按部署系统要求提供三样东西：`build.sh`（打包）、`scripts/{start,stop,restart}.sh`（服务契约的启停命令）、
以及「运行期状态只放 `backend/`」的目录布局。

| 项 | 约定 |
|----|------|
| 打包 | 仓库根 `build.sh`，cwd=仓库根、`APP_VERSION=<8位短hash>`；产出 `outputs/`，其中**必须**含 `scripts/restart.sh`；`VERSION`/`COMMIT`/`GIT_REPO_URL` 由平台写进发版包，本脚本不写 |
| 发版包内容 | `outputs/{home_brain.py, README.md, .gitignore, scripts/*.sh, server/**}`（不含 `.venv`、`.env`、`data/`、`logs/`、`llm_logs/`、`uploads/`、`__pycache__`） |
| 部署动作 | 平台把包 rsync 到 runtimeDir：`rsync -a --delete --filter='P backend/{.env,data/,runtime.pid,server.log,.watchdog-paused}' --exclude='.git/'` |
| **能活过部署的东西** | `<runtime>/backend/{.env, data/, runtime.pid, server.log, .watchdog-paused}` 与 `<runtime>/.git/`；**其余一律按发版包覆盖** |
| 端口 | 平台按契约注入 `SERVICE_PORT`（本服务 = 9527）→ `scripts/start.sh` 用它对照 Brain 监听口，不一致时响亮告警 |
| 探活 | 部署后探 `healthUrl`；本服务 = `http://127.0.0.1:9527/health` |
| graceful | 本服务暂未提供 `restartNotifyUrl`/`restartPollUrl`（平台走「直接 rsync + restart」）；要做 in-flight intent 的优雅重启需在 Brain 里加这两个端点 |

因此运行期文件这样摆（部署不会被清掉）：

```
<runtime>/                          平台 runtimeDir
├── build.sh  scripts/              来自发版包
├── server/**                       Brain 源码（来自发版包）
├── .git/                          clone（rsync 排除，保留）
└── backend/                       ★ 平台唯一保留的运行期目录
    ├── .env                       密钥 + 部署配置（BRAIN_DATA_DIR / BRAIN_LOG_DIR / BRAIN_UPLOAD_DIR）
    ├── runtime.pid                start.sh 写
    └── server.log                 start.sh 写
```

库 / 日志 / 上传字节都放**代码之外**（`BRAIN_DATA_DIR` 及 `BRAIN_LOG_DIR`、`BRAIN_UPLOAD_DIR` 指向它），
所以 `--delete` 不会碰到家数据：

```ini
BRAIN_DATA_DIR=/Users/gaolei/database/home-agent-brain
BRAIN_LOG_DIR=/Users/gaolei/database/home-agent-brain/llm_logs
BRAIN_UPLOAD_DIR=/Users/gaolei/database/home-agent-brain/uploads/gopro
```


### 数据目录（代码之外）

`server/data_paths.py`：`BRAIN_DATA_DIR` > 单库 `*_PATH` 覆盖 > 历史默认 `<server>/data`。

| 文件 | 说明 |
|------|------|
| `brain.sqlite3` | 主库（jobs/participants/assets/registrations…），`db.py` |
| `dev_console.sqlite3` | Dev Console / Dev Task / issue 库，`dev_console_db.py` |
| `agent_tasks.json` / `debug_issues.json` | 旧 JSON 迁移源（已并入上面的库，保留兼容） |

本机生产指向 `/Users/gaolei/database/home-agent-brain`（`backend/.env` 的 `BRAIN_DATA_DIR`），
所以换代码 / 重新部署不动数据；老的 `~/Projects/smart_home_control/server/data` 只是历史位置 + 冷备。
`BRAIN_LOG_DIR`（Brain 运行日志）与 `BRAIN_UPLOAD_DIR`（Asset 原始字节）同理指向数据目录 ——
放在 runtime 目录里会被每次部署的 `--delete` 清掉。


## 边界

- 本仓库只承载 **Brain 控制面**。Edge 端的 Brain 客户端（`mac/`、`android/`、`ios/`）不在此仓库。
- `server/` 内的 sidecar（`main.py`、`photo_upload_*`、`vision_analyze_flask.py`、`audio_pickup.py`）
  与 Admin/dev 辅助模块随本次搬迁一并带入，保持目录结构与 import 不变。
