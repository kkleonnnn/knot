"""tests/test_doc_invariants.py — v0.6.4.11 task #44 doc-不变量 CI 守护一揽子.

元教训：doc 宣称的不变量（版本字面 / 文件集 / CHANGELOG）无 CI 强制 → 跨 PATCH 静默 drift
（8 stale-doc 数据点，PRIMARY = Shell sidebar version stale v0.6.4.2 drift 8 PATCH）。

本文件补 3 个 grounded 缺口（守护者 grounded 清单）；现有守护勿重造（奥卡姆）：
- R-72 main.py version → tests/test_rename_smoke.py
- R-181 Login footer + R-185 KnotLogo DOM + KNOW-1 README → tests/test_login_version_sync.py
- Foundation additive → tests/test_foundation_additive.py
"""
import re
from pathlib import Path


def _main_version():
    from knot.main import app
    return app.version


# ─── PRIMARY: 前端版本单一真相源 bridge（Shell drift 8 PATCH 根治）──────────

def test_app_version_synced_with_main():
    """frontend/src/version.js APP_VERSION === knot.main.app.version.

    Shell sidebar + Login footer 读 {APP_VERSION}（不再硬编）→ 本 bridge 保前端版本不 drift。
    改 main.py 不改 version.js（或反之）即红 —— 根治 v0.6.4.2 stale 8 PATCH 的条件式同步缺陷。
    """
    src = Path("frontend/src/version.js").read_text(encoding="utf-8")
    m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "version.js 须 export const APP_VERSION = '...'"
    assert m.group(1) == _main_version(), (
        f"前端 version.js APP_VERSION={m.group(1)!r} ≠ main.py version={_main_version()!r}（版本 drift）"
    )


def test_shell_sidebar_renders_app_version():
    """Shell.jsx sidebar 渲染 `v{APP_VERSION}`（非硬编 version 字面）+ import version.js.

    断言渲染引用（非仅 import）→ 与 bridge 组合 ⟹ sidebar = main version。
    防 v0.6.4.2 式硬编 stale 复发。
    """
    src = Path("frontend/src/Shell.jsx").read_text(encoding="utf-8")
    assert "v{APP_VERSION}" in src, "Shell.jsx sidebar 须渲染 v{APP_VERSION}（version.js 单一真相源）"
    assert "version.js" in src, "Shell.jsx 须 import APP_VERSION from version.js"
    assert not re.search(r">v\d+\.\d+\.\d+", src), "Shell.jsx 不得含硬编 version 字面（>vN.N.N）"


# ─── KnotLogo 渲染集（精确 4 渲染；Shared 定义归 R-185）──────────────────

def test_knotlogo_file_set():
    """`<KnotLogo` JSX 渲染精确命中 4 文件：Shell / Login / Enroll / ForceChangePassword.

    v0.6.4.12 收紧：子串 `"KnotLogo"` → `"<KnotLogo"`（仅渲染引用计入）。
    Shared.jsx 仅 `export function KnotLogo` 定义（0 渲染），由 R-185
    （test_login_version_sync）守护 → 收紧不丢守护，消注释/字符串 false-red。
    R-199.5：KnotLogo 文件集随 brand/app 屏演进（v0.6.2.0 +Enroll/ForceChange）。
    v0.8.5 ②a：BI 短暂自建 BIShell 时命中 BI.jsx；后 BI 改共用 <AppShell>（Shell 渲染 brand）→
    BI.jsx 不再直渲 KnotLogo，回落 4 渲染（Shell 一处覆盖 chat/BI/admin 全部 app 外壳）。
    非 brand/app 屏混入 / 任一渲染蒸发 → 红。
    """
    root = Path("frontend/src")
    hits = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.jsx")
        if "<KnotLogo" in p.read_text(encoding="utf-8")
    )
    expected = sorted([
        "Shell.jsx",
        "screens/Login.jsx",
        "screens/Enroll.jsx",
        "screens/ForceChangePassword.jsx",
    ])
    assert hits == expected, f"KnotLogo 渲染集漂移（R-199.5 渲染=4）：实际 {hits} ≠ 预期 {expected}"


# ─── CHANGELOG 顶部 version 同步（漏条目 / stale → 红）────────────────────

