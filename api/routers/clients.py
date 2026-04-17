from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import (
    PERMISSION_CLIENT_WRITE,
    PERMISSION_FEISHU_SYNC,
    get_current_user,
    require_permission,
)
from api.database import get_db
from api.services.client_service import ClientService

router = APIRouter(prefix="/api/clients", tags=["clients"])
service = ClientService()


class UpdateClauseRequest(BaseModel):
    fee_clause: str


class CreateClientRequest(BaseModel):
    name: str
    business_type: str = ""
    fee_clause: str = ""


class BatchApproveContractChangeReviewsRequest(BaseModel):
    review_ids: list[int]
    override_new_fee_clause_by_review_id: dict[int, str] | None = None


class ApproveContractChangeReviewRequest(BaseModel):
    override_new_fee_clause: str | None = None


@router.post("")
def add_new_client(
    request: CreateClientRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    client_id = service.add_client(request.name, request.business_type, request.fee_clause, db)
    return {"status": "ok", "message": "添加成功", "client_id": client_id}


@router.get("")
def list_clients(search: str = None, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    clients = service.list_clients(search, db)
    return {"clients": clients, "total": len(clients)}


@router.get("/contract-change-reviews")
def list_contract_change_reviews(
    search: str = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    reviews = service.list_contract_change_reviews(search, db)
    return {"reviews": reviews, "total": len(reviews)}


@router.post("/contract-change-reviews/batch-approve")
def batch_approve_contract_change_reviews(
    request: BatchApproveContractChangeReviewsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    result = service.batch_approve_contract_change_reviews(
        request.review_ids,
        current_user.get("username") or current_user.get("sub") or "",
        db,
        request.override_new_fee_clause_by_review_id,
    )
    return {"status": "ok", **result}


@router.post("/contract-change-reviews/{review_id}/approve")
def approve_contract_change_review(
    review_id: int,
    request: ApproveContractChangeReviewRequest | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    review = service.approve_contract_change_review(
        review_id,
        current_user.get("username") or current_user.get("sub") or "",
        db,
        request.override_new_fee_clause if request else None,
    )
    if not review:
        raise HTTPException(status_code=404, detail="待确认记录不存在")
    return {"status": "ok", "review": review}


@router.post("/contract-change-reviews/{review_id}/ignore")
def ignore_contract_change_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    success = service.ignore_contract_change_review(
        review_id,
        current_user.get("username") or current_user.get("sub") or "",
        db,
    )
    if not success:
        raise HTTPException(status_code=404, detail="待确认记录不存在")
    return {"status": "ok"}


@router.get("/{client_id:int}")
def get_client_detail(client_id: int, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    client = service.get_client_detail(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="客户不存在")
    return client


@router.post("/sync-feishu")
def sync_feishu_contracts(current_user: dict = Depends(require_permission(PERMISSION_FEISHU_SYNC))):
    from api.services.feishu_service import FeishuService

    feishu_service = FeishuService()
    return feishu_service.sync_contracts()


@router.put("/{client_id:int}")
def update_client_clause(
    client_id: int,
    request: UpdateClauseRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(PERMISSION_CLIENT_WRITE)),
):
    success = service.update_client_clause(client_id, request.fee_clause, db)
    if not success:
        raise HTTPException(status_code=404, detail="客户不存在")
    return {"status": "ok", "message": "更新成功"}
