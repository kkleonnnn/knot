"""tests/test_contracts_renamed.py — v0.5.0 R-71 contract 数仍 7 + Contract 7 forbidden 同步守护（TDD）。

R-71 关键：Contract 7 crypto-only-in-allowed-callers 的 forbidden_modules 必须从
旧名 改 knot.core.crypto，否则 lint-imports 显示 KEPT 但实际 forbidden
项不存在 = 契约失效但不报警（守护者答资深架构师维度 1）。

⚠️ 本文件含字面量断言（旧包名 grep 目标）；_v050_rename.py 必须 SKIP 本文件。
"""
import configparser
import subprocess
from pathlib import Path


IMPORTLINTER_PATH = Path(".importlinter")
# 字面量分割避免被 _v050_rename.py 误替
_OLD_NS = "bi" + "_agent"  # 旧命名空间字面量


def _parse_importlinter() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(IMPORTLINTER_PATH)
    return cfg


def test_R71_root_package_is_knot():
    cfg = _parse_importlinter()
    assert cfg.get("importlinter", "root_package") == "knot", (
        "root_package 必须改 knot"
    )


def test_R71_contract_count_is_7():
    cfg = _parse_importlinter()
    contract_sections = [s for s in cfg.sections() if s.startswith("importlinter:contract:")]
    assert len(contract_sections) == 7, (
        f"contract 数应仍为 7（不增不减）；找到 {len(contract_sections)}"
    )


def test_R71_contract_7_forbidden_modules_replaced_to_knot():
    """R-71 关键：Contract 7 crypto-only-in-allowed-callers 的 forbidden_modules
    必须改为 knot.core.crypto；旧名严禁残留。"""
    cfg = _parse_importlinter()
    section = "importlinter:contract:crypto-only-in-allowed-callers"
    assert cfg.has_section(section), "Contract 7 crypto contract 必须存在"
    forbidden = cfg.get(section, "forbidden_modules")
    assert "knot.core.crypto" in forbidden, (
        f"R-71：Contract 7 forbidden 必须含 knot.core.crypto；实际：{forbidden!r}"
    )
    assert f"{_OLD_NS}.core.crypto" not in forbidden, (
        f"R-71：旧名严禁残留；实际：{forbidden!r}"
    )


def test_R71_no_old_namespace_in_any_contract_section():
    """所有 7 contracts 的 source_modules / forbidden_modules / layers 不得残留旧命名空间。"""
    cfg = _parse_importlinter()
    for section in cfg.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        for key in ("source_modules", "forbidden_modules", "layers"):
            if cfg.has_option(section, key):
                value = cfg.get(section, key)
                assert _OLD_NS not in value, (
                    f"{section}.{key} 不得含 {_OLD_NS}；实际：{value!r}"
                )


def test_R71_lint_imports_all_kept():
    """子进程跑 lint-imports 全 KEPT（实际验证 contract 守护正确加载）。

    lint-imports binary 解析顺序：
    1) PATH（CI 装好）
    2) Python 解释器同目录 bin/lint-imports（pip install --user 路径）
    3) shutil.which 兜底
    """
    import shutil
    import sys
    from pathlib import Path

    bin_path = shutil.which("lint-imports")
    if not bin_path:
        candidate = Path(sys.executable).parent / "lint-imports"
        if candidate.exists():
            bin_path = str(candidate)
    if not bin_path:
        # macOS python -m user install 路径
        for p in (
            Path.home() / "Library" / "Python" / "3.9" / "bin" / "lint-imports",
            Path.home() / "Library" / "Python" / "3.10" / "bin" / "lint-imports",
            Path.home() / "Library" / "Python" / "3.11" / "bin" / "lint-imports",
            Path.home() / ".local" / "bin" / "lint-imports",
        ):
            if p.exists():
                bin_path = str(p)
                break
    assert bin_path, "lint-imports binary 未找到（pip install -e .[dev] 后应可用）"

    result = subprocess.run(
        [bin_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"lint-imports 必须全 KEPT；returncode={result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    output = result.stdout + result.stderr
    # 7 contracts KEPT 验证（lint-imports 版本输出文案宽容匹配）
    assert "7 kept" in output.lower() or output.count("KEPT") >= 7, (
        f"应见 7 KEPT；输出节选：{output[:600]}"
    )


def test_R71_contract_7_allow_indirect_imports_preserved():
    """Contract 7 allow_indirect_imports = True 行为不变（v0.4.5 设定）。"""
    cfg = _parse_importlinter()
    section = "importlinter:contract:crypto-only-in-allowed-callers"
    assert cfg.has_option(section, "allow_indirect_imports")
    assert cfg.get(section, "allow_indirect_imports").strip().lower() == "true"


def test_R71_layered_architecture_uses_knot_namespace():
    """Contract 1 layered-architecture 4 layers 全部 knot.X 命名空间。"""
    cfg = _parse_importlinter()
    section = "importlinter:contract:layered-architecture"
    layers = cfg.get(section, "layers")
    for prefix in ("knot.api", "knot.services", "knot.repositories", "knot.adapters", "knot.models"):
        assert prefix in layers, f"layered-architecture 应含 {prefix}；实际：{layers!r}"
