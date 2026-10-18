# Brain 核心拆分分析（2026-10-18）

> 范围：`home_brain.py` → `server/home_brain.py` 单进程，及其同级的规划
> （`prompts/`、`shortcut_mode/`、方舟调用）、`marketplace_catalog.py`、
> `capability_ads.py`、HTTP 路由层（`@app.route`）、`db.py` + `sql/`。
> 基线：`main@78746c2`。本文给出**还能拆什么、按什么顺序拆**；
> 不改进程边界（仍是唯一 Brain 进程，见 [architecture.md](architecture.md)）。

## 1. 体量与现状

| 指标 | os 旧方案（2026-08） | 当前 |
|---|---|---|
| `server/home_brain.py` 行数 | ~8,035 | 7,232（本 PR 后；`main` 为 7,306） |
| 顶层 `def`/`class` | ~302 | 246（`main` 为 251） |
| `@app.route` 装饰器 | 66 | 74（其中 `/api/v1/admin/*` 35） |
| `tests/test_home_brain.py` | ~5,035 | 6,241 |
| 同级已拆模块 | `dev_task`、`debug_gateway` 等 | 另加 19 个值/策略模块（见 architecture.md「核心内部模块」） |
| `db.py` | ~2,473 | 2,769 |

入口文件头部 ~600 行是 import 与兼容导出（`server.*` / 直接导入两套），
其余按职责分段（行号为本 PR 后）：

| 行段 | 职责 | 约行数 | 主要共享状态 |
|---|---|---|---|
| 1–631 | import、兼容导出、薄适配（`sanitize_execution_plan` 等） | 630 | — |
| 632–694 | Flask `app`、`task_queue`/`qwen_task_queue`、`llm_running_lock`、`commands_queue`、日志 | 60 | 全部在此定义 |
| 695–1453 | Participant / Endpoint / 策略（`can_participate`、`_load_control_policy_index`）、speak 附加 | 760 | `brain_db` 心跳/注册 |
| 1454–1655 | `assemble_presentation` | 200 | intent dict |
| 1656–2268 | 规划：prompt 组装、`call_ark`、`call_qwen`、shadow review、`extract_llm_plan` | 610 | `mock_cache`、`llm_running_lock` |
| 2269–2541 | 选边：`online_capability_providers`、`_assign_runtime_edge_id`、`do_execution_plan` | 270 | `capability_edge_mapping`、`commands_queue` |
| 2542–2910 | 失败文案、intent 持久化（`_job_to_intent`、`_save_intent`、`update_intent_status`） | 370 | `brain_db` jobs |
| 2911–3095 | 后台 worker（`llm_worker`、`qwen_llm_worker`） | 185 | 两条队列 |
| 3096–3137 | DuerOS 兼容（`quick_speak`、`push_speech_to_dueros`） | 40 | — |
| 3138–3993 | 收单路由：`dispatch_intent`、shortcut/direct、voice wake、intent 查询 | 855 | 队列、`request` |
| 3994–4440 | Step 状态机：`_apply_step_status_record`、`try_run_system_steps`、`notify_*` | 445 | jobs、`commands_queue` |
| 4441–4727 | 上传 / URL 资产登记 | 285 | `_ASSET_UPLOAD_DIR` |
| 4728–6032 | 在线目录视图 + Admin API（policy、intents、dev task、release、agent chat、debug、docs） | 1,300 | `request`、`brain_db` |
| 6033–6628 | Edge 视图、Asset ACL / 读取 / 代理、Entity | 595 | `brain_db` assets |
| 6629–6773 | `command_handler`（Edge 拉单）、DuerOS skill、`chat` | 145 | `commands_queue` |
| 6774–7029 | 注册 / 心跳（`node_register`、`upsert_edge_heartbeat`） | 255 | `_EDGES`、`services_registered*` |
| 7030–7210 | `rebuild_capability_maps`、requeue、`_reconcile_orphan_jobs`、boot | 180 | `_CAP_MAPS_LOCK`、映射表 |
| 7211–末 | `__main__`：mDNS + `app.run(:9527)` | 20 | — |

## 2. 耦合与混杂点

