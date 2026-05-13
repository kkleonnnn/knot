"""tests/scripts/test_dockerfile_copy.py — v0.6.0.1 G-6 守护者立约。

R-PA-7.1/7.2/7.3 三守护字面 grep 验证（不解析 Dockerfile AST — 轻量 +
跨 docker 版本稳定 — R-PA-16）：

- R-PA-7.1: COPY knot/prompts/ /app/knot/prompts/
- R-PA-7.2: COPY knot/services/agents/_template_catalog.py /app/knot/services/agents/_template_catalog.py
- R-PA-7.3: COPY --from=frontend-builder /knot/static ./knot/static
  （注意：commit 9 修复路径 /knot/static — 不是 /app/knot/static）

R-PA-11（commit 9 守护者立约）：Dockerfile 多 stage WORKDIR + vite outDir
相对路径一致性。本测试是 R-PA-11 字面单元测试化。

闸门级别：本地 pytest（毫秒级）+ G-5 CI docker build smoke（端到端）— 互补。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = (REPO / "Dockerfile").read_text(encoding="utf-8")


def test_R_PA_7_1_dockerfile_copies_prompts_to_app():
    """Dockerfile 必含 prompts 目录 COPY（守护启动期 seed 对象）。"""
    pattern = r"COPY\s+knot/prompts/\s+/app/knot/prompts/"
    assert re.search(pattern, DOCKERFILE), (
        "Dockerfile 缺 R-PA-7.1 守护字面 'COPY knot/prompts/ /app/knot/prompts/'；"
        "详 docs/plans/v0.6.0-phase-a-sanitize.md §3 R-PA-7"
    )


def test_R_PA_7_2_dockerfile_copies_catalog_template():
    """Dockerfile 必含 _template_catalog.py COPY（守护 catalog fallback 第 3 级）。"""
    pattern = r"COPY\s+knot/services/agents/_template_catalog\.py\s+/app/knot/services/agents/_template_catalog\.py"
    assert re.search(pattern, DOCKERFILE), (
        "Dockerfile 缺 R-PA-7.2 守护字面 '_template_catalog.py' 显式 COPY；"
        "详 docs/plans/v0.6.0-phase-a-sanitize.md §3 R-PA-7"
    )


def test_R_PA_7_3_dockerfile_copies_static_from_frontend_builder():
    """Dockerfile frontend-builder → python stage 路径对齐（commit 9 LOCKED 盲区 #7 补救）。

    关键断言：路径必须是 /knot/static（不是 /app/knot/static）—
    vite.config.js outDir='../knot/static' 相对 frontend WORKDIR=/frontend
    解析为 /knot/static（容器根）。
    """
    # 必含正确路径
    pattern_correct = r"COPY\s+--from=frontend-builder\s+/knot/static\s+\./knot/static"
    assert re.search(pattern_correct, DOCKERFILE), (
        "Dockerfile 缺 R-PA-7.3 守护字面 'COPY --from=frontend-builder /knot/static'；"
        "详 docs/plans/v0.6.0-phase-a-sanitize.md §3 R-PA-11 (v0.6.0-hotfix commit 9)"
    )

    # 必不含错误路径（commit 9 修复前的 bug 状态）
    pattern_buggy = r"COPY\s+--from=frontend-builder\s+/app/knot/static"
    assert not re.search(pattern_buggy, DOCKERFILE), (
        "Dockerfile 含 commit 9 修复前的错误字面 '/app/knot/static' — "
        "vite outDir 解析后实际产物在 /knot/static（不是 /app/knot/static）"
    )
