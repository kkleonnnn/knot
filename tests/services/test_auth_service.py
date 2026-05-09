"""auth_service happy-path 单测。"""
from knot.services import auth_service


def test_hash_and_verify_roundtrip():
    h = auth_service.hash_password("Pa$$w0rd")
    assert auth_service.verify_password("Pa$$w0rd", h)
    assert not auth_service.verify_password("wrong", h)


def test_hash_returns_bcrypt_format():
    h = auth_service.hash_password("x")
    assert h.startswith("$2b$") or h.startswith("$2a$")


def test_verify_password_handles_bytes_correctly():
    """bcrypt 内部用 bytes，本接口 utf-8 包装；多语言密码也应工作。"""
    h = auth_service.hash_password("中文密码 🔑")
    assert auth_service.verify_password("中文密码 🔑", h)
    assert not auth_service.verify_password("中文密碼 🔑", h)
