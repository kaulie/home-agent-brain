#!/usr/bin/env bash
#
# 启动 home-agent-brain —— 遵循 agent-control-plane-deployment 部署规范。
#
# 平台调用方式（见部署平台 services 行）：
#   cwd = runtimeDir（本仓 runtime 目录）、注入 PORT / RUNTIME_DIR / APP_VERSION
#   start / stop / restart = bash scripts/{start,stop,restart}.sh
#   契约：port=9527、health_url=http://127.0.0.1:9527/health
#
# 端口只有一个 9527（Brain 本体，Flask 0.0.0.0:9527）：
#   * 客厅 Mac Edge（mac/.env 的 MAC_EDGE_BRAIN_URL）、iPhone、小度都连它；
#   * mDNS 广告 _ha-brain._tcp 也是它（server/mdns_service.py）。
#   所以平台契约的 port/healthUrl 必须同为 9527；被注入别的端口时这里只告警不改监听口
#   （交互式 shell 里残留的 PORT 属于别的服务，是已知坑）。
#
# 数据：库文件 / 遗留 JSON 都在代码目录之外，由 .env 的 BRAIN_DATA_DIR 指定
# （默认 ~/database/home-agent-brain，见 server/data_paths.py）；.env 含密钥、
# 不入 git（权限 600），模板见 server/.env.example。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# runtime 目录以**脚本自身位置**为准：平台调用的就是 <runtime>/scripts/start.sh 绝对路径。
# 不要信交互式 shell 里继承来的 RUNTIME_DIR —— 那可能是别的服务（实测残留过 web-cursor），
# 照它走会去别的服务目录里找 server/。
SELF_RUNTIME_DIR="$(cd "${DIR}/.." && pwd)"
BRAIN_PORT="${BRAIN_PORT:-9527}"
CONTRACT_PORT="${SERVICE_PORT:-${PORT:-${BRAIN_PORT}}}"
APP_VERSION="${APP_VERSION:-dev}"

log() { echo "[start] $*"; }
warn() { echo "[start][警告] $*" >&2; }
die() { echo "[start][错误] $*" >&2; exit 1; }

if [ -n "${RUNTIME_DIR:-}" ] && [ "${RUNTIME_DIR}" != "${SELF_RUNTIME_DIR}" ]; then
  warn "忽略继承来的 RUNTIME_DIR=${RUNTIME_DIR}，按脚本位置用 ${SELF_RUNTIME_DIR}"
fi
RUNTIME_DIR="${SELF_RUNTIME_DIR}"

SERVER="${RUNTIME_DIR}/server"
VENV="${SERVER}/.venv"
PY="${VENV}/bin/python"
ENV_FILE="${SERVER}/.env"
REQ="${SERVER}/requirements.txt"
LOG_DIR="${SERVER}/logs"
PID_FILE="${LOG_DIR}/runtime.pid"
LOG_FILE="${LOG_DIR}/brain.log"

[ -d "${SERVER}" ] || die "缺少 ${SERVER}（runtime 布局应为 <runtime>/server）"
command -v python3 >/dev/null 2>&1 || die "本机没有 python3"
python3 -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
  || die "需要 Python 3.10+"

if [ "${CONTRACT_PORT}" != "${BRAIN_PORT}" ]; then
  warn "注入/约定的契约端口(${CONTRACT_PORT}) != Brain 监听口(${BRAIN_PORT})。"
  warn "/health 只在 ${BRAIN_PORT} 上：把部署平台里本服务的 port/healthUrl 改成 ${BRAIN_PORT}，"
  warn "或显式 BRAIN_PORT=… 启动（客户端与 mDNS 都按 ${BRAIN_PORT} 连，改监听口要同步改它们）。"
fi

[ -f "${ENV_FILE}" ] || die "缺少 ${ENV_FILE}（需要 ARK_API_KEY 等；模板见 ${SERVER}/.env.example），且不入 git"

# 依赖：Brain 需要 Flask（server/requirements.txt）。缺 venv 就现建，装不上退系统包。
if [ ! -x "${PY}" ]; then
  log "创建 venv ${VENV}"
  python3 -m venv "${VENV}" || die "python3 -m venv 失败"
fi
if ! "${PY}" -c 'import flask' >/dev/null 2>&1; then
  log "安装依赖（$(basename "${REQ}")）"
  if ! "${PY}" -m pip install -q --disable-pip-version-check -r "${REQ}"; then
    warn "pip 安装失败（离线？）→ 用 --system-site-packages 重建 venv 兜底"
    rm -rf "${VENV}"
    python3 -m venv --system-site-packages "${VENV}" || die "重建 venv 失败"
  fi
fi
"${PY}" -c 'import flask' >/dev/null 2>&1 || die "venv 里没有 Flask，请联网后重跑本脚本"

mkdir -p "${SERVER}/data" "${SERVER}/llm_logs" "${SERVER}/uploads" "${LOG_DIR}"

# 已在运行就不重复拉起（平台重启前都会先 stop；这里是防御性检查）。
if [ -f "${PID_FILE}" ]; then
  old="$(tr -d '[:space:]' < "${PID_FILE}" || true)"
  if [ -n "${old}" ] && kill -0 "${old}" 2>/dev/null; then
    log "已在运行 pid=${old}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

# 端口占用守卫：真被占用就响亮失败（别把老 Brain 盖成半死状态）。
if command -v lsof >/dev/null 2>&1; then
  holder="$(lsof -nP -iTCP:"${BRAIN_PORT}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "${holder}" ]; then
    die "端口 ${BRAIN_PORT} 已被 pid=${holder} 占用：$(ps -o command= -p "${holder}" 2>/dev/null | head -c 160)
      先停掉占用者（老仓库起的 Brain 也要停：bash scripts/stop.sh 会按端口兜底识别）"
  fi
fi

log "启动 部署版本=${APP_VERSION} 监听=0.0.0.0:${BRAIN_PORT} runtime=${RUNTIME_DIR}"
log "数据目录看 ${ENV_FILE} 的 BRAIN_DATA_DIR（未设置则 ${SERVER}/data）"
cd "${SERVER}"
nohup env BRAIN_ORIGIN="${BRAIN_ORIGIN:-lan}" "${PY}" home_brain.py >> "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"
pid="$(cat "${PID_FILE}")"

for _ in $(seq 1 60); do
  if ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${PID_FILE}"
    echo "[start][错误] 进程已退出，最近日志：" >&2
    tail -30 "${LOG_FILE}" >&2 || true
    exit 1
  fi
  if curl -fsS -m 2 "http://127.0.0.1:${BRAIN_PORT}/health" >/dev/null 2>&1; then
    log "启动成功 pid=${pid} 健康=http://127.0.0.1:${BRAIN_PORT}/health log=${LOG_FILE}"
    exit 0
  fi
  sleep 0.5
done

echo "[start][错误] 30s 内 /health 未就绪，最近日志：" >&2
tail -30 "${LOG_FILE}" >&2 || true
kill "${pid}" 2>/dev/null || true
rm -f "${PID_FILE}"
exit 1
