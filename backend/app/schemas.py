from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    start_date: date
    end_date: date
    budget: float = Field(default=0, ge=0, le=1_000_000_000_000)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3,8}$")
    workday_start: time = time(8, 0)
    workday_end: time = time(18, 0)

    @model_validator(mode="after")
    def validate_ranges(self) -> ProjectCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if self.workday_end <= self.workday_start:
            raise ValueError("workday_end must be after workday_start")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    budget: float | None = Field(default=None, ge=0, le=1_000_000_000_000)
    status: Literal["PLANNING", "PRODUCTION", "COMPLETED"] | None = None


class SceneCreate(BaseModel):
    scene_number: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    location_id: str | None = None
    estimated_duration_minutes: int = Field(default=30, ge=1, le=1440)
    setup_minutes: int = Field(default=10, ge=0, le=480)
    priority: int = Field(default=3, ge=1, le=5)


class SceneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    location_id: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    setup_minutes: int | None = Field(default=None, ge=0, le=480)
    priority: int | None = Field(default=None, ge=1, le=5)


class ShotCreate(BaseModel):
    shot_number: str = Field(min_length=1, max_length=30)
    description: str = Field(default="", max_length=2000)
    frame_size: str = Field(default="MS", max_length=30)
    camera_movement: str = Field(default="Static", max_length=50)
    estimated_duration_minutes: int = Field(default=10, ge=1, le=480)
    setup_minutes: int = Field(default=5, ge=0, le=240)


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    type: Literal["CAST", "CREW", "EQUIPMENT", "LOCATION"]
    subtype: str = Field(default="", max_length=80)
    email: EmailStr | None = None
    default_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    overtime_rate: float | None = Field(default=None, ge=0, le=1_000_000_000)
    address: str | None = Field(default=None, max_length=400)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    extension_rate: float | None = Field(default=None, ge=0, le=1_000_000_000)


class AvailabilityCreate(BaseModel):
    date: date
    available_from: time = time(0, 0)
    available_until: time = time(23, 59)
    status: Literal["AVAILABLE", "UNAVAILABLE"] = "AVAILABLE"
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_window(self) -> AvailabilityCreate:
        if self.available_until <= self.available_from:
            raise ValueError("available_until must be after available_from")
        return self


class RequirementCreate(BaseModel):
    scene_id: str | None = None
    shot_id: str | None = None
    category: Literal["CAST", "EQUIPMENT", "LIGHTING", "AUDIO", "WEATHER", "LOCATION", "TIME", "DEPENDENCY", "QUALITY", "CONTINGENCY"]
    name: str = Field(min_length=1, max_length=180)
    required_resource_id: str | None = None
    required_value: str | None = Field(default=None, max_length=255)
    is_hard_constraint: bool = False
    source: Literal["MANUAL", "AI_SUGGESTED", "DOCUMENT"] = "MANUAL"
    confirmation_status: Literal["SUGGESTED", "CONFIRMED", "REJECTED"] = "CONFIRMED"
    fulfillment_status: Literal["SATISFIED", "UNKNOWN", "FAILED"] = "UNKNOWN"


class RequirementDecision(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED"]
    is_hard_constraint: bool | None = None


class IssueAction(BaseModel):
    action: Literal["ACCEPTED", "IGNORED", "RESOLVED"]
    confirm_patch: bool = False


class IncidentCreate(BaseModel):
    category: Literal["WEATHER", "EQUIPMENT_FAILURE", "EQUIPMENT_DELAY", "CAST_DELAY", "LOCATION", "OTHER"]
    resource_id: str | None = None
    scene_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=5000)
    estimated_duration_minutes: int | None = Field(default=None, ge=0, le=10080)
    affected_scene_ids: list[str] = Field(default_factory=list, max_length=100)
    impact_type: str = Field(default="BLOCKED", min_length=1, max_length=40)


class RecoveryGenerate(BaseModel):
    priority: Literal["TIME", "COST", "STABILITY"] = "TIME"


class WeatherManualCreate(BaseModel):
    location_id: str
    temperature: float | None = Field(default=None, ge=-100, le=100)
    rain_probability: float | None = Field(default=None, ge=0, le=100)
    weather_code: str = Field(default="MANUAL", max_length=40)


class AISettingsUpdate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=100)
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=160)
    api_key: str | None = Field(default=None, min_length=8, max_length=4096)
    enabled: bool = True


class ConfirmationResponse(BaseModel):
    response: Literal["AVAILABLE", "UNAVAILABLE"]


class NotificationSend(BaseModel):
    notification_ids: list[str] = Field(min_length=1, max_length=200)


class Envelope(BaseModel):
    success: bool
    data: Any | None = None
    error: dict[str, Any] | None = None
    model_config = ConfigDict(arbitrary_types_allowed=True)
