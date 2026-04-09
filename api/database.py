# -*- coding: utf-8 -*-
"""
数据库操作模块 (SQLAlchemy ORM 版)
"""
from typing import Any, List, Dict, Optional
from sqlalchemy import create_engine, desc, func, and_, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
from .models import Base, Client, BillingHistory, ClientMonthlyDetailStats, ClientMonthlyNote, ClientMonthlyStats
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import json

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "contracts.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """初始化数据库表 (在 Alembic 环境下通常仅用于手动测试或第一次运行)"""
    # Base.metadata.create_all(bind=engine)
    pass

def ensure_user_permissions_column():
    """
    Add users.permissions for older databases that predate permission-based access control.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "users" not in inspector.get_table_names():
            return
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "permissions" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '[]'"))
            conn.execute(text("UPDATE users SET permissions = '[]' WHERE permissions IS NULL"))


def ensure_dashboard_indexes():
    """
    Add performance indexes for dashboard aggregation/report queries on existing databases.
    Safe to run repeatedly.
    """
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            table_names = set(inspector.get_table_names())

            if "client_monthly_stats" in table_names:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_client_monthly_stats_client_month "
                        "ON client_monthly_stats (client_name, month)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_client_monthly_stats_month_consumption "
                        "ON client_monthly_stats (month, consumption)"
                    )
                )

            if "client_monthly_detail_stats" in table_names:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_client_monthly_detail_stats_client_month "
                        "ON client_monthly_detail_stats (client_name, month)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_client_monthly_detail_stats_month_total "
                        "ON client_monthly_detail_stats (month, total)"
                    )
                )

            if "billing_history" in table_names:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_billing_history_created_at "
                        "ON billing_history (created_at)"
                    )
                )
    except OperationalError as exc:
        logger.warning("ensure_dashboard_indexes skipped due to database operational error: %s", exc)


def ensure_client_monthly_detail_stats_table():
    """
    Ensure per-client monthly detail aggregation table exists for ledger pages.
    Safe to run repeatedly.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS client_monthly_detail_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        month TEXT NOT NULL,
                        client_name TEXT NOT NULL,
                        bill_type TEXT DEFAULT '—',
                        service_type TEXT DEFAULT '—',
                        flow_consumption FLOAT DEFAULT 0,
                        managed_consumption FLOAT DEFAULT 0,
                        net_consumption FLOAT DEFAULT 0,
                        service_fee FLOAT DEFAULT 0,
                        fixed_service_fee FLOAT DEFAULT 0,
                        coupon FLOAT DEFAULT 0,
                        dst FLOAT DEFAULT 0,
                        total FLOAT DEFAULT 0,
                        CONSTRAINT _month_client_detail_uc UNIQUE (month, client_name)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_client_monthly_detail_stats_client_month "
                    "ON client_monthly_detail_stats (client_name, month)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_client_monthly_detail_stats_month_total "
                    "ON client_monthly_detail_stats (month, total)"
                )
            )
    except OperationalError as exc:
        logger.warning("ensure_client_monthly_detail_stats_table skipped due to database operational error: %s", exc)


def ensure_client_monthly_notes_table():
    """
    Ensure per-client monthly note table exists for editable ledger remarks.
    Safe to run repeatedly.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS client_monthly_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        month TEXT NOT NULL,
                        client_name TEXT NOT NULL,
                        note TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT _month_client_note_uc UNIQUE (month, client_name)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_client_monthly_notes_client_month "
                    "ON client_monthly_notes (client_name, month)"
                )
            )
    except OperationalError as exc:
        logger.warning("ensure_client_monthly_notes_table skipped due to database operational error: %s", exc)


def ensure_operation_audit_table():
    """
    Ensure operation audit table exists for task history and traceability.
    Safe to run repeatedly.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS operation_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        action TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        status TEXT NOT NULL,
                        input_file TEXT,
                        output_file TEXT,
                        result_ref TEXT,
                        error_message TEXT,
                        metadata_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_operation_audit_logs_created_at "
                    "ON operation_audit_logs (created_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_operation_audit_logs_actor_created_at "
                    "ON operation_audit_logs (actor, created_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_operation_audit_logs_action_created_at "
                    "ON operation_audit_logs (action, created_at)"
                )
            )
    except OperationalError as exc:
        logger.warning("ensure_operation_audit_table skipped due to database operational error: %s", exc)


def upsert_billing_history(month: str, consumption: float, fee: float, db: Session = None):
    """更新月度账单统计"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        record = db.query(BillingHistory).filter(BillingHistory.month == month).first()
        if record:
            record.total_consumption = consumption
            record.total_service_fee = fee
        else:
            new_record = BillingHistory(
                month=month,
                total_consumption=consumption,
                total_service_fee=fee
            )
            db.add(new_record)
        db.commit()
    finally:
        if should_close:
            db.close()

