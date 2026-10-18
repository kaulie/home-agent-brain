# project_map — home-agent-brain 项目地图

本目录按**运行事实**说明本仓库，不是概念词典。

| 文档 | 维度 |
|---|---|
| [positioning.md](positioning.md) | 项目定位：解决什么、不解决什么、和周边怎么分工 |
| [architecture.md](architecture.md) | 服务架构：进程、规划、心跳、存储、HTTP |
| [tech-stack.md](tech-stack.md) | 技术栈 |
| [deployment.md](deployment.md) | 部署：谁部署、端口、运行目录、数据落点 |
| [release.md](release.md) | 发布：`build.sh` 产物、契约 |
| [development.md](development.md) | 开发：工作区、分支、测试、提交边界 |
| [brain-split-analysis.md](brain-split-analysis.md) | 核心拆分分析：职责盘点、os 旧方案核对、拆分候选排序 |

根目录 [`AGENT.md`](../../AGENT.md) 是后续 agent 的入口：理解以本目录为准，滞后必须更新，与事实不符必须提出异议。

协议原文仍在 [`server/README.md`](../../server/README.md)。`server/README.md` 回答「API 长什么样」；`docs/project_map/` 回答「这个仓库现在怎么跑、怎么改」。

## 怎么读

1. 先读 [positioning.md](positioning.md) 和 [architecture.md](architecture.md)，再按任务去对应维度。
2. 动手前对照代码：路由在 `server/home_brain.py` 的 `@app.route`；规划广告在 `server/marketplace_catalog.py`；schema 在 `server/sql/`。
3. 发现本目录或 README 与代码不一致时，按 [`AGENT.md`](../../AGENT.md) 处理，不要默认文档赢。

## 本轮已核对的异议（2026-10-12）

1. **能力声明不在本仓。** Brain 读集市 `GET /api/v1/export`（`marketplace_catalog.py`），心跳只表示在线。不要在本仓再维护一份 `plugins/` 目录。
2. **OCR 不在本仓源码树。** `image.ocr` 调 [kaulie/ocr-service](https://github.com/kaulie/ocr-service) `:9188`。
3. **[`kaulie/home-agent-os`](https://github.com/kaulie/home-agent-os) 已归档只读。** 不要往 os 回写 Brain。
4. **本检出无 `.github/workflows`。** 合入前至少本地跑单测，不要假设有 Actions。
5. **核心不再要求只改一个文件。** 原 `server/home_brain.py` 文件头的
   “Iterate on this file only” 已失效；内部值处理与策略拆入七个同级模块，
   入口仍拥有全部原有路由与启动流程，落点见 [architecture.md](architecture.md)。
6. **继续拆分（2026-10-14）。** 模型响应/错误处理与执行步骤值处理已迁入
   `model_response.py`、`execution_step_values.py`；入口保留原 helper 导出，
   不改变 Flask 进程、路由、网络请求和持久化的归属。
7. **拆分分析（2026-10-18）。** 剩余可拆项与 os 旧方案核对见
   [brain-split-analysis.md](brain-split-analysis.md)；Admin 展示 helper 已迁入
   `admin_values.py`。`server.home_brain` 包式导入在 `main` 上本就失败
   （`intent_complexity` 直接导入 `capability_ads`），双导入布局只对同级 helper 成立。
8. **`BRAIN_DATA_DIR` 默认值（2026-10-18）。** 未设置时为 `server/data`；
   平台部署由 `start.sh` 写成 `<runtime>/backend/data`。`build.sh` 注释里的
   `~/database/home-agent-brain` 仍过时，待人决定是否修改。

后续 agent 若发现上述条目被新代码推翻，删除或改写，不要累积过期异议。