1. **模块级可变状态是拆分的主阻力。** `commands_queue`（10 处引用）、
   `capability_edge_mapping`/`_EDGES`/`services_registered`（各 9 处）、
   `_REGISTERED_edges`（8 处）被心跳、选边、Edge 拉单、Admin 视图同时读写；
   测试直接给 `hb._REGISTERED_edges` 赋值（`tests/test_home_brain.py` setUp）。
   任何把它们搬出入口的切片都必须保留 `home_brain.<name>` 的**同一对象**。
2. **`request` 渗透：** 125 处 `request.` 引用，路由与业务没有分层；
   Admin 段的 `_admin_auth_error` 被 35 条 Admin 路由复用。
3. **规划与执行在 worker 里交织：** `_process_llm_task` 一次完成调方舟 →
   解析 → `do_execution_plan`（选边 + 入队）→ 状态更新；`mock_cache` 与
   `llm_running_lock` 只在这里用，但 key 依赖 `_capability_registry_fingerprint`。
4. **Step FSM 已有终态守卫，但没有统一入口：** `_apply_step_status_record`
   拒绝终态回退（`intent is terminal; step cannot return to running`），
   `update_intent_status` 仍被多处直接调用。
5. **Asset 子系统与 intent 生命周期交叉：** ACL 依赖 `_intent_job_presents_asset`
   与 plan 输入（`_grant_plan_input_assets`），因此不能只按 URL 前缀切。
6. **死代码：** `bp = Blueprint("gopro_photos", __name__)`（`home_brain.py:3137`）
   从未注册也未挂路由；同名 Blueprint 实际在 `photo_upload_flask.py`。
7. **入口只支持 server 目录直导：** `import server.home_brain` 在 `main` 上就失败
   （`intent_complexity/matcher.py` 直接 `import capability_ads`）。双导入布局
   只对同级 helper 模块成立（`tests/test_core_modules.py` 覆盖），见第 6 节异议。

## 3. 对照 os 旧方案（只读核对）

