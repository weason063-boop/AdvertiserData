from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import (
    PERMISSION_BILLING_RUN,
    get_current_user,
    require_permission,
)
from api.services.daily_fx_snapshot_service import DailyFxSnapshotService
from api.services.exchange_rate_service import ExchangeRateService

router = APIRouter(prefix="/api/exchange-rates", tags=["exchange-rates"])
service = ExchangeRateService()
daily_fx_service = DailyFxSnapshotService()


class DailySnapshotUpsertRequest(BaseModel):
    cny_tt_buy: float = Field(..., gt=0)
    eur_tt_buy: float = Field(..., gt=0)
    usd_tt_sell: float = Field(..., gt=0)
    jpy_tt_sell: float = Field(..., gt=0)
    usd_tt_buy: float = Field(..., gt=0)


@router.get("")
def get_rates(current_user: str = Depends(get_current_user)):
    """
    汇率页只读接口。
    数据来源：手工维护的日快照。
    """
    data = service.get_current_rates()
    snapshot_payload = daily_fx_service.get_today_snapshot_payload()
    return {
        "rates": data,
        "snapshot": snapshot_payload,
    }


@router.get("/daily-snapshot")
def get_daily_snapshot(current_user: str = Depends(get_current_user)):
    return daily_fx_service.get_today_snapshot_payload()


@router.get("/daily-snapshots")
def get_daily_snapshots(
    limit: int = Query(default=14, ge=1, le=90),
    current_user: str = Depends(get_current_user),
):
    return {"items": daily_fx_service.list_snapshots(limit)}


@router.put("/daily-snapshots/{rate_date}")
def upsert_daily_snapshot(
    rate_date: str,
    payload: DailySnapshotUpsertRequest,
    current_user: dict = Depends(require_permission(PERMISSION_BILLING_RUN)),
):
    try:
        snapshot = daily_fx_service.upsert_snapshot(
            rate_date=rate_date,
            cny_tt_buy=payload.cny_tt_buy,
            eur_tt_buy=payload.eur_tt_buy,
            usd_tt_sell=payload.usd_tt_sell,
            jpy_tt_sell=payload.jpy_tt_sell,
            usd_tt_buy=payload.usd_tt_buy,
            actor=str(current_user.get("username") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "snapshot": snapshot}
