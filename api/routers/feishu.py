import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from api.auth import PERMISSION_FEISHU_SYNC, get_current_user, require_permission
from api.database import get_db, record_operation_audit
from api.services.receivable_sync_service import ReceivableSyncService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feishu", tags=["feishu"])
_EVENT_SYNC_LOCK = Lock()
_LAST_EVENT_SYNC_AT: datetime | None = None


@router.get("/receivables/summary")
def get_receivable_summary(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return ReceivableSyncService().get_summary(db)


@router.get("/receivables/bills")
def list_receivable_bills(
    status: str = Query("overdue", pattern="^(overdue|outstanding|all)$"),
    limit: int = Query(100, ge=1, le=500),
    client_name: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return {
        "status": status,
        "limit": limit,
        "client_name": client_name,
        "rows": ReceivableSyncService().list_bills(status=status, limit=limit, client_name=client_name, db=db),
    }


@router.get("/receivables/client-summary")
def get_receivable_client_summary(
    metric: str = Query("overdue", pattern="^(overdue|outstanding)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return ReceivableSyncService().get_client_summary(metric=metric, limit=limit, db=db)


@router.post("/receivables/sync")
def sync_receivables(current_user: dict = Depends(require_permission(PERMISSION_FEISHU_SYNC))):
    actor = str(current_user.get("username") or current_user.get("sub") or "system")
    service = ReceivableSyncService()
    try:
        result = service.sync_all()
        record_operation_audit(
            category="feishu",
            action="sync_receivables",
            actor=actor,
            status="success",
            metadata={
                "synced_records": result.get("synced_records"),
                "table_counts": result.get("table_counts"),
            },
        )
        return result
    except Exception as exc:
        logger.exception("Failed to sync Feishu receivables")
        record_operation_audit(
            category="feishu",
            action="sync_receivables",
            actor=actor,
            status="failed",
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"飞书应收/逾期同步失败: {exc}")


@router.post("/events")
async def handle_feishu_event(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    try:
        payload = _load_event_payload(raw_body, request)
        _verify_event_token(payload)

        challenge = _extract_challenge(payload)
        if challenge:
            return {"challenge": challenge}

        event_type = _extract_event_type(payload)
        background_tasks.add_task(_sync_receivables_from_event, payload)
        return {"code": 0, "msg": "accepted", "event_type": event_type}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to handle Feishu event")
        record_operation_audit(
            category="feishu",
            action="event_sync_receivables",
            actor="feishu_event",
            status="failed",
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"飞书事件处理失败: {exc}")


def _sync_receivables_from_event(payload: dict[str, Any]) -> None:
    global _LAST_EVENT_SYNC_AT
    event_type = _extract_event_type(payload)
    throttle_seconds = _event_sync_throttle_seconds()
    now = datetime.now()

    if _LAST_EVENT_SYNC_AT and (now - _LAST_EVENT_SYNC_AT).total_seconds() < throttle_seconds:
        record_operation_audit(
            category="feishu",
            action="event_sync_receivables",
            actor="feishu_event",
            status="skipped",
            metadata={
                "event_type": event_type,
                "reason": "throttled",
                "throttle_seconds": throttle_seconds,
            },
        )
        return

    if not _EVENT_SYNC_LOCK.acquire(blocking=False):
        record_operation_audit(
            category="feishu",
            action="event_sync_receivables",
            actor="feishu_event",
            status="skipped",
            metadata={
                "event_type": event_type,
                "reason": "sync_already_running",
            },
        )
        return

    _LAST_EVENT_SYNC_AT = now
    try:
        result = ReceivableSyncService().sync_all()
        record_operation_audit(
            category="feishu",
            action="event_sync_receivables",
            actor="feishu_event",
            status="success",
            metadata={
                "event_type": event_type,
                "synced_records": result.get("synced_records"),
            },
        )
    except Exception as exc:
        logger.exception("Failed to sync Feishu receivables from event")
        record_operation_audit(
            category="feishu",
            action="event_sync_receivables",
            actor="feishu_event",
            status="failed",
            error_message=str(exc),
            metadata={"event_type": event_type},
        )
    finally:
        _EVENT_SYNC_LOCK.release()


def _event_sync_throttle_seconds() -> int:
    try:
        return max(0, int(os.getenv("FEISHU_EVENT_SYNC_THROTTLE_SECONDS", "15")))
    except ValueError:
        return 15


def _load_event_payload(raw_body: bytes, request: Request) -> dict[str, Any]:
    _verify_event_signature(raw_body, request)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Feishu event JSON") from exc

    encrypted = payload.get("encrypt")
    if encrypted:
        encrypt_key = os.getenv("FEISHU_EVENT_ENCRYPT_KEY", "")
        if not encrypt_key:
            raise HTTPException(status_code=400, detail="Encrypted Feishu event received, but FEISHU_EVENT_ENCRYPT_KEY is not configured")
        decrypted_text = _decrypt_feishu_event(str(encrypted), encrypt_key)
        try:
            return json.loads(decrypted_text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid decrypted Feishu event JSON") from exc
    return payload


def _verify_event_signature(raw_body: bytes, request: Request) -> None:
    signature = request.headers.get("X-Lark-Signature")
    if not signature:
        return

    encrypt_key = os.getenv("FEISHU_EVENT_ENCRYPT_KEY", "")
    if not encrypt_key:
        raise HTTPException(status_code=403, detail="FEISHU_EVENT_ENCRYPT_KEY is required for signature verification")

    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    sign_source = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + raw_body
    expected = hashlib.sha256(sign_source).hexdigest()
    if not _constant_time_equal(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid Feishu event signature")


def _verify_event_token(payload: dict[str, Any]) -> None:
    expected_token = os.getenv("FEISHU_EVENT_VERIFICATION_TOKEN", "")
    if not expected_token and _allow_unverified_events():
        return
    if not expected_token:
        raise HTTPException(status_code=403, detail="FEISHU_EVENT_VERIFICATION_TOKEN is required")
    observed_token = (
        payload.get("token")
        or (payload.get("header") or {}).get("token")
        or (payload.get("event") or {}).get("token")
    )
    if str(observed_token or "") != expected_token:
        raise HTTPException(status_code=403, detail="Invalid Feishu event verification token")


def _allow_unverified_events() -> bool:
    if os.getenv("TESTING") == "True":
        return True
    return os.getenv("FEISHU_EVENT_ALLOW_UNVERIFIED", "").strip().lower() in {"1", "true", "yes"}


def _extract_challenge(payload: dict[str, Any]) -> str | None:
    challenge = payload.get("challenge")
    if challenge:
        return str(challenge)
    event = payload.get("event")
    if isinstance(event, dict) and event.get("challenge"):
        return str(event.get("challenge"))
    return None


def _extract_event_type(payload: dict[str, Any]) -> str | None:
    header = payload.get("header")
    if isinstance(header, dict) and header.get("event_type"):
        return str(header.get("event_type"))
    if payload.get("type"):
        return str(payload.get("type"))
    return None


def _decrypt_feishu_event(encrypted_text: str, encrypt_key: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7
    except Exception as exc:
        raise HTTPException(status_code=500, detail="cryptography package is required to decrypt Feishu events") from exc

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    iv = key[:16]
    try:
        encrypted_bytes = base64.b64decode(encrypted_text)
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded_plain = decryptor.update(encrypted_bytes) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(padded_plain) + unpadder.finalize()
        return plain.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to decrypt Feishu event payload") from exc


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
