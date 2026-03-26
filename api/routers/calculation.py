import csv
from datetime import datetime, timedelta, timezone
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from api.auth import (
    PERMISSION_BILLING_RUN,
    PERMISSION_CLIENT_WRITE,
    get_current_admin_user,
    require_permission,
)
from api.database import list_operation_audit_logs
from api.services.calculation_service import CalculationService

router = APIRouter(prefix="/api", tags=["calculation"])
service = CalculationService()


@router.post("/calculate")
async def calculate_fees(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    try:
        owner_username = str(current_user.get("username") or "")
        file_path = await service.save_uploaded_file(file, owner_username=owner_username)
        return service.process_local_file(
            file_path,
            file.filename or "",
            owner_username=owner_username,
            operation="calculate",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"计算失败: {exc}")


@router.post("/recalculate")
def recalculate_fees(current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN))):
    try:
        return service.recalculate_latest(owner_username=str(current_user.get("username") or ""))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重算失败: {exc}")


@router.get("/latest-result")
def get_latest_result(current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN))):
    return service.get_latest_result_info_for_user(owner_username=str(current_user.get("username") or ""))


@router.get("/results/{result_id}")
def get_results_data(result_id: str, current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN))):
    return service.get_results_data(result_id, owner_username=str(current_user.get("username") or ""))


@router.get("/download/{result_id}")
def download_file(result_id: str, current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN))):
    file_path = service.get_download_path(result_id, owner_username=str(current_user.get("username") or ""))
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/upload-contract")
async def upload_contract(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    return await service.process_contract_upload(
        file,
        owner_username=str(current_user.get("username") or ""),
    )


@router.get("/task-history")
def get_task_history(
    limit: int = Query(default=100, ge=1, le=500),
    actor: str | None = Query(default=None),
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    status: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=365),
    current_user: dict = Depends(get_current_admin_user),
):
    created_after = None
    if days is not None:
        created_after = datetime.now(timezone.utc) - timedelta(days=days)
    items = list_operation_audit_logs(
        limit=limit,
        actor=None,
        actor_like=(actor or None),
        category=(category or None),
        action=(action or None),
        status=(status or None),
        created_after=created_after,
    )
    return {"items": items, "count": len(items)}


@router.get("/task-history/export")
def export_task_history(
    limit: int = Query(default=500, ge=1, le=500),
    actor: str | None = Query(default=None),
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    status: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=365),
    current_user: dict = Depends(get_current_admin_user),
):
    created_after = None
    if days is not None:
        created_after = datetime.now(timezone.utc) - timedelta(days=days)

    items = list_operation_audit_logs(
        limit=limit,
        actor=None,
        actor_like=(actor or None),
        category=(category or None),
        action=(action or None),
        status=(status or None),
        created_after=created_after,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "category", "action", "status", "actor", "input_file", "output_file", "result_ref", "error_message"])
    for item in items:
        writer.writerow(
            [
                item.get("id"),
                item.get("created_at"),
                item.get("category"),
                item.get("action"),
                item.get("status"),
                item.get("actor"),
                item.get("input_file"),
                item.get("output_file"),
                item.get("result_ref"),
                item.get("error_message"),
            ]
        )

    filename = f"task_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    payload = output.getvalue().encode("utf-8-sig")
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8", headers=headers)
