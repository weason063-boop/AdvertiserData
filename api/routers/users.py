import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import (
    BUSINESS_PERMISSIONS,
    get_current_super_admin_user,
    get_password_hash,
    get_role_permissions,
    normalize_permissions,
)
from api.database import get_db
from api.models import User

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="user")
    permissions: list[str] = Field(default_factory=list)


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_super_admin_user),
):
    users = db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role or "user",
                "permissions": get_role_permissions(u.role, getattr(u, "permissions", "[]")),
                "created_at": u.created_at,
            }
            for u in users
        ]
    }


@router.post("")
def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_super_admin_user),
):
    username = request.username.strip()
    role = (request.role or "user").strip().lower()
    if role not in {"user", "admin", "super_admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="Username already exists")

    if role in {"admin", "super_admin"}:
        permissions = list(BUSINESS_PERMISSIONS)
    else:
        permissions = normalize_permissions(request.permissions)

    new_user = User(
        username=username,
        password_hash=get_password_hash(request.password),
        role=role,
        permissions=json.dumps(permissions, ensure_ascii=False),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "status": "ok",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "role": new_user.role or "user",
            "permissions": get_role_permissions(new_user.role, new_user.permissions),
            "created_at": new_user.created_at,
        },
    }


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_super_admin_user),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.username == current_user.get("username"):
        raise HTTPException(status_code=400, detail="Cannot delete current login account")

    target_role = target.role or "user"
    if target_role == "super_admin":
        super_admin_count = db.query(User).filter(User.role == "super_admin").count()
        if super_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last super admin")

    db.delete(target)
    db.commit()
    return {"status": "ok", "message": "User deleted"}
