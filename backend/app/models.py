from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    budget: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="IDR")
    workday_start: Mapped[time] = mapped_column(Time, default=time(8, 0))
    workday_end: Mapped[time] = mapped_column(Time, default=time(18, 0))
    default_overtime_rate: Mapped[float] = mapped_column(Float, default=250_000)
    default_transport_rate: Mapped[float] = mapped_column(Float, default=350_000)
    default_location_extension_rate: Mapped[float] = mapped_column(Float, default=1_500_000)
    status: Mapped[str] = mapped_column(String(20), default="PLANNING")
    production_state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scenes: Mapped[list[Scene]] = relationship(back_populates="project", cascade="all, delete-orphan")
    resources: Mapped[list[Resource]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    local_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    document: Mapped[Document] = relationship(back_populates="versions")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "scene_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scene_number: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    location_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    setup_minutes: Mapped[int] = mapped_column(Integer, default=10)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    project: Mapped[Project] = relationship(back_populates="scenes")
    shots: Mapped[list[Shot]] = relationship(back_populates="scene", cascade="all, delete-orphan")
    requirements: Mapped[list[Requirement]] = relationship(back_populates="scene", cascade="all, delete-orphan", foreign_keys="Requirement.scene_id")


class Shot(Base):
    __tablename__ = "shots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    shot_number: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    frame_size: Mapped[str] = mapped_column(String(30), default="MS")
    camera_movement: Mapped[str] = mapped_column(String(50), default="Static")
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    setup_minutes: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    scene: Mapped[Scene] = relationship(back_populates="shots")


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    subtype: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    default_cost: Mapped[float] = mapped_column(Float, default=0)
    overtime_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    extension_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    project: Mapped[Project] = relationship(back_populates="resources", foreign_keys=[project_id])
    availability: Mapped[list[ResourceAvailability]] = relationship(back_populates="resource", cascade="all, delete-orphan")


class ResourceAvailability(Base):
    __tablename__ = "resource_availability"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    available_from: Mapped[time] = mapped_column(Time, default=time(0, 0))
    available_until: Mapped[time] = mapped_column(Time, default=time(23, 59))
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    notes: Mapped[str] = mapped_column(Text, default="")
    resource: Mapped[Resource] = relationship(back_populates="availability")


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=True, index=True)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    required_resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    required_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_hard_constraint: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")
    confirmation_status: Mapped[str] = mapped_column(String(20), default="CONFIRMED")
    fulfillment_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    scene: Mapped[Scene | None] = relationship(back_populates="requirements", foreign_keys=[scene_id])


class PreventRun(Base):
    __tablename__ = "prevent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")
    category_scores_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    issues: Mapped[list[PreventIssue]] = relationship(back_populates="run", cascade="all, delete-orphan")


class PreventIssue(Base):
    __tablename__ = "prevent_issues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    prevent_run_id: Mapped[str] = mapped_column(ForeignKey("prevent_runs.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id", ondelete="SET NULL"), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="RULE")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    proposed_patch_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    run: Mapped[PreventRun] = relationship(back_populates="issues")


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("project_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="INITIAL")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    parent_schedule_id: Mapped[str | None] = mapped_column(ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list[ScheduleItem]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    shooting_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_start: Mapped[time] = mapped_column(Time, nullable=False)
    planned_end: Mapped[time] = mapped_column(Time, nullable=False)
    planned_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    schedule: Mapped[Schedule] = relationship(back_populates="items")


class SceneExecution(Base):
    __tablename__ = "scene_execution"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    schedule_item_id: Mapped[str] = mapped_column(ForeignKey("schedule_items.id", ondelete="CASCADE"), unique=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    actual_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED")
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_analysis_status: Mapped[str] = mapped_column(String(20), default="NOT_REQUIRED")
    impacts: Mapped[list[IncidentImpact]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentImpact(Base):
    __tablename__ = "incident_impacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    impact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="CRITICAL")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    incident: Mapped[Incident] = relationship(back_populates="impacts")


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    base_schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"))
    base_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="VALID")
    estimated_finish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    estimated_extra_cost: Mapped[float] = mapped_column(Float, default=0)
    moved_scene_count: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_scene_count: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list[RecoveryPlanItem]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    costs: Mapped[list[RecoveryCostItem]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class RecoveryPlanItem(Base):
    __tablename__ = "recovery_plan_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recovery_plan_id: Mapped[str] = mapped_column(ForeignKey("recovery_plans.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    shooting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[RecoveryPlan] = relationship(back_populates="items")


class RecoveryCostItem(Base):
    __tablename__ = "recovery_cost_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recovery_plan_id: Mapped[str] = mapped_column(ForeignKey("recovery_plans.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(20), default="unit")
    rate: Mapped[float] = mapped_column(Float, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[RecoveryPlan] = relationship(back_populates="costs")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    recipient_email: Mapped[str] = mapped_column(String(254), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="EMAIL")
    status: Mapped[str] = mapped_column(String(20), default="PREVIEW")
    subject: Mapped[str] = mapped_column(String(200), default="Schedule update")
    body: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrewConfirmation(Base):
    __tablename__ = "crew_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)


class AISetting(Base):
    __tablename__ = "ai_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider_name: Mapped[str] = mapped_column(String(100), default="siaptuan.my.id")
    base_url: Mapped[str] = mapped_column(String(500), default="https://siaptuan.my.id/v1")
    model: Mapped[str] = mapped_column(String(160), default="")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AICache(Base):
    __tablename__ = "ai_cache"
    __table_args__ = (UniqueConstraint("operation", "input_hash", "context_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
