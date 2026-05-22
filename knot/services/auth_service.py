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


def authenticate(username: str, password: str):
    user = get_user_by_username(username)
    if user and user["is_active"] and verify_password(password, user["password_hash"]):
        return user
    return None


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
