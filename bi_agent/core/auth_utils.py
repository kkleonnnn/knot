import bcrypt
import persistence


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def authenticate(username: str, password: str):
    user = persistence.get_user_by_username(username)
    if user and user["is_active"] and verify_password(password, user["password_hash"]):
        return user
    return None
