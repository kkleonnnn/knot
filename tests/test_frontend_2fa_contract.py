"""v0.6.5.2 — 前端 2FA API 契约源码守护（防 C1/C2/F3 false-green 回归）.

⚠️ 方法说明（执行者向守护者明示的 plan §4-test6 偏离）：
本测试（v0.6.5.2 hotfix 期）取「调用形状断言」：用源码断言守护契约形状
（同 test_totp_2fa.py::test_R_PB_B1_12_service_layer_uses_valid_window 的 grep-source 范式）。
当时前端零 JS 测试框架，引入 vitest 对安全 hotfix 属显著 scope 扩张。守护者 Stage 3 条件明确允许
「前端调用形状断言 *或* e2e」。关键价值：既有后端 TestClient verify 测试用 body 已绿，
*无法* 捕获前端发 header 的 C1 bug。

📌 v0.7.43（B5.1）更新：早期「node_modules 符号链接到主仓」顾虑已消失（现为真实独立目录）；
vitest 已引入并接入 CI（frontend-lint job + npm run test）。挂账的「完整 vitest 行为套件」已落地：
`frontend/src/api.test.js` 覆盖 normalizeDetail **6** 分支（旧述「5 例」少计 {message} + catch 兜底）。
本源码-grep 守护**仍保留**：它守 api.js verify/reset 的 **header 形状**（C1 bug 维度），
vitest 的 normalizeDetail 行为测试**未覆盖该维度** → 二者互补，非替代。渲染测试留 phase 2。
"""
from pathlib import Path

_FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"


def _read(rel: str) -> str:
    return (_FRONTEND_SRC / rel).read_text(encoding="utf-8")


def test_C1_verify_sends_interim_token_in_body():
    """C1：api.js verify 必须把 interim_token 放 body（非 Authorization header）。

    旧 bug：放 header → verify 端点无 get_current_user 不读 header → Pydantic 422 →
    已 enrolled 用户全员登录第二步卡死。后端契约要求 interim_token 在 body。
    """
    src = _read("api.js")
    # v0.9.4 step 8/9：verify 由自写裸 fetch 改为委托 `reqPublic`（去重）⇒ 哨兵**跟着搬**：
    # 「不带 Authorization」的决策现在落在 reqPublic 里。若只核 verify 段，本哨兵覆盖面会
    # **静默缩小** —— 有人在 reqPublic 里加回 Authorization，422 锁死全员登录的 bug 就复发而哨兵仍绿
    #（v0.9.3 教训「修实例不修机制」的同一形状）。
    assert "verify: (code, interimToken) =>" in src, \
        "C1：verify 定义形状变了 —— 哨兵目标集失效，须同步本测（勿直接删断言）"
    verify_seg = src.split("verify: (code, interimToken) =>", 1)[1].split("reset:", 1)[0]
    assert "interim_token: interimToken" in verify_seg, \
        "C1：verify body 必须含 interim_token（TotpVerifyRequest 必填字段）"
    assert "_hWith(interimToken)" not in verify_seg, \
        "C1：verify 严禁把 interim_token 放 Authorization header（致 422 锁死全员登录）"

    # ⭐ 跟到 reqPublic：它是 verify 实际发请求的地方，必须**不带 Authorization**
    assert "async reqPublic(method, path, body)" in src, \
        "C1：reqPublic 不存在 —— verify 的委托对象变了，哨兵须同步"
    pub_seg = src.split("async reqPublic(method, path, body)", 1)[1].split("get:", 1)[0]
    for forbidden in ("Authorization", "_h()", "_hWith", "_token()"):
        assert forbidden not in pub_seg, \
            f"C1：reqPublic 严禁带凭据（命中 {forbidden!r}）—— 它服务 login/totp.verify 两个登录流程端点：" \
            f"带 Authorization 会让 verify 回到 422 锁死全员登录，且让陈旧 token 参与登录（v0.9.4 B-5）"


def test_C2_reset_uses_target_user_id():
    """C2：api.js reset 必须用 target_user_id 字段名（非 user_id）。

    旧 bug：发 user_id → TotpResetRequest 要 target_user_id → 422 → admin 无法救援。
    """
    src = _read("api.js")
    assert "target_user_id: userId" in src, \
        "C2：reset 必须发 target_user_id（TotpResetRequest 字段名）"
    assert "{ user_id: userId }" not in src, \
        "C2：reset 严禁发 user_id（致 422，admin 无法为被锁用户重置 2FA）"


def test_F3_normalizeDetail_string_identity_first():
    """F3：normalizeDetail 必须首先对 string 原样返回（identity，零变换）。

    保 isEnrollErr（err.detail === 'totp_enroll_required'）等字面比较不断裂。
    """
    src = _read("api.js")
    assert "export function normalizeDetail" in src
    seg = src.split("export function normalizeDetail", 1)[1].split("export const api", 1)[0]
    # string identity 分支必须存在且在函数体最前（第一个 return 即 string 原样）
    assert "if (typeof detail === 'string') return detail" in seg, \
        "F3：normalizeDetail 必须含 string identity 分支（零变换）"
    first_return = seg.index("return detail")
    # identity 之前不应有任何其它 return（确保 string 最先短路）
    assert "return" not in seg[:first_return], \
        "F3：string identity 必须是第一个 return（不被其它分支抢先变换）"
    assert "Array.isArray(detail)" in seg, "F3：须处理 422 Array（各 msg 拼接）"


