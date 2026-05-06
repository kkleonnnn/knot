#!/usr/bin/env bash
# v0.3.0 回滚脚本：直接 revert 合并提交。
set -euo pipefail
echo "▶ 回滚 v0.3.0 重构"
echo ""
echo "找到 v0.3.0 squash merge 提交后执行："
echo "  git revert -m 1 <merge-sha>"
echo "  git push origin main"
echo ""
echo "或直接重置（DESTRUCTIVE，仅在没人 pull 过的情况下）："
echo "  git reset --hard <pre-merge-tag>"
echo "  git push origin main --force-with-lease"
