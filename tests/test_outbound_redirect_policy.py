"""⭐ 出网禁令**不可遗漏**（v0.9.22）—— 本片的安全价值**全部押在本文件**。

## 它守什么
出网 allowlist **只管第一跳**：目标回一个 302 就能把请求（连同凭据）引到名单外的主机。
v0.9.21 给当时的 6 个出网点各加了 `allow_redirects=False`，v0.9.22 补上第 7 个
（`or_catalog` 的 `urlopen` —— 它之所以被漏，正因为**形态不同**）。
⇒ 但「各加一遍」意味着**第 8 个出网点默认无禁令** ⇒ 本文件把它变成结构性的。

## ⚠️⚠️ 判据必须是「值为**字面 `False`**」，不是「出现了这个参数」
初版方案写的是「必须**显式声明**重定向策略」—— **两个独立评审都判它没有判别力**，
执行者复跑坐实：那个判据对 `allow_redirects=True` 与 `allow_redirects=flag`（变量）
**两个 mutant 全部放行**。而本片的安全价值全押这一条 ⇒ 判据必须硬到能区分它们。

## ⚠️ 为什么是**两级并存**，而不是「下沉到调用级」
初版方案写「判据下沉到调用级」—— **错的一半**（实测）：
`httpx` / `urllib3` / `http.client` 的惯用形态是**实例方法**（`httpx.Client().post(...)`）
⇒ 「模块名.verb」这种调用级判据对它们**结构上认不出**，实测 0 命中。
⇒ 必须两级：
- **import 级**（`test_no_second_http_client_in_http_adapter`，v0.9.22 已把它的作用域扩到 `knot/`）
  管「**换库**」这一整类 —— 也顺带管住 `getattr` / 变量间接 / `functools.partial` / `Session()`
  这些逃逸写法，因为它们**都需要本文件先 import 那个库**；
- **本文件（调用 + 值级）** 管「参数被改成 `True` / 变量 / 漏写」。

## ⚠️ 参数名**按库映射**，不能一个集合通吃
实测：在 `httpx` 上写 `allow_redirects`（而非 `follow_redirects`）会让「强判据」也放行
—— 因为它根本不是 httpx 的参数名，httpx 会**默认跟随**。
⇒ 映射表见 `_REDIRECT_KWARG`。**本片 import 级已禁 httpx/urllib3**
⇒ 该映射是为将来解禁时准备的；写在这里以免那天有人只加库、不加映射。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]

#: 库 → 它的「禁跟随重定向」参数名。⚠️ 一个集合通吃会漏（见 docstring）。
_REDIRECT_KWARG = {
    "requests": "allow_redirects",
    "httpx": "follow_redirects",
    "urllib3": "redirect",
}

#: 会发请求的动词。
_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}

#: ⭐ **文件白名单，不是目录排除**（`tests/` 整体排除会成为逃逸口：
#: 把出网代码写进 `tests/` 下的 helper 再被生产码 import。今天 `knot/` import `tests/` = 0 处，
#: 由 `test_production_code_never_imports_tests` 守住）。
#: 这些是**差分测**：它们需要**独立于生产实现**的发送方式当 oracle
#: （用生产的封装去测生产的封装 = 用被测对象自证）。
_ALLOWED_TEST_FILES = {
    "tests/adapters/test_url_canon_single_parser.py",
    "tests/test_outbound_redirect_policy.py",
}


def _aliases(tree: ast.AST) -> dict[str, str]:
    """本地名 → 上游库名（含 `import requests as _rq` 这种别名）。

    ⚠️ **必须解析别名** —— 上一片的探针就是漏了 `_rq` 才把作业面数错
    （而 `datasources.py:72` 恰好就是那个形态）。
    """
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                root = a.name.split(".")[0]
                if root in _REDIRECT_KWARG:
                    out[a.asname or root] = root
        elif isinstance(n, ast.ImportFrom) and n.module:
            root = n.module.split(".")[0]
            if root in _REDIRECT_KWARG:
                for a in n.names:
                    out[a.asname or a.name] = root
    return out


def _outbound_calls(path: pathlib.Path):
    """→ [(lineno, 库名, 动词, 该调用的 keywords)]（只认**模块属性**形态的发送调用）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    alias = _aliases(tree)
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        v = n.func.value
        if not isinstance(v, ast.Name) or v.id not in alias:
            continue
        if n.func.attr not in _VERBS:
            continue                     # ⚠️ `requests.Request(...)` 不是发送 ⇒ 不算（v0.9.21 立的区分）
        hits.append((n.lineno, alias[v.id], n.func.attr, n.keywords))
    return hits


