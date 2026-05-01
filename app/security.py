import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

# Hash cố định cho nhánh user không tồn tại (chi phí bcrypt tương tự).
_DUMMY_PLAIN = b"___qcmaster_login_timing_dummy___"
DUMMY_PASSWORD_HASH: bytes = bcrypt.hashpw(_DUMMY_PLAIN, bcrypt.gensalt(rounds=12))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, password_hash: str | None) -> bool:
    if not password_hash or not isinstance(password_hash, str):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


def verify_dummy(plain: str) -> None:
    bcrypt.checkpw(plain.encode("utf-8"), DUMMY_PASSWORD_HASH)


def create_access_token(*, user_id: str, role: str) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=settings.access_token_expire_seconds)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(*, user_id: str) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=settings.refresh_token_expire_seconds)
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": jti,
        "exp": int(exp.timestamp()),
        "typ": "refresh",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, jti


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def decode_refresh_token(token: str, *, verify_exp: bool = True) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if not verify_exp:
        options["verify_exp"] = False
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        options=options,
    )
