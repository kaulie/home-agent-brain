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
# 运行期 pid 放 <runtime>/backend/（平台部署只保留 backend/{.env,data/,runtime.pid,server.log}）。
PID_FILE="${RUNTIME_DIR}/backend/runtime.pid"
# 过渡期：老布局把 pid 写在 server/logs/ 下，两个都看。
LEGACY_PID_FILE="${RUNTIME_DIR}/server/logs/runtime.pid"

PIDS=()
for pf in "${PID_FILE}" "${LEGACY_PID_FILE}"; do
  [ -f "${pf}" ] || continue
  pid="$(tr -d '[:space:]' < "${pf}" || true)"
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    PIDS+=("${pid}")
  else
    log "pid 文件 ${pf} 里的 ${pid:-?} 已不存在，清理"
  fi
  rm -f "${pf}"
done

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

# mDNS 广告是 Brain 拉起的 dns-sd 子进程：父进程一死它就变孤儿继续广告（历次重启会累积，
# 实测攒了 9 个）。这里按 comm==dns-sd + 命令行含 _ha-brain._tcp 精确清理，不碰别的 dns-sd
# （例如 img-server 的 _ha-img-server._tcp）；随后的 start.sh 会重新广告一个。
cleanup_mdns_ads() {
  command -v ps >/dev/null 2>&1 || return 0
  local pids
  pids="$(ps -Ao pid=,comm=,command= | awk '$2 == "dns-sd" && /_ha-brain\._tcp/ {print $1}')"
  [ -n "${pids}" ] || return 0
  log "清理孤儿 mDNS 广告：$(echo ${pids} | tr '\n' ' ')"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
}

cleanup_mdns_ads
log "已停止"