def upsert_client_stats_batch(month: str, stats: List[Dict], db: Session = None):
    """批量更新客户月度统计"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        for s in stats:
            record = db.query(ClientMonthlyStats).filter(
                ClientMonthlyStats.month == month,
                ClientMonthlyStats.client_name == s['name']
            ).first()
            
            if record:
                record.consumption = s['consumption']
                record.service_fee = s['fee']
            else:
                new_record = ClientMonthlyStats(
                    month=month,
                    client_name=s['name'],
                    consumption=s['consumption'],
                    service_fee=s['fee']
                )
                db.add(new_record)
        db.commit()
    finally:
        if should_close:
            db.close()

def get_top_clients(month: str, limit: int = 20, db: Session = None) -> List[Dict]:
    """获取某月消耗排名前N的客户"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        results = db.query(ClientMonthlyStats).filter(
            ClientMonthlyStats.month == month
        ).order_by(desc(ClientMonthlyStats.consumption)).limit(limit).all()
        return [{"client_name": r.client_name, "consumption": r.consumption, "service_fee": r.service_fee} for r in results]
    finally:
        if should_close:
            db.close()

def get_billing_history(db: Session = None) -> List[Dict]:
    """获取所有历史账单数据（按月份排序）"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        results = db.query(BillingHistory).order_by(BillingHistory.month).all()
        return [{"month": r.month, "total_consumption": r.total_consumption, "total_service_fee": r.total_service_fee} for r in results]
    finally:
        if should_close:
            db.close()

def get_all_clients(search: str = None, db: Session = None) -> List[Dict]:
    """获取所有客户"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        query = db.query(Client)
        if search:
            query = query.filter(Client.name.like(f"%{search}%"))
        results = query.order_by(Client.name).all()
        return [
            {
                "id": r.id, "name": r.name, "business_type": r.business_type,
                "department": r.department, "entity": r.entity, "fee_clause": r.fee_clause,
                "payment_term": r.payment_term,
                "created_at": r.created_at, "updated_at": r.updated_at
            }
            for r in results
        ]
    finally:
        if should_close:
            db.close()

def get_client(client_id: int, db: Session = None) -> Optional[Dict]:
    """获取单个客户"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        r = db.query(Client).filter(Client.id == client_id).first()
        if r:
            return {
                "id": r.id, "name": r.name, "business_type": r.business_type,
                "department": r.department, "entity": r.entity, "fee_clause": r.fee_clause,
                "payment_term": r.payment_term,
                "created_at": r.created_at, "updated_at": r.updated_at
            }
        return None
    finally:
        if should_close:
            db.close()

def get_client_by_name(name: str, db: Session = None) -> Optional[Dict]:
    """根据名称获取客户"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        r = db.query(Client).filter(Client.name == name).first()
        if r:
            return {
                "id": r.id, "name": r.name, "business_type": r.business_type,
                "department": r.department, "entity": r.entity, "fee_clause": r.fee_clause,
                "payment_term": r.payment_term,
                "created_at": r.created_at, "updated_at": r.updated_at
            }
        return None
    finally:
        if should_close:
            db.close()

def update_client(client_id: int, fee_clause: str, db: Session = None) -> bool:
    """更新客户条款"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        r = db.query(Client).filter(Client.id == client_id).first()
        if r:
            r.fee_clause = fee_clause
            r.updated_at = datetime.now()
            db.commit()
            return True
        return False
    finally:
        if should_close:
            db.close()

def upsert_client(name: str, business_type: str = None, department: str = None, 
                  entity: str = None, fee_clause: str = None, payment_term: str = None, db: Session = None) -> int:
    """插入或更新客户（完全覆盖模式）"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        r = db.query(Client).filter(Client.name == name).first()
        if r:
            if business_type is not None: r.business_type = business_type
            if department is not None: r.department = department
            if entity is not None: r.entity = entity
            if fee_clause is not None: r.fee_clause = fee_clause
            if payment_term is not None: r.payment_term = payment_term
            r.updated_at = datetime.now()
            client_id = r.id
        else:
            new_client = Client(
                name=name,
                business_type=business_type,
                department=department,
                entity=entity,
                fee_clause=fee_clause,
                payment_term=payment_term
            )
            db.add(new_client)
            db.flush()  # To get the ID
            client_id = new_client.id
        db.commit()
        return client_id
    finally:
        if should_close:
            db.close()


