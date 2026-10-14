# 开发流程

## 工作区

只在 task 简报给出的 workspace 里开发。origin 只能是 `https://github.com/kaulie/home-agent-brain`。

- **永远不要**改 `/Users/gaolei/runtime/**`。
- 不要改已归档的 home-agent-os。
- 不要改 marketplace / gateway，除非任务点名（声明在集市，设备 I/O 在 gateway）。

## 分支

从最新 `origin/main` 开短命分支，PR 回 `main`。简报有 task id 则写进分支名。禁止直推 `main`、禁止 force push `main`。

任务已有 `prUrl` 时不要再开第二个 PR。合入 / 部署只听从 `goal` 与人的明确指令。

## 改代码时的边界

1. 先读 [`../../AGENT.md`](../../AGENT.md) 与本目录。
2. 规划规则改 `server/prompts/` 或 `shortcut_mode/`，不要把长文写进 `home_brain.py`。
3. 能力触发语 / schema 改集市，本仓只消费 export。
4. schema 变更走 `server/sql/`，点名 `@dba` 的规矩仍成立。
5. 不要在本仓库加「发起部署」的接口。

## 测试

```bash
cd server && python3 -m unittest discover -s tests -t .
```

部分用例依赖本机库表或可选依赖；失败先分清是否本次引入。改路由 / 广告 / presentation 后至少跑相关测试。

核心拆分的模块边界回归可单独运行：
`cd server && python3 -m unittest tests.test_core_modules -v`。
它验证独立导入无启动副作用、实时 provider 回调、规划/shortcut 差异、
JSON 解析、展示策略、资源视图和实例匹配。涉及运行状态的集成行为仍由
`tests/test_home_brain.py` 等原有测试覆盖；拆分时应与同环境 main 基线比较。

## 提交与敏感物

不要提交 `server/.env`、`ARK_API_KEY`、`BRAIN_ADMIN_TOKEN`、sqlite 库、`uploads/`。
