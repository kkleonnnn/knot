#!/usr/bin/env bash
# v0.3.0 重构迁移脚本（审计参考；实际改动以 PR 提交为准）
#
# 本脚本用于：
#   1. 部署方升级到 v0.3.0 时清掉本地老 import 残留
#   2. 资深 review 时复盘"哪些文件被 git mv，哪些是手动拆分"的边界
#
# 幂等：可重复执行；执行前 git stash 本地未提交改动。
set -euo pipefail

echo "▶ v0.3.0 工程化重构 — 迁移概览"
echo ""
echo "本 PR 已自动完成的迁移："
echo "  ✓ pip install -e . 工程化（pyproject.toml + setup.py 兜底）"
echo "  ✓ models/ 顶级包（10 个领域叶子文件，import-linter 锁死叶子）"
echo "  ✓ config/ 子包（settings.py 单例 + module-level 常量兼容）"
echo "  ✓ repositories/ 9 模块（拆分 persistence.py 758 行）"
echo "  ✓ schema.sql 集中外置"
echo "  ✓ 全局裸名 import 重写：所有 'import persistence / config / llm_client...'"
echo "    都改为 'from knot.X.Y import Z' 绝对路径"
echo "  ✓ main.py 删 sys.path.insert hack"
echo "  ✓ .importlinter 4 层 contract（FIXME-v0.3.1/v0.3.2/v0.3.3 标注 contract 升级点）"
echo "  ✓ pre-commit + GitHub Actions CI"
echo ""
echo "BREAKING：老外部脚本如有 'import persistence' 必须改写为："
echo "    from knot.repositories.user_repo import get_user_by_id"
echo "    from knot.repositories.settings_repo import get_app_setting"
echo "    ...等 (按 *_repo.py 模块化访问)"
echo ""
echo "v0.3.1 起将删除 knot.repositories 包级的 facade re-export，"
echo "完整切换到模块级 import。届时本 shim 失效（FIXME-v0.3.1 标记）。"
echo ""
echo "▶ 升级本地环境（部署方 / 合作伙伴执行）："
echo "  pip install -e \".[dev]\""
echo "  pre-commit install"
echo "  pytest tests/ -v"
echo "  lint-imports"
