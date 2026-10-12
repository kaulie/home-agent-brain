# 项目定位

## 一句话

home-agent-brain 是家庭 Agent 的 **Brain 控制面**：把自然语言变成 `execution_plan`，选边、入队、组装 presentation。它不是 Edge，不是发出窗，也不是能力声明权威。

仓库：[`https://github.com/kaulie/home-agent-brain`](https://github.com/kaulie/home-agent-brain)  
契约端口：`9527`  
平台 serviceId：`home-agent-brain`（`build.sh` 注释）

## 它要解决什么

```
人/手机/语音 → POST /api/v1/intent → 规划器 → execution_plan（每步 assigned_edge_id）
        → Edge 心跳在线表选边 → 拉单执行 → assemble_presentation
```

- **规划在 Brain**：prompt 在 `server/prompts/`，shortcut 在 `server/shortcut_mode/`。
- **声明在集市**：触发语 / schema / decomposes_to 以 marketplace export 为准。
- **执行在 Edge / 手机 / sidecar**：本进程只跑 `kind=system` 步（如 `clock.now`）。
- **世界状态是 job / presentation / asset_ref**：不要把临时 URL 当 identity。

## 它不是什么

| 不是 | 谁才是 |
|---|---|
| Mac 设备 I/O / 投屏 / 小度 | [`home-agent-gateway`](https://github.com/kaulie/home-agent-gateway) |
| 能力声明目录 | [`home-agent-capabilty-marketplace`](https://github.com/kaulie/home-agent-capabilty-marketplace) `:4250` |
| 图片 OCR 引擎 | [`ocr-service`](https://github.com/kaulie/ocr-service) `:9188` |
| 发出窗 | [`home-agent-ios`](https://github.com/kaulie/home-agent-ios) / [`home-agent-android`](https://github.com/kaulie/home-agent-android) |
| 部署平台 | [`agent-control-plane-deployment`](https://github.com/kaulie/agent-control-plane-deployment) `:4220` |
| 已冻结的单体 os | [`home-agent-os`](https://github.com/kaulie/home-agent-os)（归档只读） |

本仓库**没有**「对本机 runtime 发起部署」的 HTTP 入口。上线走 `:4220`。

## 当前形态

已落地、且后续开发必须当现状：

- 唯一进程 `server/home_brain.py`（Flask），根 `home_brain.py` 是 shim
- 双实例：LAN `BRAIN_ORIGIN=lan` 与云 `cloud`（同代码，不同 origin）
- 集市广告 + 心跳在线覆盖
- Asset 上传 / 授权 / `GET /api/v1/assets/{id}/content`
- Admin / Dev Task / Fleet 代理（Fleet 实际在本机 agent-bridge，仍留在 os）
- 发版包装 `build.sh` + `scripts/{start,stop,restart}.sh`
