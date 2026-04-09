from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    business_type = Column(String)
    department = Column(String)
    entity = Column(String)
    fee_clause = Column(String)
    payment_term = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ClientContractLine(Base):
    __tablename__ = "client_contract_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)
    source_token = Column(String, nullable=False)
    source_row_index = Column(Integer, nullable=False)
    client_name = Column(String, nullable=False)
    business_type = Column(String)
    department = Column(String)
    entity = Column(String)
    fee_clause = Column(String)
    payment_term = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            'source_type', 'source_token', 'source_row_index',
            name='_contract_line_source_row_uc'
        ),
    )


class BillingHistory(Base):
    __tablename__ = "billing_history"
    
    month = Column(String, primary_key=True)
    total_consumption = Column(Float)
    total_service_fee = Column(Float)
    created_at = Column(DateTime, server_default=func.now(), index=True)

class ClientMonthlyStats(Base):
    __tablename__ = "client_monthly_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False)
    client_name = Column(String, nullable=False)
    consumption = Column(Float, default=0.0)
    service_fee = Column(Float, default=0.0)
    
    __table_args__ = (
        UniqueConstraint('month', 'client_name', name='_month_client_uc'),
        Index('ix_client_monthly_stats_client_month', 'client_name', 'month'),
        Index('ix_client_monthly_stats_month_consumption', 'month', 'consumption'),
    )


class ClientMonthlyDetailStats(Base):
    __tablename__ = "client_monthly_detail_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False)
    client_name = Column(String, nullable=False)
    bill_type = Column(String, default="—")
    service_type = Column(String, default="—")
    flow_consumption = Column(Float, default=0.0)
    managed_consumption = Column(Float, default=0.0)
    net_consumption = Column(Float, default=0.0)
    service_fee = Column(Float, default=0.0)
    fixed_service_fee = Column(Float, default=0.0)
    coupon = Column(Float, default=0.0)
    dst = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint('month', 'client_name', name='_month_client_detail_uc'),
        Index('ix_client_monthly_detail_stats_client_month', 'client_name', 'month'),
        Index('ix_client_monthly_detail_stats_month_total', 'month', 'total'),
    )


class ClientMonthlyNote(Base):
    __tablename__ = "client_monthly_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False)
    client_name = Column(String, nullable=False)
    note = Column(String)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('month', 'client_name', name='_month_client_note_uc'),
        Index('ix_client_monthly_notes_client_month', 'client_name', 'month'),
    )

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    permissions = Column(String, default="[]", nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class OperationAuditLog(Base):
    __tablename__ = "operation_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    input_file = Column(String)
    output_file = Column(String)
    result_ref = Column(String)
    error_message = Column(String)
    metadata_json = Column(String)
    created_at = Column(DateTime, server_default=func.now(), index=True)