def test_every_outbound_call_bans_redirects_with_a_literal_false():
    """⭐⭐ 每个出网调用都必须带**字面 `False`** 的禁跟随参数。

    ⚠️ **不是「带了这个参数」** —— 实测那种弱判据对 `=True` 与 `=变量` 全部放行。
    ⚠️ **参数名按库取**（见 `_REDIRECT_KWARG`）。

    revert-to-bad（三种，都应红）：
      ① 任一处 `allow_redirects=False` → `True`；
      ② 改成变量 `allow_redirects=flag`；
      ③ 整个参数删掉。
    绝不该红：`requests.Request(...).prepare()`（不是发送）· `from requests.exceptions import ...`。
    """
    offenders = []
    for py in sorted((_REPO / "knot").rglob("*.py")):
        for lineno, lib, verb, kws in _outbound_calls(py):
            want = _REDIRECT_KWARG[lib]
            kw = next((k for k in kws if k.arg == want), None)
            rel = py.relative_to(_REPO)
            if kw is None:
                offenders.append(f"{rel}:{lineno} {lib}.{verb}() **缺** {want}=False")
            elif not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                shown = ast.unparse(kw.value)
                offenders.append(f"{rel}:{lineno} {lib}.{verb}() 的 {want}={shown}（**必须是字面 False**）")
    assert not offenders, (
        "出网调用未禁跟随重定向：\n  " + "\n  ".join(offenders)
        + "\n\n出网 allowlist **只管第一跳** —— 目标回一个 302 就能把请求（连同凭据）"
          "引到名单外的主机。\n"
          "⚠️ 值必须是**字面 `False`**：`True` / 变量 / 漏写都会让禁令失效，"
          "而其中两种**看起来像是声明过了**。"
    )


