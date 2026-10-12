# 服务架构

## 进程边界

```
iPhone / Android / Mac Edge / 其它 Intent Source
        │  HTTP :9527
        ▼
  home_brain.py → server/home_brain.py     ← 唯一 Brain 进程
        │
        ├─ 规划      prompts/ + shortcut_mode/ + 方舟 ARK
        ├─ 广告      marketplace_catalog.py → GET 集市 /api/v1/export
        ├─ 在线表    edge_services.py（心跳 last-writer-wins）
        ├─ 系统步    system_capabilities.py（kind=system）
        ├─ OCR 客户端 sdk/image_ocr.py → http://127.0.0.1:9188
        ├─ Store     db.py + sql/ 迁移；库在 BRAIN_DATA_DIR
        └─ HTTP      Flask @app.route（见 server/README.md）
```

不要再起第二个 Brain 进程「分担路由」。LAN 与 Cloud 是两个部署实例。

## 规划与广告

1. `marketplace_catalog.py` 拉 `HOME_AGENT_MARKETPLACE_URL`（默认 `http://127.0.0.1:4250`）的 `/api/v1/export`，磁盘缓存、TTL 约 60s。
2. `capability_ads.py` 的 `attach` / `composition_of` / `decomposes_to` 以这份广告为准；缺 id 则 stub，避免 KeyError。
3. 心跳 overlay：在线 Edge 覆盖实例字段；空字段用声明补齐。`kind=system` 的 catalog 行在本仓强制 `kind=system`。
4. **`decomposes_to` 是执行顺序**，不要按字母重排（那是集市 exporter 的责任）。

Planner 规则写在 markdown prompt，不要把长规则写回 `home_brain.py`。

## HTTP 面（摘录，完整表以 `server/README.md` 与 `@app.route` 为准）

| 路径 | 作用 |
|---|---|
| `GET /health` | 探活 |
| `GET /api/v1/ping` | 连通 + 时钟 |
| `POST /api/v1/intent` | 收单；立刻 `intent_received`，后台规划 |
| `GET /api/v1/intent_detail` | 发出端轮询 |
| `GET /api/v1/devices/.../intents` | Edge 拉已规划单 |
| `POST /api/v1/intent/<id>/step/<step>/status` | 步状态 |
| `POST /api/v1/edge-register` / 心跳 | 登记与在线 |
| `GET /api/v1/capabilities` | **在线**能力表（不是集市目录） |
| `POST /api/v1/assets/upload` 等 | Asset |
| `/api/v1/admin/*` | 管理；本机 HTML 代理不在本仓（os `admin/`，另起炉灶） |

Vision / LLM 原始 JSON 即为契约，禁止拆包兜底。

## 存储

- SQLite：`server/db.py`，迁移 `server/sql/`。
- 生产库目录 `BRAIN_DATA_DIR`（本机常 `/Users/gaolei/database/home-agent-brain`），**不在** runtime 代码树。
- 上传字节 `server/uploads/`（gitignore）。日志 `server/llm_logs/` 或 `BRAIN_LOG_DIR`。

## 外部依赖

| 依赖 | 默认 |
|---|---|
| 集市 | `http://127.0.0.1:4250` |
| OCR | `http://127.0.0.1:9188` |
| 方舟 | `ARK_API_KEY` |
| 部署平台 | `:4220`（本进程不调自己 restart） |
