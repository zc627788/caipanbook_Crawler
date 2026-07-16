#!/usr/bin/env bash
# 文书网日批采集：每日跑一次，触顶或任务完自然退出；次日预算自动清零
set -euo pipefail
cd "$(dirname "$0")/.."

# 按服务器环境修改：
#   PROXY  — 默认代理；账号 config/account_pool.json 的 current_proxy 优先
#   无代理时: export PROXY=""
export PROXY="${PROXY:-http://127.0.0.1:10808}"

LOG_DIR="${LOG_DIR:-./logs}"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/daily_${STAMP}.log"

echo "[$(date -Iseconds)] start daily crawl proxy=${PROXY:-direct}" | tee -a "$LOG_FILE"

if [[ -n "${PROXY}" ]]; then
  python crawler_wenshu.py --proxy "$PROXY" 2>&1 | tee -a "$LOG_FILE"
else
  python crawler_wenshu.py --proxy "" 2>&1 | tee -a "$LOG_FILE"
fi

EC=${PIPESTATUS[0]}
echo "[$(date -Iseconds)] exit=$EC" | tee -a "$LOG_FILE"
exit "$EC"
