"""tests/test_deploy_md_exists.py — v0.6.0.10 DEPLOY.md 完整性守护。

防部署手册被误删 / 关键段缺失 — 这是运维 + AI 助手的优先参考资料。
"""
from __future__ import annotations

from pathlib import Path


def test_deploy_md_exists_at_root():
    """DEPLOY.md 必须在仓库 root（运维 git clone 后立即可见）。"""
    p = Path("DEPLOY.md")
    assert p.is_file(), "DEPLOY.md 必须在仓库 root（运维优先参考）"


def test_deploy_md_has_required_sections():
    """部署手册必须含 6 个关键段（增删段时同步更新本测试）。"""
    src = Path("DEPLOY.md").read_text(encoding="utf-8")
    required = [
        "一键部署",
        "部署必读",
        "KNOT_MASTER_KEY",     # 终身密钥提醒
        "admin / admin123",    # 默认账号提醒
        "升级流程",
        "故障排查",
        "JWT_SECRET",          # 安全配置
        "deploy_checklist.sh", # 自动化脚本引用
        # v0.6.0.11 新增 — 配置加载机制 + 12-Factor 合规说明
        "12-Factor",           # 合规清单段
        "配置优先级",          # 系统 env > .env > fallback
        "data_sources",        # DB_HOST 仅 seed 不动运行时数据源
        # v0.6.0.12 新增 — 生产安全段（运维提问：会不会写库）
        "生产安全",            # §标题
        "STRICT_READONLY_GRANTS",  # 强约束 env
        "_is_safe_sql",        # Layer 1 应用层守护
        "GRANT SELECT",        # Layer 3 DBA 只读账号示例
    ]
    for keyword in required:
        assert keyword in src, f"DEPLOY.md 缺关键段 / 关键字: {keyword!r}"


def test_readme_links_to_deploy_md():
    """README 必须有指向 DEPLOY.md 的链接（运维入口路径完整）。"""
    src = Path("README.md").read_text(encoding="utf-8")
    assert "DEPLOY.md" in src, "README.md 必须链接到 DEPLOY.md（运维入口）"
