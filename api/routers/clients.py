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


@router.get("/{client_id}")
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


@router.put("/{client_id}")
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
