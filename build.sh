#!/usr/bin/env bash
#
# 打包脚本 —— 遵循「agent-control-plane-deployment」部署系统规范。
#
# 调用方（二选一，均从仓库根执行）：
#   - 控制面流水线：POST /api/deploy-notify {serviceId:"home-agent-brain"}
#   - 独立发版：~/deployment/bin/release.sh home-agent-brain [ref]
#
# 约定（与 agent-benchmark-tool / service-registry 同一套）：
#   - cwd = 仓库根；环境变量 APP_VERSION = <8 位短 hash>
#   - 必须产出 outputs/，其中必须包含 scripts/restart.sh（平台硬性要求）
#   - VERSION / COMMIT / GIT_REPO_URL 由调用方写进发版包，本脚本不写
#   - 运行期可变内容一律不进 outputs/：平台部署是
#       rsync -a --delete --filter='P backend/{.env,data/,runtime.pid,server.log,.watchdog-paused}'
#     即 **runtime 目录里只有 backend/ 那几项和 .git/ 能活过部署**，其余按发版包覆盖。
#     Brain 的实际数据在代码之外（BRAIN_DATA_DIR，默认 ~/database/home-agent-brain），
#     运行期的 .env / pid / log 放 <runtime>/backend/（见 scripts/start.sh）。
#
# 本服务是 Python（不是 Go 二进制）：发版包 = 运行期目录布局，即
#   outputs/{scripts/{start,stop,restart}.sh, server/**(源码), home_brain.py, README.md, .gitignore}
# Python 依赖（Flask）由 scripts/start.sh 在目标机上按 server/requirements.txt 安装
# （venv 会被部署覆盖，所以每次部署都可能重装一次；离线时退 --system-site-packages）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

VERSION="${APP_VERSION:-dev}"
OUT="${ROOT}/outputs"

echo "[build] home-agent-brain version=${VERSION}"
[ -f "${ROOT}/scripts/restart.sh" ] || {
  echo "[build][错误] 缺少 scripts/restart.sh（平台硬性要求）" >&2
  exit 1
}
[ -d "${ROOT}/server" ] || {
  echo "[build][错误] 缺少 server/（Brain 控制面源码）" >&2
  exit 1
}

# 语法体检：Brain 是纯标准库 + Flask，编译一遍就能拦住拼写/缩进级别的问题。
# 不跑单测（那是评审/CI 的事，且本仓有既有失败用例，不该卡住发版）。
if command -v python3 >/dev/null 2>&1; then
  python3 -m compileall -q "${ROOT}/server" >/dev/null || {
    echo "[build][错误] server/ 语法检查未通过（python3 -m compileall）" >&2
    exit 1
  }
  echo "[build] 语法检查通过（compileall server/）"
fi

rm -rf "${OUT}"
mkdir -p "${OUT}/scripts"

# 只搬运行期需要的源码 / 脚本；.git、.venv、数据、日志、上传、密钥一概不进包。
# 注意排除模式是相对「传输根」的（这里传输根就是 server/），所以写 data/ 而不是 server/data/。
rsync -a \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='.venv/' \
  --exclude='.env' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='llm_logs/' \
  --exclude='uploads/' \
  "${ROOT}/server/" "${OUT}/server/"

cp "${ROOT}/home_brain.py" "${OUT}/home_brain.py"
[ -f "${ROOT}/README.md" ] && cp "${ROOT}/README.md" "${OUT}/README.md"
[ -f "${ROOT}/.gitignore" ] && cp "${ROOT}/.gitignore" "${OUT}/.gitignore"
cp "${ROOT}/scripts/start.sh" "${ROOT}/scripts/stop.sh" "${ROOT}/scripts/restart.sh" \
  "${OUT}/scripts/"

# 包里的 __pycache__ 是 compileall 的副产物，清掉（平台 rsync 会把它们铺到 runtime）。
find "${OUT}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

chmod +x "${OUT}/scripts/"*.sh

echo "[build] outputs 就绪："
ls -1 "${OUT}" | sed 's/^/  /'
echo "  scripts/: $(cd "${OUT}/scripts" && ls -1 | tr '\n' ' ')"