def test_changelog_top_version_synced_with_main():
    """CHANGELOG 首个 `## [` 条目 header 含 `v{main.py version}`.

    防 v0.6.4.1.1 式漏 CHANGELOG 条目 / 顶部 stale（8 数据点之一）。
    """
    lines = Path("CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    top = next((ln for ln in lines if ln.startswith("## [")), None)
    assert top, "CHANGELOG 无 `## [` 条目"
    expected = f"v{_main_version()}"
    assert expected in top, f"CHANGELOG 顶部条目不含 {expected!r}（版本 stale / 漏条目）；实际：{top!r}"


# ─── CHANGELOG 单一 [Unreleased]（历史漏 demote → stale 堆积 → 红）──────────

def test_changelog_single_unreleased():
    """CHANGELOG 恰有 1 个 `## [Unreleased]`（仅当前在飞 PATCH）。

    元教训 #5：约定 = 在飞 `[Unreleased] - vX`、已发 demote `[Released] - vX`；
    历史漏 demote → stale [Unreleased] 堆积（v0.6.4.12 实查 41 条全史 relabel）。
    count==1 防再 drift：每 PATCH 须 demote 上一 top + 新 top 唯一。
    """
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    n = len(re.findall(r"^## \[Unreleased\]", text, flags=re.MULTILINE))
    assert n == 1, f"CHANGELOG `## [Unreleased]` 应恰 1 个（当前在飞）；实际 {n}（历史漏 demote → stale 堆积）"


# ─── v0.9.10 R14：构建产物纳入版本闸门（4 源点此前不含它 ⇒ 漏 3 片无人察觉）────

_STATIC = Path("knot/static")
# ⚠️ **引号无关**（Stage 4 should-fix）：初版锚死反引号（``0.9.10``），而那只是 **esbuild 当前的
#    最小化输出形态** —— 源码 `version.js` 写的其实是单引号。若将来 Vite/esbuild 升级改成 `"0.9.10"`，
#    断言会在**正确的 bundle 上假红**，而那时没人会想到是 minifier 换了引号。
#    反向引用 `\1` 要求首尾同型，避免 `` `0.9.10" `` 这种跨引号的偶然命中。
_QUOTED_SEMVER = re.compile(r"""(['"`])\d+\.\d+\.\d+\1""")
_V_SEMVER = re.compile(r"v\d+\.\d+(?:\.\d+)?")


def _quoted_literal_re(version: str) -> re.Pattern:
    return re.compile(r"""(['"`])""" + re.escape(version) + r"""\1""")


def _index_html_asset_refs() -> set[str]:
    """`index.html` 真正引用的资产集（src= 与 href= 两种，modulepreload 用后者）。"""
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    return set(re.findall(r'(?:src|href)="/(assets/[^"]+)"', html))


def test_static_bundle_version_synced_with_version_js():
    """`knot/static` 构建产物里的版本 == `version.js` APP_VERSION.

    **为什么需要它**：4 源点（main.py / test_rename_smoke / README / version.js）**不含构建产物**
    ⇒ 没有任何闸门看它 ⇒ v0.9.7/.8/.9 三片都 bump 了 4 源点却没重建 static，
    **用户在 UI 侧栏 / Login 页脚看到 v0.9.6 而 API 报 0.9.9**，连漏 3 片无人察觉。

    ⭐ **锚点 = `index.html` 真正引用的那个 chunk**（浏览器会加载的那个）。
    这个锚点让「旧 hash chunk 未删」这个形态**自动消解**：孤儿 chunk 不被引用 ⇒ 不会被加载
    ⇒ 它不是 stale 发布、只是磁盘垃圾（另由 `test_static_assets_no_orphan_chunks` 管卫生）。
    真正危险的是「index.html 指着一个旧 chunk」，而那**恰恰**被本断言抓到。

    ⚠️ **判据 = 反引号包裹的裸版本串** —— APP_VERSION 编译后的实际形状（实测 ``Xe=`0.9.10` ``）。
    两版被证伪的 oracle 记此备考，别再走回头路：
      ① `v\\d+\\.\\d+\\.\\d+` 字面全集 —— UI 源码写的是 `v{APP_VERSION}`，`v` 是**另一个 JSX 文本节点**
         ⇒ `v0.9.10` **不会连续出现**；实测 bundle 里 8 个 `v0.x.y` 全是别处的串。
      ② 裸 semver 字面全集 —— bundle 里合法含大量**依赖**版本字面（实测 `0.4.2`/`1.82.33`/`127.0.0` …）。
    """
    from knot.main import app  # noqa: F401 — 与 main version 的桥由 test_app_version_synced_with_main 守
    src = Path("frontend/src/version.js").read_text(encoding="utf-8")
    m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "version.js 须 export const APP_VERSION = '...'"
    app_version = m.group(1)

    entry = next((r for r in _index_html_asset_refs()
                  if re.fullmatch(r"assets/index-[A-Za-z0-9_-]+\.js", r)), None)
    assert entry, f"index.html 未引用应用入口 chunk（assets/index-*.js）；实际引用：{sorted(_index_html_asset_refs())}"
    entry_path = _STATIC / entry
    assert entry_path.exists(), f"index.html 引用了不存在的 {entry}（构建产物残缺）"

    body = entry_path.read_text(encoding="utf-8", errors="replace")
    # ⚠️ 诊断用的 pattern 提为模块级常量，是因为把它内联进 f-string 时我写成了 `\\d`（raw string 里
    #    = 反斜杠+d，永不匹配数字）⇒ 诊断行恒报 `[]`，**红是红了，但说的是假话**。
    #    根因：诊断代码**只在失败路径上运行** ⇒ 它只能靠真的把它弄红来测试。
    #    ⇒ revert-to-bad 的验收产物是**那条失败消息的原文**，不是「转红了」三个字。
    found = sorted({m.group(0) for m in _QUOTED_SEMVER.finditer(body)})
    assert _quoted_literal_re(app_version).search(body), (
        f"构建产物 stale：{entry} 里找不到被引号包裹的 {app_version!r}（APP_VERSION）。\n"
        f"    该 chunk 里带引号的 semver 实际是：{found}\n"
        f"    ⇒ bump 了 version.js 但没重建前端。修：cd frontend && npm ci && npm run build"
    )


def test_static_assets_no_orphan_chunks():
    """磁盘上的 js/css **精确等于** `index.html` 的引用集（无孤儿、无缺失）。

    `vite.config.js` 有 `emptyOutDir: true` ⇒ 正常构建天然满足；本断言守的是
    **绕过正常构建的手改**（手拷文件 / 关掉 emptyOutDir / 部分回滚）。
    ⚠️ 只覆盖 js/css：字体等由 CSS 引用，不出现在 index.html 里。
    """
    refs = {r for r in _index_html_asset_refs() if r.endswith((".js", ".css"))}
    disk = {str(p.relative_to(_STATIC)) for p in (_STATIC / "assets").glob("*")
            if p.suffix in {".js", ".css"}}
    assert disk == refs, (
        f"构建产物与 index.html 引用集不一致 —— 孤儿：{sorted(disk - refs) or '无'}；"
        f"引用了但磁盘没有：{sorted(refs - disk) or '无'}"
    )


# ─── v0.9.12 Stage 4 should-fix：DEPLOY.md 顶部版本（与 R14 完全同形）────────

def test_deploy_md_top_version_synced_with_main():
    """`DEPLOY.md` 顶部「当前版本」== `main.py` version.

    **为什么现在装而不是进 backlog**（守护者 Stage 4 §III）：
    它**与 R14 完全同形** —— R14 的机制正是「不在 4 源点里 ⇒ 没有闸门 ⇒ 静默漂 3 片」。
    实测本条今天**零闸门**，而 `DEPLOY.md` 顶部已 stale **8 个版本**（写 v0.9.4，实际 0.9.12）。
    ⇒ **同形的问题必须同形处置**：R14 的处置是**当场装闸门**，不是登记。
    「一行的东西放进 backlog」而这条弧刚用三个版本证明了 backlog 是什么。

    判据 = **包含式**（照 README 的 KNOW-1 范式，`test_login_version_sync.py:63`）：
    ⚠️ 不能用精确集合 —— 顶部还合法含 `v0.6.1` / `v0.6.5`（指向旧升级 runbook 的引用）。
    """
    top = Path("DEPLOY.md").read_text(encoding="utf-8")[:1000]
    expected = f"v{_main_version()}"
    # ⚠️ pattern 提为模块级常量 —— **不得内联进 f-string**：本断言初版就是内联的，
    #    在 f-string 里被双重转义成 `\\.`（= 反斜杠+点）⇒ 诊断恒报 `[]`，**红是红了但在撒谎**。
    #    这是本弧**第 4 次**同一机制（v0.9.10 那次也在本文件里，而当时的注释就写着这条教训）。
    #    ⇒ 已由 `tests/test_test_hygiene.py::test_no_regex_literal_inlined_in_fstring` 机械守护。
    found = sorted(set(_V_SEMVER.findall(top)))
    assert expected in top, (
        f"DEPLOY.md 顶部 1000 字符内不含 {expected!r}（运维手册版本 stale）。\n"
        f"    顶部出现的版本串：{found}\n"
        f"    ⇒ 每片 bump 版本时同步 DEPLOY.md 顶部那一行。"
    )
