"""tests/scripts/test_dockerignore_context.py — 构建上下文泄漏守护（v0.9.13 · P0）。

**P0 实证**：本仓无 `.dockerignore` 而 `Dockerfile:14` 是 `COPY . .`
⇒ 2026-08-01 排练期从本工作树 build 的两个镜像里，`.env`（含 `KNOT_MASTER_KEY` / `JWT_SECRET`
/ DB 密码 / 4 个 LLM key）· `.git`（125M 全历史）· 24 个含明文凭据的 `.bak` · `.venv`
**全部真的在**（已销毁 + build cache 已清）。

═══ ⭐ 判据为什么必须跑**真 Docker**（Stage 3 R3，我上稿的错）═══
上一稿打算用 Python 复现 `.dockerignore` 的匹配语义 —— **那是错的**：
**被测对象就是 Docker 的行为**，不用 Docker 就测不了它。
（实证：守护者与我曾就「`.git/` 带斜杠能否排掉一个 `.git` 文件」产生分歧，
**双方各跑一次真 build 才定案** —— Docker 对 pattern 做 `filepath.Clean`，两种写法等价。
若当时用 Python matcher 判，得到的只是「我们各自以为的语义」。）
⇒ Python 层只留 `Se0`（清单完整性，格式守卫），**不得**称为安全守护。

═══ ⚠️⚠️ 两条硬约束（Codex R4 + 守护者放大）═══
1. **canary 必须逐族真造**：clean CI 上本来就没有 `.env` / 真库 / 备份
   ⇒ 负向断言会**因为文件根本不存在而绿** = **对空集做否定断言恒真**
   （正是 v0.9.12 立进 CLAUDE.md「跑 revert 前四问」第 ③ 条的那个形态）。
2. ⛔ **mutant 只准跑在合成 fixture 上** —— **严禁**在真实含密钥工作树上 build「坏规则」变体，
   否则一次 mutant 就**再造一个被污染的镜像**（本会话已经造过两个）。
   本文件的所有 mutant 都在 `tmp_path` 里跑，且 fixture 里的「秘密」全是假值。
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tarfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO / ".dockerignore"

# 必排规则（少一条即红）—— 与 `.dockerignore` 里的注释互为镜像
_REQUIRED_RULES = (
    ".env", ".env.*", "**/.git",
    "data/", "knot/data/",            # ⚠️ 两个都要：根锚定 ⇒ `data/` 排不到 `knot/data/`
    "**/*.bak", "**/*.bak-*",
    ".venv/", "**/node_modules/", "**/__pycache__/",
)


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "buildx", "version"], check=False,
                              capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_ok(),
    reason="需要 docker buildx —— 阻断执行点是 CI 的 dockerignore-context job（见 ci.yml）",
)


def _context_entries(ctx_dir: pathlib.Path, tmp_out: pathlib.Path) -> set[str]:
    """把 `ctx_dir` 当构建上下文跑一次真 build，返回**实际进入上下文**的路径集。

    ⭐ `FROM scratch` + BuildKit tar exporter：**零 Docker Hub 拉取**
    （`scratch` 是保留的空镜像，不需要任何 registry）⇒ 本判据可以是**阻断门**，
    不会把 `ci.yml:134` 那条 `continue-on-error` 当初要避的 rate-limit 噪声请回来。
    ⚠️ tar **必须写到上下文之外** —— 实测写在里面会自包含（下次跑还会含上次的 tar）。
    """
    df = tmp_out / "ctx.Dockerfile"
    df.write_text("FROM scratch\nCOPY . /ctx\n", encoding="utf-8")
    tar_path = tmp_out / "ctx.tar"
    subprocess.run(
        ["docker", "buildx", "build", "-f", str(df),
         "--output", f"type=tar,dest={tar_path}", str(ctx_dir)],
        capture_output=True, check=True, timeout=600,
    )
    with tarfile.open(tar_path) as t:
        return {n[len("ctx/"):] for n in t.getnames()
                if n.startswith("ctx/") and not n.endswith("/")}


# ─── Se0（纯 Python · 格式守卫，**不是**安全守护）───────────────────────────

def test_Se0_dockerignore_has_every_required_rule():
    """必排清单少一条即红 —— 防有人「顺手」删掉一行。

    ⚠️ 本条是**格式守卫**，安全结论只由 Se1/Se2 的真 Docker oracle 给（Stage 3 R8 降级）。
    """
    assert DOCKERIGNORE.exists(), ".dockerignore 不存在 —— 那正是本片要修的 P0"
    lines = {ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()}
    missing = [r for r in _REQUIRED_RULES if r not in lines]
    assert not missing, (
        f".dockerignore 缺以下必排规则：{missing}\n"
        "    ⚠️ 特别注意 `data/` 与 `knot/data/` **两条都要** —— 含 `/` 的 pattern 是**根锚定**，\n"
        "       `data/` 排不到 `knot/data/`。（前者是 DEPLOY 的挂载点、部署主机上会长出来。）"
    )


def test_Se0b_only_the_root_dockerignore_exists():
    """全仓只允许**根** `.dockerignore`（Codex R7 后半）。

    ⚠️ Docker 支持 **Dockerfile 专属**的 `<dockerfile>.dockerignore`，它**整份覆盖**根规则
    ⇒ 一个 `ctx.Dockerfile.dockerignore` 就能**静默作废**本片的全部守护。
    而本片的 Se1/Se2 恰恰引入了一个叫 `ctx.Dockerfile` 的 fixture ⇒ **给这条路取了名字**
    ⇒ 现在就把它封上（一行断言，最省）。
    """
    found = sorted(
        p.relative_to(REPO).as_posix()
        for p in REPO.rglob("*.dockerignore")
        if not any(part in {".venv", "node_modules", ".git", ".claude"} for part in p.parts)
    )
    assert found == [".dockerignore"], (
        f"除根 `.dockerignore` 外发现其他 ignore 文件：{found}\n"
        "    ⚠️ Dockerfile 专属 ignore（`<name>.Dockerfile.dockerignore`）会**整份覆盖**根规则\n"
        "       ⇒ 本片的全部守护会被静默作废。"
    )


# ─── canary fixture：逐族真造（否则负向断言在空集上恒真）────────────────────

_CANARY_SECRET = "CANARY-FAKE-SECRET-8Q4Z"

# 每族 = (族名, [该族的文件], 拆掉哪条规则会让它逃逸)
_FAMILIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("根 data/",        ("data/knot.db", "data/knot.db-wal"),                     "data/"),
    ("包内 knot/data/", ("knot/data/knot.db", "knot/data/knot.db-wal",
                         "knot/data/knot.db-shm"),                                "knot/data/"),
    ("env",             (".env", ".env.local"),                                   ".env"),
    # ⭐ 根目录形态 + 子目录指针形态**合并为一族**：per-family mutant 实测
    #    `**/.git` 已覆盖根 `.git` ⇒ 保留两条规则会让其中一条**无法被检验**（冗余即盲区）。
    ("git（根 + 子目录指针）", (".git/config", ".git/HEAD", "sub_wt/.git", "deep/nest/.git"), "**/.git"),
    # ⚠️ 备份 canary **不能**放 `knot/data/` —— 那里被 `knot/data/` 规则顶班 ⇒ 摘掉 `**/*.bak`
    #    也不会逃逸 ⇒ 该族的 mutant 变成空判据（实测抓到，v3.1-B #7）。放到无人覆盖的目录。
    ("备份",            ("backups/x.bak", "backups/x.bak-wal"),                    "**/*.bak"),
    ("venv",            (".venv/pyvenv.cfg", ".venv/lib/site.py"),                 ".venv/"),
    ("嵌套 node_modules", ("frontend/node_modules/a.js", "deep/x/node_modules/b.js"), "**/node_modules/"),
    # ⚠️ 同理：`.pyc` 被 `**/*.py[cod]` 顶班 ⇒ 本族用**非 .pyc** 文件，才测得到目录规则本身。
    ("pycache",         ("knot/__pycache__/CACHEDIR.TAG",),                         "**/__pycache__/"),
)

# 本片**刻意不排**的（下一片才处理）—— 正向断言，让这个决定**机械可见**
_MUST_STAY = ("knot/main.py", "requirements.txt", "frontend/package-lock.json",
              "knot/repositories/schema.sql", "knot/prompts/sql_planner.md",
              "knot/services/agents/_template_catalog.py",
              "knot/services/agents/_local_catalog.py")


def _make_fixture(root: pathlib.Path, dockerignore_text: str) -> None:
    """造一个**合成**上下文：逐族真造 canary + 必留文件。⛔ 秘密全是假值。"""
    (root / ".dockerignore").write_text(dockerignore_text, encoding="utf-8")
    for _name, files, _rule in _FAMILIES:
        for rel in files:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_CANARY_SECRET, encoding="utf-8")
    for rel in _MUST_STAY:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("keepme", encoding="utf-8")


@requires_docker
def test_Se1_no_canary_family_survives_into_the_context(tmp_path):
    """⛔ 负向：**逐族真造**的 canary 一个都不得进入构建上下文。

    ⚠️ 「逐族真造」是本测存在的全部理由：clean CI 上没有 `.env`/真库/备份
    ⇒ 不造就等于**在空集上做否定断言**（恒真，v0.9.12「四问」③）。
    """
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    _make_fixture(ctx, DOCKERIGNORE.read_text(encoding="utf-8"))
    entries = _context_entries(ctx, tmp_path)

    # 前提自证：fixture 真的造出了这些文件（否则本测在空跑）
    for _name, files, _rule in _FAMILIES:
        for rel in files:
            assert (ctx / rel).exists(), f"注入前提不成立：{rel} 没造出来 ⇒ 本测空跑"

    leaked = sorted(e for e in entries
                    if any(e == rel or e.startswith(rel.rstrip("/") + "/")
                           for _n, fs, _r in _FAMILIES for rel in fs)
                    or e.endswith("/.git") or e == ".git")
    assert not leaked, (
        f"以下 canary 进入了构建上下文（= 会被烤进镜像层）：{leaked}\n"
        f"    上下文共 {len(entries)} 项。⇒ 检查 `.dockerignore` 对应规则。"
    )


@requires_docker
def test_Se2_required_files_still_reach_the_context(tmp_path):
    """✅ 正向：必需文件必须**仍在**上下文里 —— **这一半不可省**。

    ⭐ Codex R4 的教训：**纯负断言在空集上恒真** ——
    一个把整个仓库都排除掉的 `.dockerignore` 会让 Se1 通过，而镜像**完全坏掉**。

    ⚠️ `_local_catalog.py` **刻意在必留清单里**：本片**不排**私有 catalog
    （排它会让 file 层落 `_template_catalog` ⇒ HTTP 查询静默落 SQL = v0.7.29b 失败模式，
    而 R-v096-4 明禁）。⇒ 下一片改 bind-mount + 启动 WARN 后才排。
    **把这个决定写成断言，是为了让下一片必须显式改掉它 —— 决定不能静默翻转。**
    """
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    _make_fixture(ctx, DOCKERIGNORE.read_text(encoding="utf-8"))
    entries = _context_entries(ctx, tmp_path)
    missing = [f for f in _MUST_STAY if f not in entries]
    assert not missing, (
        f"以下必需文件**没能**进入构建上下文 ⇒ 镜像会坏：{missing}\n"
        f"    上下文共 {len(entries)} 项 ⇒ `.dockerignore` 排得太宽。"
    )


@requires_docker
@pytest.mark.parametrize("family,files,rule", _FAMILIES, ids=[f[0] for f in _FAMILIES])
def test_Se1_mutant_each_family_reddens_on_its_own(tmp_path, family, files, rule):
    """⭐ **每族单独验**「删掉对应规则 ⇒ 该族逃逸」—— 不是验一次总的（守护者点名）。

    ⛔ mutant 只跑在**合成 fixture** 上（`tmp_path`），秘密全是假值 ——
    **严禁**在真实含密钥工作树上 build 坏规则变体（本会话已造过两个污染镜像）。
    """
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    mutated = "\n".join(ln for ln in text.splitlines() if ln.strip() != rule)
    assert mutated != text, f"注入前提不成立：`.dockerignore` 里找不到规则 {rule!r} ⇒ 本测空跑"
    _make_fixture(ctx, mutated)

    entries = _context_entries(ctx, tmp_path)
    escaped = [rel for rel in files if rel in entries]
    assert escaped, (
        f"摘掉规则 {rule!r} 后，{family} 族**仍然没有**逃逸出来 ⇒ 该规则可能是**空判据**\n"
        f"    （或另有别的规则在顶班 —— 两种都意味着 Se1 对这一族的绿是假的）。\n"
        f"    本族文件：{list(files)}；上下文共 {len(entries)} 项。"
    )


@requires_docker
def test_Se2_mutant_over_broad_ignore_is_caught(tmp_path):
    """反向 mutant：排太宽（`**`）⇒ Se2 必须红 —— 证明正向那一半真的在守。"""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    _make_fixture(ctx, "**\n")
    entries = _context_entries(ctx, tmp_path)
    still = [f for f in _MUST_STAY if f in entries]
    assert not still, f"`**` 全排后竟仍有文件进上下文：{still}（说明 Se2 的判据本身有问题）"


# ─── 真仓库上的实测（本片是否真的消掉 P0）───────────────────────────────────

@requires_docker
def test_real_repo_context_carries_no_secrets(tmp_path):
    """⭐ 在**真仓库**上跑一次：上下文里不得有 `.env` / `.git` / `.venv` / `node_modules` / 备份 / 库。

    ⚠️ 与 Se1 的分工：Se1 用合成 fixture 保证**规则本身**有效（且可安全跑 mutant）；
    本测保证**这个仓库此刻**的实际上下文是干净的（真仓库里可能有 fixture 想不到的东西）。
    """
    entries = _context_entries(REPO, tmp_path)
    bad = sorted(e for e in entries if (
        e == ".env" or e.startswith(".env.") or e == ".git" or e.startswith(".git/")
        or e.startswith(".venv/") or "/node_modules/" in f"/{e}"
        or ".bak" in e or e.startswith("data/") or e.startswith("knot/data/")
    ))
    assert not bad, f"真仓库的构建上下文里仍有敏感项：{bad[:20]}（共 {len(bad)} 个）"
    assert "knot/main.py" in entries, "真仓库上下文里连 knot/main.py 都没有 ⇒ 排得太宽"
