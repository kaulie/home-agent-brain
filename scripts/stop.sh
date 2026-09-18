#!/usr/bin/env bash
#
# 停止 home-agent-brain（TERM → 最多 15s → KILL）。
#
# pid 来源优先级：
#   1. server/logs/runtime.pid（scripts/start.sh 写的）
#   2. 兜底：监听 BRAIN_PORT 且命令行含 home_brain.py 的进程
#      —— 老仓库 server/deploy/deploy_lan_brain.sh 起的那套没有 pid 文件，
#         迁移/收尾时要靠这条兜底停掉（只认命令行匹配，不误伤别的进程）。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# runtime 目录以脚本自身位置为准（同 start.sh：不认继承来的 RUNTIME_DIR）。
SELF_RUNTIME_DIR="$(cd "${DIR}/.." && pwd)"
BRAIN_PORT="${BRAIN_PORT:-9527}"

log() { echo "[stop] $*"; }

if [ -n "${RUNTIME_DIR:-}" ] && [ "${RUNTIME_DIR}" != "${SELF_RUNTIME_DIR}" ]; then
  log "忽略继承来的 RUNTIME_DIR=${RUNTIME_DIR}，按脚本位置用 ${SELF_RUNTIME_DIR}"
fi
RUNTIME_DIR="${SELF_RUNTIME_DIR}"
PID_FILE="${RUNTIME_DIR}/server/logs/runtime.pid"

PIDS=()
if [ -f "${PID_FILE}" ]; then
  pid="$(tr -d '[:space:]' < "${PID_FILE}" || true)"
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    PIDS+=("${pid}")
  else
    log "pid 文件里的 ${pid:-?} 已不存在，清理"
    rm -f "${PID_FILE}"
  fi
fi

if [ "${#PIDS[@]}" -eq 0 ] && command -v lsof >/dev/null 2>&1; then
  for cand in $(lsof -nP -iTCP:"${BRAIN_PORT}" -sTCP:LISTEN -t 2>/dev/null || true); do
    cmd="$(ps -o command= -p "${cand}" 2>/dev/null || true)"
    case "${cmd}" in
      *home_brain.py*)
        log "兜底：端口 ${BRAIN_PORT} 上的 pid=${cand} 是 Brain（${cmd}）"
        PIDS+=("${cand}")
        ;;
    esac
  done
fi

if [ "${#PIDS[@]}" -eq 0 ]; then
  log "没有运行中的 Brain"
  rm -f "${PID_FILE}"
  exit 0
fi

for pid in "${PIDS[@]}"; do
  log "TERM → pid=${pid}"
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 30); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  if kill -0 "${pid}" 2>/dev/null; then
    log "15s 内未退出，KILL → pid=${pid}"
    kill -9 "${pid}" 2>/dev/null || true
  fi
done

rm -f "${PID_FILE}"
log "已停止"
