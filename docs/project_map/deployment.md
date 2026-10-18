# 部署细节

## 谁负责部署

部署**只**由部署平台完成：[`agent-control-plane-deployment`](https://github.com/kaulie/agent-control-plane-deployment)，本机 `:4220`。

平台从 GitHub ref 调本仓 `build.sh`，得到 `outputs/`，rsync 到 runtime，执行 `scripts/restart.sh`。

- **禁止**在 agent 进程里同步跑 deploy / restart（会杀掉正在跑命令的 gateway）。
- **禁止**手改 `/Users/gaolei/runtime/**`。
- 本服务暂无 `restartNotifyUrl` / `restartPollUrl`（直接 rsync + restart）。

```bash
curl -sS -X POST http://127.0.0.1:4220/api/deploy-notify \
  -H 'content-type: application/json' \
  -d '{"serviceId":"home-agent-brain","ref":"main"}'
```

云 Brain（如 `49.234.45.173`）若打不到本机 `:4250`，不要假定它已吃到最新集市广告。

## 端口与探活

唯一监听：**`0.0.0.0:9527`**。平台契约 `port` / `healthUrl` 必须是 9527。`start.sh` 被注入别的 `SERVICE_PORT` 时**只告警、不改监听口**（交互式 shell 残留 `PORT` 是已知坑）。

探活：`GET http://127.0.0.1:9527/health`。

**本机开发不要占用 9527**，除非确认线上实例已停。

## 运行目录

```
<runtime>/                          平台 runtimeDir（本仓 clone）
  scripts/{start,stop,restart}.sh
  home_brain.py
  server/                           源码
  backend/.env                      平台 rsync --delete 时保留
  backend/data/                     平台保留：默认库目录 + .venv
  backend/runtime.pid
  backend/server.log
```

库不在代码树：`BRAIN_DATA_DIR`。代码默认（未设置）是 `server/data`（`server/data_paths.py:data_dir`），
会被下次 rsync 清掉；所以 `start.sh` 在 `backend/.env` 缺这一项时写入
`BRAIN_DATA_DIR=<runtime>/backend/data`（平台保留 `backend/data/`，venv 也在 `backend/data/.venv`）。
本机生产常显式设为 `/Users/gaolei/database/home-agent-brain`。

`start.sh` 以**脚本自身位置**定 runtime，忽略继承来的 `RUNTIME_DIR`（曾残留过 web-cursor）。