来源：[`kaulie/home-agent-os`](https://github.com/kaulie/home-agent-os)（已归档，`6084fe0`）
`docs/architecture/brain-simplification-plan.md`（简称 SP）与
`docs/architecture/brain-complexity-refactor.md`（简称 CR）。
状态：**已完成** / **部分完成** / **仍适用** / **已过时**。

| 旧条目 | 状态 | 当前代码事实 |
|---|---|---|
| 目标目录 `server/brain/{intent,planner,routing,...}/`（SP §3.1、CR §4） | 已过时 | 仓库不存在 `server/brain/`；实际走法是**扁平同级模块** + 入口兼容导出（`planner_output.py`、`plan_normalization.py` 等），architecture.md 已把它定为约定 |
| P0.1/D0.1 Intent FSM `apply_intent_transition()`（CR §6.1、SP §4） | 仍适用 | 无此符号；终态守卫散在 `home_brain.py:_apply_step_status_record` 与 `intent_status_values.py:TERMINAL_STATUSES`，`update_intent_status` 仍被直接调用 |
| D0.3 `test_plan_build.py` / `test_edge_select.py` | 部分完成 | 文件名不同：`tests/test_core_modules.py` 覆盖 `plan_normalization`、`provider_selection`；`online_capability_providers` / `_assign_runtime_edge_id` 仍只在 `test_home_brain.py` 集成测 |
| D0.4 `scripts/brain_complexity_report.py` | 仍适用（可选） | `scripts/` 只有 `start/stop/restart.sh` |
| P1 step 回调迁出（`notify_step_status_update` 等） | 仍适用 | 仍在 `home_brain.py:notify_step_status_update` / `notify_intent_status_update` / `notify_delivery_complete`；值判定已迁 `execution_step_values.py` |
| D1.3 system 步前序门 / 参数解析迁出（SP §2.5） | 已完成 | `execution_step_values.py:_system_predecessors_succeeded`、`_resolve_system_params`；调度壳 `try_run_system_steps` 仍在入口 |
| P2.1 Planner：`call_ark` / cache / `extract_llm_*` | 部分完成 | HTTP 客户端 `volcano_ark_client.py`、传输边界 `llm_provider.py:get_planner_transport`、解析 `planner_output.py`、缓存 `planner_query_cache.py` 已拆；`call_ark`、`call_qwen`、`_planner_prompt_pair`、worker 仍在入口 |
| sanitize / composite fold / `make_execution_plan` | 已完成 | `plan_normalization.py`（入口保留 `sanitize_execution_plan` 等薄适配，传入实时 provider 回调） |
| P2.2 Routing：选边 + `rebuild_capability_maps` | 仍适用 | 全部仍在入口，依赖 `capability_edge_mapping` 等模块级状态；名称匹配已拆到 `provider_selection.py` |
| D2.3 Presentation：assemble / endpoint / speak | 部分完成 | 策略在 `presentation_policy.py`、`plan_presentation_kind.py`、`plan_speak_steps.py`、`endpoint_participant_values.py`；`assemble_presentation` 与 endpoint 匹配仍在入口 |
| D2.4 Asset：上传 / ACL / views | 部分完成 | 值视图 `asset_values.py`、字节写入 `img_server_client.py` 已拆；ACL（`_asset_client_may_read`、`_grant_*`）与路由仍在入口 |
| D2.5 Admin 路由 Blueprint | 仍适用 | 35 条 `/api/v1/admin/*` 仍注册在 `app`；业务已在 `dev_task*`、`agent_chat` 等；本 PR 迁出其纯展示 helper（`admin_values.py`） |
| D2.6 Participant 注册 / 心跳 / policy | 仍适用 | `node_register`、`upsert_edge_heartbeat`、`can_participate` 在入口；wire 解析在 `edge_services.py` |
| `test_home_brain.py` ≤1,500/2,000 行 | 仍适用（变差） | 现 6,241 行 |
| `home_brain.py` ≤4,500（P2）/ ≤2,500（终态） | 仍适用 | 现 7,232 |
| Admin HTML 走 os `admin/serve.py:8788` | 已过时（对本仓） | 本仓无 `admin/`；os 已归档，architecture.md 只写「本机 HTML 代理不在本仓」 |
| 云 Brain rsync `home_brain.py`+`prompts/`、`systemctl restart doubao_skill`（SP §2.3） | 已过时 | 发版只走 `:4220` 平台：`build.sh` + `scripts/restart.sh`（[deployment.md](deployment.md)） |
| `brain_app.py` 仅转调 | 仍成立 | `brain_app.py` 32 行，从 `home_brain` 再导出 `app`，自带 mDNS 启动 |
| Orphan 300s vs runtime 120s 不对齐 | 仍适用（跨仓） | `home_brain.py:_ORPHAN_GRACE_SEC = 5 * 60`；需与 `@runtime` 对齐，非 Brain 内部拆分 |
| 非目标：不拆多进程、不改 schema、prompt 只改 md | 仍成立 | 与 [development.md](development.md) 一致 |

## 4. 拆分候选（按风险从低到高，即建议顺序）

| # | 候选 | 范围 | 依赖 | 风险 | 说明 |
|---|---|---|---|---|---|
| 1 | Admin 展示值 → `admin_values.py` | `_ADMIN_ROLE_LABELS`、`_admin_node_title`、`_admin_target_title`、`_admin_policy_summary`、`_policy_items_from_body`、`_step_status_text`（~75 行） | 无：只读参数 | 极低 | **本 PR 已做** |
| 2 | 删死 Blueprint | `home_brain.py:3137` `bp = Blueprint("gopro_photos")` | 无引用 | 极低 | 与 `photo_upload_flask.bp` 同名易误导；单独 PR |
| 3 | 日志初始化 → `brain_logging.py` | `init_brain_logger`、`_attach_file_logger` | `brain_env.LOG_DIR` | 低 | 导入期副作用（`log = init_brain_logger()`）要留在入口调用 |
| 4 | DuerOS / 豆包兼容 → `dueros_compat.py` | `quick_speak`、`push_speech_to_dueros`；路由 `/dueros_skill`、`/doubao_chat` 留入口 | `brain_env.DUEROS_*`、`urllib` | 低 | 先确认这两条 legacy 路由线上是否还有流量；无流量则改为删除议题 |
| 5 | Admin 路由 → Blueprint | 35 条 `/api/v1/admin/*` + `_admin_auth_error`、`_admin_node_view`、intent/dev task 视图 | `brain_db`、`can_participate`、`_edge_public_view`、`get_intent`、`_job_to_intent` | 中 | 业务已外置；用 `register_blueprint` 但保持 URL；Blueprint 反向依赖入口 helper，需先把 #7 中的读取函数移出或以参数注入，避免导入环 |
| 6 | 规划调用 → `planner_calls.py` | `call_ark`、`call_qwen`、`_planner_prompt_pair`、`_planner_user_message`、shadow review | `mock_cache`、`llm_running_lock`、`get_planner_transport`、catalog 指纹、`brain_db` 记录 | 中 | 测试 patch `hb.call_ark` / 传输层；必须保证入口内部调用仍经过可 patch 的名字（参考 `llm_provider.set_planner_transport`） |
| 7 | Intent 持久化 → `intent_store.py` | `_job_to_intent`、`_save_intent`、`get_intent`、`update_intent_status`、`list_intents` | `brain_db` jobs、`_normalize_status` | 中 | 是 #5、#8、#9 的前置；单测可用临时 sqlite |
| 8 | Intent FSM 显式化（os P0.1） | `apply_intent_transition()` + 转移表，替换直接 `update_intent_status` | #7 | 中高 | 是行为收口而非搬迁；以 intent 333 orphan 为金样例 |
| 9 | Step 回调 + system 调度壳 | `_apply_step_status_record`、`_maybe_finalize_intent_after_step`、`try_run_system_steps`、`notify_*` | #7、#8、`commands_queue`、`system_capabilities` | 高 | incident 密度最高；在 #8 之后 |
| 10 | Asset ACL / 读取 | `_asset_client_may_read`、`_grant_*`、`_serve_asset_bytes`、`_proxy_asset_upstream`、assets/entities 路由 | `brain_db` assets、intent plan、`request` | 高 | ACL 依赖 intent；先迁 views 再迁 upload |
| 11 | 选边 + 能力映射 + 心跳状态 | `online_capability_providers`、`_assign_runtime_edge_id`、`rebuild_capability_maps`、`_EDGES`、`services_registered*` | 模块级可变状态，测试直接赋值 `hb._REGISTERED_edges` | 高 | 必须把状态收进一个对象并在入口保留同名引用；最后做 |

不建议拆：`db.py` + `sql/`（schema 归 `@dba`，只做 `intent_store` 薄封装）、
`marketplace_catalog.py` / `capability_ads.py`（已独立且职责单一，本次核对未见混杂）、
`prompts/` / `shortcut_mode/`（规则只改 md，已在入口外）。

## 5. 本 PR 实施的拆分（候选 #1）

- 新增 `server/admin_values.py`：六个符号原样搬出（只去掉前导下划线），不读
  `request` / 库 / 运行状态，也不导入入口。
- `server/home_brain.py` 在两套导入布局里都以原名（`_admin_policy_summary` 等）
  重新导出，路由调用点不变。
- 测试：`tests/test_admin_values.py` 以 `main` 上采得的输出做金样例，并断言
  `home_brain` 旧名与新模块是同一对象；`tests/test_core_modules.py` 把
  `admin_values` 纳入「独立导入无副作用」检查。

## 6. 本轮核对的文档异议

1. architecture.md 称「两种导入布局（`server.*` 与 server 目录下直接导入）均受支持」。
   事实：`import server.home_brain` 在 `main` 上报 `ModuleNotFoundError: capability_ads`
   （`intent_complexity/matcher.py` 直接导入）。处理：改文档，限定为同级 helper 模块。
2. deployment.md 称 `BRAIN_DATA_DIR`「默认 `~/database/home-agent-brain`」。
   事实：`data_paths.py:data_dir` 未设置时回落 `server/data`；`scripts/start.sh`
   首次部署写入 `BRAIN_DATA_DIR=<runtime>/backend/data`。处理：改文档；
   `build.sh` 注释同样过时，未在本 PR 修改（发版脚本，交人决定）。
