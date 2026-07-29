"""auth_utils — password hashing & lookup-by-username helper.

v0.3.0: import 重写为 absolute（knot.repositories.user_repo）。
v0.3.1 计划：本文件内容并入 services/auth_service。
import-linter exception: core 暂保留对 repositories 的 import；v0.3.1 上移至 services。
"""
import bcrypt

from knot.repositories.user_repo import get_user_by_username


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# v0.9.4 D4'-b：常量时间对齐用的假 hash（**懒建 + 进程内缓存**）。
# 懒建而非模块级常量：① 不给启动期加一次 bcrypt（默认 cost 12 约 0.25s）；
# ② 用**当前 bcrypt 默认 rounds** 生成 ⇒ 将来 bcrypt 提高默认 cost 时，假 hash 与真用户 hash
#    自动同步变贵，耗时对齐不会悄悄失效（硬编一个 `$2b$12$...` 字面就会失效）。
_dummy_hash: list = []


def consume_password_time(password: str) -> None:
    """对一个固定假 hash 跑**一次** bcrypt —— 抹平「租户/用户不存在」与「口令错」的耗时差。

    ⭐ **为什么必须显式做**（R4 实测）：`authenticate` 原本是短路 `and` ⇒ 五个失败分支
    （代号不存在 / 租户停用 / 用户不存在 / 用户停用 / 口令错）里**只有最后一支跑 bcrypt**。
    统一错误文案只堵住了「读得到的差异」，**耗时差异仍是可测的旁路**：攻击者据此判断
    「这个公司代号存在吗」「这个用户名存在吗」= 公司/账号枚举。
    故非口令分支须各补一次 bcrypt。
    """
    if not _dummy_hash:
        _dummy_hash.append(hash_password("timing-alignment-only-never-a-real-password"))
    verify_password(password, _dummy_hash[0])


def authenticate_with_reason(username: str, password: str) -> tuple:
    """→ `(user | None, reason | None)`；**每条失败分支恰跑一次 bcrypt**（D4'-b）。

    `reason` 仅供审计/日志区分，**绝不进 HTTP 响应**（进了就是账号枚举）。
    调用方须把所有失败折成同一句「账号或密码错误」+ 同一状态码。
    """
    user = get_user_by_username(username)
    if user is None:
        consume_password_time(password)          # 分支③：用户不存在
        return None, "user_not_found"
    if not user["is_active"]:
        consume_password_time(password)          # 分支④：用户已停用
        return None, "user_inactive"
    if not verify_password(password, user["password_hash"]):
        return None, "bad_password"              # 分支⑤：bcrypt 已在此跑过
    return user, None


def authenticate(username: str, password: str):
    """薄封装（保留原签名/语义供其它调用方）—— 实现走 `authenticate_with_reason`，
    以免「常量时间」只在登录端点成立、别处又退回短路。"""
    user, _ = authenticate_with_reason(username, password)
    return user


# v0.6.0.20 admin 强制改密 — 红线（CLAUDE.md R-FCPW-* 候选）
_MIN_NEW_PASSWORD_LEN = 8
_FORBIDDEN_PASSWORDS = frozenset({"admin123"})  # 默认值禁复用


def change_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    """v0.6.0.20 用户修改密码 + 解除 must_change_password 守护。

    业务规则：
    - 旧密码必须匹配（防 token 持有人冒名改密）
    - 新密码 ≥ 8 字符（与 README 部署文档一致）
    - 新密码不在禁用列表（admin123 等默认值禁复用）
    - 新密码不能等于旧密码（防 "改了等于没改"）

    Args:
        user_id: 当前登录用户 ID
        old_password: 旧密码明文
        new_password: 新密码明文

    Returns:
        (success, message)；失败时 message 是用户可读理由（前端可展）
    """
    from knot.repositories import user_repo
    user = user_repo.get_user_by_id(user_id)
    if not user:
        return False, "用户不存在"
    if not verify_password(old_password, user["password_hash"]):
        return False, "旧密码错误"
    if len(new_password) < _MIN_NEW_PASSWORD_LEN:
        return False, f"新密码至少 {_MIN_NEW_PASSWORD_LEN} 字符"
    if new_password in _FORBIDDEN_PASSWORDS:
        return False, "新密码不能使用系统默认值"
    if new_password == old_password:
        return False, "新密码不能与旧密码相同"
    user_repo.update_user(user_id, password_hash=hash_password(new_password), must_change_password=0)
    return True, "密码修改成功"