def test_urlopen_is_not_called_directly_anywhere():
    """⭐ 全仓禁直调 `urllib.request.urlopen` —— 它**默认跟随重定向**。

    唯一合法出口是 `or_catalog._OPENER`（装了 `_NoRedirect` handler 的 opener）。
    ⚠️ **为什么单列一条**：`urlopen` 不是「某个库的某个动词」，上面那条按
    `_REDIRECT_KWARG` 取参数名的判据**表示不了它**（它连那个参数都没有）
    —— 而这一处正是上一片**唯一被漏掉**的出网点，原因就是形态不同。

    revert-to-bad：把 `or_catalog` 改回 `urllib.request.urlopen(...)` ⇒ 本测红。
    """
    offenders = []
    for py in sorted((_REPO / "knot").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            name = None
            if isinstance(f, ast.Attribute) and f.attr == "urlopen":
                name = "urlopen"
            elif isinstance(f, ast.Name) and f.id == "urlopen":
                name = "urlopen"          # `from urllib.request import urlopen`
            if name:
                offenders.append(f"{py.relative_to(_REPO)}:{n.lineno}")
    assert not offenders, (
        "直调 `urlopen`（**默认跟随重定向**）：\n  " + "\n  ".join(offenders)
        + "\n\n⇒ 请走 `knot/api/admin/or_catalog._OPENER`（已装 `_NoRedirect`），"
          "或按需另建一个同形的 opener 并在此登记。"
    )


def test_url_canon_may_only_use_requests_for_parsing():
    """⭐ `url_canon.py` 里 `requests` 的属性**只允许 `Request`** —— 封死「白名单文件里 prepare-then-send」。

    ⚠️ **为什么需要这条**：该文件必须能 import `requests`（它用 `Request(...).prepare()` 算 host），
    而**文件级白名单等于把发送能力也给了它** —— `Session().send(prepared)` 是标准写法。
    ⇒ 判据下沉到**属性级**：只许 `Request`。
    ⭐ 实测该文件今天 `requests.*` 属性访问**只有 `Request` 一个** ⇒ 本条零假红。

    revert-to-bad：在该文件加 `requests.Session()` 或 `requests.get(...)` ⇒ 本测红。
    """
    path = _REPO / "knot" / "adapters" / "http" / "url_canon.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "requests"}
    assert used <= {"Request"}, (
        f"`url_canon.py` 用了 `requests` 的非解析属性 {sorted(used - {'Request'})} —— "
        "该文件只允许**解析**（`Request(...).prepare()`），不允许发送。\n"
        "⇒ 发送一律走各出网点自己那行（并带字面 `allow_redirects=False`）。"
    )


def test_production_code_never_imports_tests():
    """⭐ `knot/` 不得 import `tests/` —— 否则上面那份**测文件白名单**会变成逃逸口。

    ⚠️ 具体形状：把出网代码写进 `tests/` 下的 helper（在白名单里 ⇒ 不受禁令约束），
    再让生产码 import 它 ⇒ 禁令被绕过而三条哨兵全绿。
    ⭐ 实测今天 `knot/` import `tests/` = **0 处** ⇒ 本条零假红，纯预防。
    """
    offenders = []
    for py in sorted((_REPO / "knot").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods = [n.module]
            for m in mods:
                if m == "tests" or m.startswith("tests."):
                    offenders.append(f"{py.relative_to(_REPO)}:{n.lineno} {m}")
    assert not offenders, (
        "生产码 import 了 `tests/`：\n  " + "\n  ".join(offenders)
        + "\n\n⇒ 那会让出网哨兵的**测文件白名单**变成逃逸口。"
    )


def test_allowed_test_files_still_exist():
    """⭐ 白名单里的路径必须**真的存在** —— 否则它会静默变成一份过期清单。

    ⚠️ 本仓的教训：清单会漂，而漂掉的条目**不会让任何东西红**。
    """
    missing = [p for p in _ALLOWED_TEST_FILES if not (_REPO / p).exists()]
    assert not missing, (
        f"出网哨兵的测文件白名单里有**不存在的路径** {missing} —— "
        "它们要么被改名了、要么被删了。请同步，别留过期条目。"
    )


# ─── 行为级：`_OPENER` 真的不跟随 ────────────────────────────────────────


def _serve(handler_cls):
    """起一个真 HTTP 服务，返回 (base_url, 收到的路径 list, 关停函数)。"""
    import threading
    from http.server import HTTPServer

    received: list[str] = []
    handler_cls.received = received
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", received, srv.shutdown


def test_or_catalog_opener_does_not_follow_a_real_302(monkeypatch):
    """⭐⭐ 行为级证明：`or_catalog._OPENER` 撞到真 302 时**第二跳零发生**。

    上面三条哨兵都是**静态**的（AST）—— 它们能证明「代码里写着禁令」，
    **不能**证明「禁令真的生效」。这一条是唯一的行为级证据。

    ⚠️ **两个前提必须先自证，否则这条测是空的**：
    1. **清代理 env**（六问⑥第二形态 · v0.9.21 立）：有代理时第二个监听器**恒零收到**
       ⇒ 「零收到」变成对空集的断言，而它**看起来像证据**；
    2. **可达性正对照**：先证明「第二个监听器这会儿真收得到」，再断言它没收到。
    """
    from http.server import BaseHTTPRequestHandler

    from knot.api.admin.or_catalog import _OPENER

    for n in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
              "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(n, raising=False)

    class _Second(BaseHTTPRequestHandler):
        received: list[str] = []

        def do_GET(self):                                        # noqa: N802
            type(self).received.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"data": []}')

        def log_message(self, *a):                               # noqa: D102
            pass

    second, hits2, stop2 = _serve(_Second)

    class _First(BaseHTTPRequestHandler):
        received: list[str] = []

        def do_GET(self):                                        # noqa: N802
            type(self).received.append(self.path)
            self.send_response(302)
            self.send_header("Location", f"{second}/redirected")
            self.end_headers()

        def log_message(self, *a):                               # noqa: D102
            pass

    first, hits1, stop1 = _serve(_First)
    try:
        # ① 可达性正对照 —— 证明「第二个监听器真收得到」（否则下面的零断言是空的）
        _OPENER.open(f"{second}/reachable", timeout=5).read()
        assert hits2 == ["/reachable"], f"可达性正对照失败: {hits2} —— 本测的零断言不可信"
        hits2.clear()

        # ② 真 302 → **不得**到达第二跳
        # ⚠️⚠️ **刻意不用 `pytest.raises` 当主 oracle**（CLAUDE.md：安全属性是「什么没发生」，
        #    不是「抛了异常」）—— 实测坐实：换回默认 opener 时 `pytest.raises` 停在
        #    **DID NOT RAISE**，于是「第二跳零收到」这条**真属性的断言根本不执行**，
        #    失败消息也不会提到重定向。⇒ 先无条件断真属性，最后才断「有没有给出可诊断的错误」。
        import urllib.error
        raised = None
        try:
            _OPENER.open(f"{first}/start", timeout=5)
        except Exception as e:                                   # noqa: BLE001
            raised = e

        assert hits1 == ["/start"], f"第一跳应恰好收到一次: {hits1}"
        assert hits2 == [], (
            f"⛔ **跟随了重定向** —— 第二跳收到 {hits2}。"
            f"出网 allowlist 只管第一跳 ⇒ 目标回一个 302 就能把请求引到名单外的主机。"
        )
        assert isinstance(raised, urllib.error.HTTPError) and raised.code == 302, (
            f"零投递做到了，但没给出可诊断的错误（拿到 {raised!r}）—— "
            f"调用方会把「被拒」误当成「成功但空」。"
        )
    finally:
        stop1()
        stop2()
