# -*- coding: utf-8 -*-
"""FastAPI backend service."""
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    BUSINESS_PERMISSIONS,
    create_access_token,
    get_password_hash,
    get_role_permissions,
    verify_password,
)
from api.database import (
    ensure_client_monthly_detail_stats_table,
    ensure_client_monthly_notes_table,
    SessionLocal,
    ensure_dashboard_indexes,
    ensure_operation_audit_table,
    ensure_user_permissions_column,
)
from api.models import User
from api.routers import calculation, clients, dashboard, exchange_rates, users

load_dotenv()
logger = logging.getLogger(__name__)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "weason")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize bootstrap super admin securely."""
    if os.getenv("TESTING") == "True":
        yield
        return

    db = SessionLocal()
    try:
        ensure_user_permissions_column()
        ensure_dashboard_indexes()
        ensure_client_monthly_detail_stats_table()
        ensure_client_monthly_notes_table()
        ensure_operation_audit_table()
        super_admin = db.query(User).filter(User.role == "super_admin").first()
        if not super_admin:
            if not ADMIN_PASSWORD:
                raise RuntimeError(
                    "No super_admin account found. Set ADMIN_USERNAME/ADMIN_PASSWORD in .env for first-time bootstrap."
                )

            bootstrap_user = db.query(User).filter(User.username == ADMIN_USERNAME).first()
            if bootstrap_user and bootstrap_user.role != "super_admin":
                raise RuntimeError(
                    f"Bootstrap user '{ADMIN_USERNAME}' exists but is not super_admin. "
                    "Promote it manually or choose another ADMIN_USERNAME."
                )

            if not bootstrap_user:
                bootstrap_user = User(
                    username=ADMIN_USERNAME,
                    password_hash=get_password_hash(ADMIN_PASSWORD),
                    role="super_admin",
                    permissions=json.dumps(list(BUSINESS_PERMISSIONS), ensure_ascii=False),
                )
                db.add(bootstrap_user)
                db.commit()
                logger.info("Bootstrap super_admin created: %s", ADMIN_USERNAME)
            else:
                bootstrap_user.password_hash = get_password_hash(ADMIN_PASSWORD)
                bootstrap_user.permissions = json.dumps(list(BUSINESS_PERMISSIONS), ensure_ascii=False)
                db.commit()
                logger.info("Bootstrap super_admin updated from env: %s", ADMIN_USERNAME)
    except Exception:
        logger.exception("Failed during startup bootstrap checks")
        raise
    finally:
        db.close()

    # FX sync is intentionally decoupled from API startup and should run via
    # scheduled script/manual trigger only.
    yield


app = FastAPI(title="合同条款管理系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == form_data.username).first()
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        permissions = get_role_permissions(user.role, getattr(user, "permissions", "[]"))
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role or "user", "permissions": permissions},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "username": user.username,
            "role": user.role or "user",
            "permissions": permissions,
        }
    finally:
        db.close()


app.include_router(dashboard.router)
app.include_router(clients.router)
app.include_router(calculation.router)
app.include_router(exchange_rates.router)
app.include_router(users.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