def upsert_client_detail_stats_batch(month: str, stats: List[Dict], db: Session = None):
    """批量更新客户月度明细统计"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        for s in stats:
            client_name = str(s.get("name") or "").strip()
            if not client_name:
                continue

            record = db.query(ClientMonthlyDetailStats).filter(
                ClientMonthlyDetailStats.month == month,
                ClientMonthlyDetailStats.client_name == client_name,
            ).first()

            payload = {
                "bill_type": str(s.get("bill_type") or "—").strip() or "—",
                "service_type": str(s.get("service_type") or "—").strip() or "—",
                "flow_consumption": float(s.get("flow_consumption") or 0.0),
                "managed_consumption": float(s.get("managed_consumption") or 0.0),
                "net_consumption": float(s.get("net_consumption") or 0.0),
                "service_fee": float(s.get("service_fee") or 0.0),
                "fixed_service_fee": float(s.get("fixed_service_fee") or 0.0),
                "coupon": float(s.get("coupon") or 0.0),
                "dst": float(s.get("dst") or 0.0),
                "total": float(s.get("total") or 0.0),
            }

            if record:
                record.bill_type = payload["bill_type"]
                record.service_type = payload["service_type"]
                record.flow_consumption = payload["flow_consumption"]
                record.managed_consumption = payload["managed_consumption"]
                record.net_consumption = payload["net_consumption"]
                record.service_fee = payload["service_fee"]
                record.fixed_service_fee = payload["fixed_service_fee"]
                record.coupon = payload["coupon"]
                record.dst = payload["dst"]
                record.total = payload["total"]
            else:
                db.add(
                    ClientMonthlyDetailStats(
                        month=month,
                        client_name=client_name,
                        **payload,
                    )
                )
        db.commit()
    finally:
        if should_close:
            db.close()


def record_operation_audit(
    *,
    category: str,
    action: str,
    actor: str,
    status: str,
    input_file: str | None = None,
    output_file: str | None = None,
    result_ref: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Persist operation audit log in best-effort mode.
    Never raises to callers.
    """
    ensure_operation_audit_table()
    payload = None
    if metadata:
        try:
            payload = json.dumps(metadata, ensure_ascii=False)
        except Exception:
            payload = json.dumps({"_meta_dump_failed": True}, ensure_ascii=False)

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO operation_audit_logs
                    (category, action, actor, status, input_file, output_file, result_ref, error_message, metadata_json)
                    VALUES
                    (:category, :action, :actor, :status, :input_file, :output_file, :result_ref, :error_message, :metadata_json)
                    """
                ),
                {
                    "category": str(category or "").strip() or "unknown",
                    "action": str(action or "").strip() or "unknown",
                    "actor": str(actor or "").strip() or "system",
                    "status": str(status or "").strip() or "unknown",
                    "input_file": str(input_file or "").strip() or None,
                    "output_file": str(output_file or "").strip() or None,
                    "result_ref": str(result_ref or "").strip() or None,
                    "error_message": str(error_message or "").strip()[:1000] or None,
                    "metadata_json": payload,
                },
            )
    except OperationalError as exc:
        logger.warning("record_operation_audit skipped due to database operational error: %s", exc)
    except Exception:
        logger.warning("record_operation_audit failed", exc_info=True)


def list_operation_audit_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    actor: str | None = None,
    actor_like: str | None = None,
    category: str | None = None,
    action: str | None = None,
    status: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """
    Read task history records ordered by newest first.
    """
    ensure_operation_audit_table()
    safe_limit = max(1, min(500, int(limit or 100)))
    safe_offset = max(0, int(offset or 0))
    filters = []
    params: dict[str, Any] = {"limit": safe_limit, "offset": safe_offset}

    if actor:
        filters.append("actor = :actor")
        params["actor"] = actor
    if actor_like:
        filters.append("actor LIKE :actor_like")
        params["actor_like"] = f"%{actor_like}%"
    if category:
        filters.append("category = :category")
        params["category"] = category
    if action:
        filters.append("action = :action")
        params["action"] = action
    if status:
        filters.append("status = :status")
        params["status"] = status
    if created_after:
        filters.append("created_at >= :created_after")
        params["created_after"] = created_after.strftime("%Y-%m-%d %H:%M:%S")
    if created_before:
        filters.append("created_at <= :created_before")
        params["created_before"] = created_before.strftime("%Y-%m-%d %H:%M:%S")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    count_sql = text(f"SELECT COUNT(1) FROM operation_audit_logs {where_clause}")
    sql = text(
        f"""
        SELECT id, category, action, actor, status, input_file, output_file, result_ref, error_message, metadata_json, created_at
        FROM operation_audit_logs
        {where_clause}
        ORDER BY id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    total_count = 0
    try:
        with engine.connect() as conn:
            total_count = conn.execute(count_sql, params).scalar() or 0
            rows = conn.execute(sql, params).mappings().all()
    except OperationalError as exc:
        logger.warning("list_operation_audit_logs skipped due to database operational error: %s", exc)
        return 0, []
    except Exception:
        logger.warning("list_operation_audit_logs failed", exc_info=True)
        return 0, []

    results: list[dict[str, Any]] = []
    for row in rows:
        metadata_obj = None
        raw_meta = row.get("metadata_json")
        if raw_meta:
            try:
                metadata_obj = json.loads(str(raw_meta))
            except Exception:
                metadata_obj = {"raw": str(raw_meta)}
        results.append(
            {
                "id": row.get("id"),
                "category": row.get("category"),
                "action": row.get("action"),
                "actor": row.get("actor"),
                "status": row.get("status"),
                "input_file": row.get("input_file"),
                "output_file": row.get("output_file"),
                "result_ref": row.get("result_ref"),
                "error_message": row.get("error_message"),
                "metadata": metadata_obj,
                "created_at": str(row.get("created_at") or ""),
            }
        )
    return total_count, results
