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
