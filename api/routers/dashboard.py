from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from api.database import get_db, record_operation_audit
from api.auth import PERMISSION_BILLING_RUN, get_current_user, require_permission
from api.services.dashboard_service import DashboardService
from api.services.dashboard_report_service import DashboardReportService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
service = DashboardService()
report_service = DashboardReportService()


@router.get("")
def get_dashboard_data(db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    """获取看板统计数据"""
    return service.get_main_stats(db)


@router.get("/export/report.xlsx")
def export_dashboard_report(
    period_type: str = Query(...),
    period: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    include_details: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    actor = str(current_user.get("username") or "system")
    metadata = {
        "period_type": period_type,
        "period": period,
        "limit": limit,
        "include_details": include_details,
    }
    try:
        file_buffer, filename = report_service.build_report(
            period_type=period_type,
            period=period,
            limit=limit,
            include_details=include_details,
            db=db,
        )
        record_operation_audit(
            category="dashboard",
            action="export_report",
            actor=actor,
            status="success",
            output_file=filename,
            metadata=metadata,
        )
        return StreamingResponse(
            file_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException as exc:
        record_operation_audit(
            category="dashboard",
            action="export_report",
            actor=actor,
            status="failed",
            error_message=str(getattr(exc, "detail", exc)),
            metadata=metadata,
        )
        raise
    except Exception as exc:
        record_operation_audit(
            category="dashboard",
            action="export_report",
            actor=actor,
            status="failed",
            error_message=str(exc),
            metadata=metadata,
        )
        raise HTTPException(status_code=500, detail=f"报表导出失败: {exc}")


@router.get("/client/{client_name}/trend")
def get_client_trend_data(
    client_name: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """获取指定客户的月度消耗趋势"""
    try:
        return service.get_client_trend(client_name, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights")
def get_insights_data(db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    """获取仪表盘洞察数据"""
    try:
        return service.get_insights(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/month/{month}/top-clients")
def get_month_top_clients(
    month: str,
    limit: int = 10,
    compare_prev: bool = False,
    compare_mode: str | None = Query(default=None, pattern="^(none|mom|yoy|dual)$"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """获取指定月份的 TOP 客户数据"""
    try:
        return service.get_month_top_clients(
            month,
            limit,
            db,
            compare_prev=compare_prev,
            compare_mode=compare_mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quarter/{quarter}/top-clients")
def get_quarter_top_clients(
    quarter: str,
    limit: int = 10,
    compare_prev: bool = False,
    compare_mode: str | None = Query(default=None, pattern="^(none|qoq|yoy|dual)$"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """获取指定季度的 TOP 客户数据（Q4=12月至次年2月）"""
    try:
        return service.get_quarter_top_clients(
            quarter,
            limit,
            db,
            compare_prev=compare_prev,
            compare_mode=compare_mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