def test_F3_err_detail_normalized_in_req_and_verify():
    """F3：req() + verify 两处错误路径都须经 normalizeDetail（err.detail 恒 string）。"""
    src = _read("api.js")
    assert src.count("normalizeDetail(") >= 2, \
        "F3：req() 与 verify 两处都须走 normalizeDetail（err.detail 恒 string 防 React #31）"


def test_F3_gate_literal_preserved_in_app():
    """F3：isEnrollErr 的 gate 字面 'totp_enroll_required' 在 App.jsx 保留（identity 守护它）。"""
    app_src = _read("App.jsx")
    assert "'totp_enroll_required'" in app_src, \
        "F3：isEnrollErr 须比较 err.detail === 'totp_enroll_required'（normalizeDetail identity 保它）"


# ─── v0.9.4 MF9（守护者 Stage 4）：401 风暴路径的两条源码守护 ──────────────


def test_MF9_sse_401_is_wired_to_the_single_handler():
    """⭐ SSE 的 401 **接线**必须存在（此前只测了两端、没测接上没有）。

    v0.9.4 会把所有人的存量 token 一次性 401（判别式是 tid 有无）。若 SSE 这条路径不接
    `handleUnauthorized`，流式查询的用户既不会被登出、也只看到一条看不懂的错误。
    我 step 9 的 vitest 覆盖了「handler 产出带 status 的错误」与「handleUnauthorized 本体」**两端**，
    但**没有**任何测断言 `Chat.jsx` 真的把二者接上 —— 守护者 MF9 指出的正是这个缺口。
    （Chat.jsx 是大组件、无 React 测试脚手架 ⇒ 取源码守护；与 C1 系列同一手法。）
    """
    src = _read("screens/Chat.jsx")
    assert "handleUnauthorized" in src, "Chat.jsx 未引用 handleUnauthorized —— SSE 401 无处置"
    # 接线形状：识别 401 → 调单一处置。允许写法微调，但两者必须出现在同一行附近。
    lines = src.splitlines()
    wired = any(
        "401" in ln and "handleUnauthorized" in ln
        for ln in lines
    ) or any(
        "401" in lines[i] and "handleUnauthorized" in lines[i + 1]
        for i in range(len(lines) - 1)
    )
    assert wired, "Chat.jsx 里 401 判断与 handleUnauthorized 未接上（SSE 会话失效将无声无息）"


def test_MF9_no_bare_authorized_fetch_outside_the_single_entry():
    """⭐ 带 `Authorization` 的裸 `fetch(` 只允许出现在**三个**文件里。

    `api.req`（JSON）覆盖不到文件上传 / blob 下载 / 导出，于是全仓曾有 9 处各自手拼
    `Authorization` 且**没有一处处置 401** ⇒ v0.9.4 的一次性 401 时刻，这些路径的用户
    既不登出也不知所以（与 `api.req` 那条行为分裂）。已收敛到 `api.fetchAuthed`。

    允许的三处及理由：
    - `api.js` —— `fetchAuthed` / `req` 本体（唯一入口）
    - `screens/chat/sse_handler.js` —— SSE 必须用裸 fetch 读流；R-118 要求它是纯函数、
      **不得**自己处置，故由上层（`Chat.jsx`）接 `handleUnauthorized`（见上一条测）
    - `error_reporter.js` —— **刻意豁免**：它自己就是错误上报通道，401 时触发清会话+重载
      会造成「上报→重载→再上报」循环；telemetry 静默失败是正确行为
    """
    allowed = {"api.js", "screens/chat/sse_handler.js", "error_reporter.js"}
    bad = []
    for py in sorted(_FRONTEND_SRC.rglob("*.js")) + sorted(_FRONTEND_SRC.rglob("*.jsx")):
        rel = str(py.relative_to(_FRONTEND_SRC))
        if rel in allowed:
            continue
        text = py.read_text(encoding="utf-8")
        for i, ln in enumerate(text.splitlines(), 1):
            if "fetch(" in ln and "fetchAuthed(" not in ln and "Authorization" in ln:
                bad.append(f"{rel}:{i}: {ln.strip()[:80]}")
        # 多行形态：fetch( 与 Authorization 分行
        chunks = text.split("fetch(")
        for k, ch in enumerate(chunks[1:], 1):
            head = ch[:220]
            if "Authorization" in head and not chunks[k - 1].rstrip().endswith("Authed"):
                marker = f"{rel}:~{text[:text.index('fetch(') + 1].count(chr(10)) + 1}"
                if not any(b.startswith(rel) for b in bad):
                    bad.append(f"{marker}（多行形态，含 Authorization）")
    assert not bad, (
        "发现带 Authorization 的裸 fetch —— 它绕过 401 单一处置，"
        "v0.9.4 一次性 401 时该路径既不登出也不提示：\n  " + "\n  ".join(bad)
        + "\n改用 `fetchAuthed(url, opts)`（api.js）。"
    )
