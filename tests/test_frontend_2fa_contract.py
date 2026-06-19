"""v0.6.5.2 — 前端 2FA API 契约源码守护（防 C1/C2/F3 false-green 回归）.

⚠️ 方法说明（执行者向守护者明示的 plan §4-test6 偏离）：
前端当前零 JS 测试框架；node_modules 是符号链接到主仓 → 引入 vitest 会改主仓 node_modules
+ 需新增 CI 接线，对安全 hotfix 属显著 scope 扩张。守护者 Stage 3 条件明确允许
「前端调用形状断言 *或* e2e」—— 本测试取「调用形状断言」：用源码断言守护契约形状
（同 test_totp_2fa.py::test_R_PB_B1_12_service_layer_uses_valid_window 的 grep-source 范式）。
关键价值：既有后端 TestClient verify 测试用 body 已绿，*无法* 捕获前端发 header 的 C1 bug。
完整 vitest 行为套件（normalizeDetail 5 例 + 渲染不崩）留独立 chore PATCH（见 plan §6）。
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
    assert "async verify(code, interimToken)" in src
    # 提取 verify 函数段（到下一个 reset 方法）
    verify_seg = src.split("async verify(code, interimToken)", 1)[1].split("reset:", 1)[0]
    assert "interim_token: interimToken" in verify_seg, \
        "C1：verify body 必须含 interim_token（TotpVerifyRequest 必填字段）"
    assert "_hWith(interimToken)" not in verify_seg, \
        "C1：verify 严禁把 interim_token 放 Authorization header（致 422 锁死全员登录）"


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
