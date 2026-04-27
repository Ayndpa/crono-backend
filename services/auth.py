import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from services.database import get_db

# ── 配置 ──────────────────────────────────────────────
SECRET_KEY = "cronos-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


# ── 密码工具 ──────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT 工具 ──────────────────────────────────────────
def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


# ── 数据库操作 ────────────────────────────────────────
def get_user_by_username(db: sqlite3.Connection, username: str) -> Optional[dict]:
    row = db.execute(
        "SELECT id, username, hashed_password FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def create_user(db: sqlite3.Connection, username: str, password: str) -> dict:
    hashed = hash_password(password)
    cursor = db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (username, hashed),
    )
    db.commit()
    return {"id": cursor.lastrowid, "username": username}


# ── FastAPI 依赖：获取当前登录用户 ────────────────────
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
        )
    payload = decode_token(credentials.credentials)
    user_id = int(payload["sub"])
    row = db.execute(
        "SELECT id, username FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return dict(row)
