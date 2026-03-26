import logging
import os
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Callable

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from api.database import SessionLocal
from api.models import User

load_dotenv()
logger = logging.getLogger(__name__)

# Configuration
_env_secret = os.getenv("SECRET_KEY", "")
if not _env_secret:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "⚠️  SECRET_KEY 未在 .env 中设置，已自动生成临时密钥。"
        "重启后所有已签发的 Token 将失效。请在 .env 中配置 SECRET_KEY。"
    )
else:
    SECRET_KEY = _env_secret

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

PERMISSION_CLIENT_WRITE = "client_write"
PERMISSION_FEISHU_SYNC = "feishu_sync"
PERMISSION_BILLING_RUN = "billing_run"
BUSINESS_PERMISSIONS = (
    PERMISSION_CLIENT_WRITE,
    PERMISSION_FEISHU_SYNC,
    PERMISSION_BILLING_RUN,
)


def normalize_permissions(permissions: list[str] | None) -> list[str]:
    if not permissions:
        return []
    normalized = []
    seen = set()
    for item in permissions:
        value = str(item or "").strip().lower()
        if value in BUSINESS_PERMISSIONS and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def get_role_permissions(role: str | None, raw_permissions: str | None) -> list[str]:
    normalized_role = str(role or "user").strip().lower()
    if normalized_role in {"admin", "super_admin"}:
        return list(BUSINESS_PERMISSIONS)
    try:
        parsed = json.loads(raw_permissions or "[]")
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        parsed = []
    return normalize_permissions([str(item) for item in parsed])


def has_permission(current: Dict[str, Any], permission: str) -> bool:
    if current.get("role") in {"admin", "super_admin"}:
        return True
    return permission in set(current.get("permissions") or [])


def require_permission(permission: str) -> Callable:
    if permission not in BUSINESS_PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    async def _permission_guard(current: Dict[str, Any] = Depends(get_current_user_info)) -> Dict[str, Any]:
        if not has_permission(current, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return current

    return _permission_guard


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    return _decode_username_from_token(token)


def _decode_username_from_token(token: str) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username


async def get_current_user_info(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    username = _decode_username_from_token(token)
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role or "user",
            "permissions": get_role_permissions(user.role, getattr(user, "permissions", "[]")),
        }
    finally:
        db.close()


async def get_current_admin_user(current: Dict[str, Any] = Depends(get_current_user_info)) -> Dict[str, Any]:
    if current.get("role") not in {"admin", "super_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permission required")
    return current


async def get_current_super_admin_user(current: Dict[str, Any] = Depends(get_current_user_info)) -> Dict[str, Any]:
    if current.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin permission required")
    return current
