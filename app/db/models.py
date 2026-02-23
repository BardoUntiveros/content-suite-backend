from __future__ import annotations

import enum
from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(str, enum.Enum):
    CREATOR = "creator"
    APPROVER_A = "approver_a"
    APPROVER_B = "approver_b"


class AssetType(str, enum.Enum):
    PRODUCT_DESCRIPTION = "product_description"
    VIDEO_SCRIPT = "video_script"
    IMAGE_PROMPT = "image_prompt"


class WorkflowStatus(str, enum.Enum):
    PENDING_A = "pending_a"
    PENDING_B = "pending_b"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditVerdict(str, enum.Enum):
    CHECK = "check"
    FAIL = "fail"


class JourneyEventType(str, enum.Enum):
    ASSET_CREATED = "asset_created"
    REVIEW_A_APPROVED = "review_a_approved"
    REVIEW_A_REJECTED = "review_a_rejected"
    AUDIT_CHECK = "audit_check"
    AUDIT_FAIL = "audit_fail"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role_enum"), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class BrandManual(Base):
    __tablename__ = "brand_manuals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tone: Mapped[str] = mapped_column(String(200), nullable=False)
    audience: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    manual_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    creator: Mapped[User] = relationship()
    chunks: Mapped[list[BrandManualChunk]] = relationship(
        back_populates="manual", cascade="all,delete"
    )


_embedding_type = Vector(768).with_variant(JSON(), "sqlite")


class BrandManualChunk(Base):
    __tablename__ = "brand_manual_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    manual_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_manuals.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(_embedding_type, nullable=False)

    manual: Mapped[BrandManual] = relationship(back_populates="chunks")


RagChunk = BrandManualChunk
RAG_CHUNK_SCOPE_FIELD = "manual_id"


class CreativeAsset(Base):
    __tablename__ = "creative_assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    manual_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brand_manuals.id"), nullable=False
    )
    created_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type_enum"), nullable=False
    )
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status_enum"),
        nullable=False,
        default=WorkflowStatus.PENDING_A,
    )
    reviewer_a_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reviewer_b_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    manual: Mapped[BrandManual] = relationship()
    audits: Mapped[list[MultimodalAudit]] = relationship(
        back_populates="asset", cascade="all,delete"
    )
    journey_events: Mapped[list[AssetJourneyEvent]] = relationship(
        back_populates="asset",
        cascade="all,delete",
        order_by="AssetJourneyEvent.created_at",
    )


class MultimodalAudit(Base):
    __tablename__ = "multimodal_audits"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creative_assets.id"), nullable=False, index=True
    )
    approver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    verdict: Mapped[AuditVerdict] = mapped_column(
        Enum(AuditVerdict, name="audit_verdict_enum"), nullable=False
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    asset: Mapped[CreativeAsset] = relationship(back_populates="audits")


class AssetJourneyEvent(Base):
    __tablename__ = "asset_journey_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creative_assets.id"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    event_type: Mapped[JourneyEventType] = mapped_column(
        Enum(JourneyEventType, name="journey_event_type_enum"),
        nullable=False,
    )
    from_status: Mapped[WorkflowStatus | None] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status_enum"),
        nullable=True,
    )
    to_status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status_enum"),
        nullable=False,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    asset: Mapped[CreativeAsset] = relationship(back_populates="journey_events")
    actor: Mapped[User | None] = relationship()
