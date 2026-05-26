import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import PERMISSION_BILLING_RUN, require_permission
from api.database import get_db, record_operation_audit
from api.services.bank_reconciliation_service import BankReconciliationService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bank-reconciliation", tags=["bank-reconciliation"])
service = BankReconciliationService()


class ManualMatchRequest(BaseModel):
    bank_source_id: str
    ledger_source_id: str


@router.post("/reconcile")
async def reconcile_bank_statement(
    month: str | None = Form(default=None),
    company: str | None = Form(default=None),
    bank_file: UploadFile = File(...),
    ledger_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    actor = str(current_user.get("username") or "system")
    try:
        result = await service.reconcile_uploads(
            month=month,
            company=company,
            bank_file=bank_file,
            ledger_file=ledger_file,
            actor=actor,
            db=db,
        )
        record_operation_audit(
            category="bank_reconciliation",
            action="reconcile",
            actor=actor,
            status="success",
            input_file=f"{bank_file.filename or ''}; {ledger_file.filename or ''}",
            result_ref=str(result.get("batch_no") or result.get("id") or ""),
            metadata={
                "month": result.get("month"),
                "company": result.get("company"),
                "matched_count": (result.get("summary") or {}).get("matched_count"),
                "difference_count": (result.get("summary") or {}).get("difference_count"),
            },
        )
        return result
    except HTTPException as exc:
        record_operation_audit(
            category="bank_reconciliation",
            action="reconcile",
            actor=actor,
            status="failed",
            input_file=f"{bank_file.filename or ''}; {ledger_file.filename or ''}",
            error_message=str(exc.detail),
            metadata={"month": month, "company": company},
        )
        raise
    except Exception as exc:
        logger.exception("Failed to reconcile bank statement")
        record_operation_audit(
            category="bank_reconciliation",
            action="reconcile",
            actor=actor,
            status="failed",
            input_file=f"{bank_file.filename or ''}; {ledger_file.filename or ''}",
            error_message=str(exc),
            metadata={"month": month, "company": company},
        )
        raise HTTPException(status_code=500, detail=f"银行对账失败: {exc}") from exc


@router.get("/companies")
def list_bank_reconciliation_companies(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    from api.models import BankReconciliationBatch
    rows = db.query(BankReconciliationBatch.company).filter(
        BankReconciliationBatch.company.isnot(None), 
        BankReconciliationBatch.company != ""
    ).distinct().all()
    # Also fetch from clients entity to populate options
    from api.models import Client
    client_entities = db.query(Client.entity).filter(
        Client.entity.isnot(None), 
        Client.entity != ""
    ).distinct().all()
    
    companies = sorted(list({r[0] for r in rows} | {r[0] for r in client_entities}))
    return {"companies": companies}


@router.get("/batches")
def list_bank_reconciliation_batches(
    limit: int = Query(20, ge=1, le=100),
    month: str | None = Query(None),
    company: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    return service.list_batches(limit=limit, month=month, company=company, db=db)


@router.get("/batches/{batch_id}")
def get_bank_reconciliation_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    return service.get_batch(batch_id, db=db)


@router.post("/batches/{batch_id}/manual-match")
def manual_match_bank_reconciliation_batch(
    batch_id: int,
    payload: ManualMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    actor = str(current_user.get("username") or "system")
    try:
        result = service.manual_match(
            batch_id=batch_id,
            bank_source_id=payload.bank_source_id,
            ledger_source_id=payload.ledger_source_id,
            actor=actor,
            db=db,
        )
        record_operation_audit(
            category="bank_reconciliation",
            action="manual_match",
            actor=actor,
            status="success",
            result_ref=str(batch_id),
            metadata={
                "bank_source_id": payload.bank_source_id,
                "ledger_source_id": payload.ledger_source_id,
            },
        )
        return result
    except HTTPException as exc:
        record_operation_audit(
            category="bank_reconciliation",
            action="manual_match",
            actor=actor,
            status="failed",
            result_ref=str(batch_id),
            error_message=str(exc.detail),
            metadata={
                "bank_source_id": payload.bank_source_id,
                "ledger_source_id": payload.ledger_source_id,
            },
        )
        raise
    except Exception as exc:
        logger.exception("Failed to manually match bank reconciliation rows")
        record_operation_audit(
            category="bank_reconciliation",
            action="manual_match",
            actor=actor,
            status="failed",
            result_ref=str(batch_id),
            error_message=str(exc),
            metadata={
                "bank_source_id": payload.bank_source_id,
                "ledger_source_id": payload.ledger_source_id,
            },
        )
        raise HTTPException(status_code=500, detail=f"银行对账人工匹配失败: {exc}") from exc


@router.get("/batches/{batch_id}/download")
def download_bank_reconciliation_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    actor = str(current_user.get("username") or "system")
    try:
        buffer, filename = service.build_report(batch_id, db=db)
        record_operation_audit(
            category="bank_reconciliation",
            action="export_report",
            actor=actor,
            status="success",
            output_file=filename,
            result_ref=str(batch_id),
        )
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": service.content_disposition(filename)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to export bank reconciliation report")
        record_operation_audit(
            category="bank_reconciliation",
            action="export_report",
            actor=actor,
            status="failed",
            result_ref=str(batch_id),
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"银行对账结果下载失败: {exc}") from exc
