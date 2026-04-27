#!/usr/bin/env bash
# scripts/profile_pyspy.sh — 用 py-spy 给运行中的 BI-Agent 抓火焰图 / 实时 top
#
# 用法：
#   1) 先启动 server： python3 -m uvicorn bi_agent.main:app --port 8000
#   2) 另开终端跑一次压力 / 几次查询，让进程吃负载
#   3) 运行：
#        ./scripts/profile_pyspy.sh top         # 实时类似 top 视图
#        ./scripts/profile_pyspy.sh flame 60    # 抓 60s 火焰图，输出 flame.svg
#
# 依赖：pip install py-spy（macOS 需要 sudo 才能 attach 已经在跑的进程）
set -euo pipefail

MODE=${1:-top}
DURATION=${2:-30}

PID=$(pgrep -f "uvicorn bi_agent.main:app" | head -1 || true)
if [[ -z "$PID" ]]; then
  echo "未找到 uvicorn bi_agent.main:app 进程，先把 server 跑起来。" >&2
  exit 1
fi
echo "attach to PID=$PID"

case "$MODE" in
  top)
    sudo py-spy top --pid "$PID"
    ;;
  flame)
    OUT="flame_$(date +%Y%m%d_%H%M%S).svg"
    sudo py-spy record --pid "$PID" --duration "$DURATION" --output "$OUT" --rate 100
    echo "wrote $OUT"
    ;;
  dump)
    sudo py-spy dump --pid "$PID"
    ;;
  *)
    echo "usage: $0 {top|flame [seconds]|dump}" >&2
    exit 2
    ;;
esac
