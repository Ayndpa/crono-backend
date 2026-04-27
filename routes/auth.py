import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from models.user import UserRegister, UserLogin, TokenResponse, UserResponse
from services.auth import (
    get_user_by_username,
    create_user,
    verify_password,
    create_access_token,
    get_current_user,
)
from services.config import ensure_user_defaults
from services.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: UserRegister, db: sqlite3.Connection = Depends(get_db)):
    if get_user_by_username(db, body.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = create_user(db, body.username, body.password)
    ensure_user_defaults(db, user["id"])
    token = create_access_token(user["id"], user["username"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=user["id"], username=user["username"]),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin, db: sqlite3.Connection = Depends(get_db)):
    user = get_user_by_username(db, body.username)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user["id"], user["username"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=user["id"], username=user["username"]),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(id=current_user["id"], username=current_user["username"])
