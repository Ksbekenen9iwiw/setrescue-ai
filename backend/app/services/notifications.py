from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import new_confirmation_token, token_hash
from app.models import (
    CrewConfirmation, Notification, Project, Requirement, Resource, Schedule, ScheduleItem, Shot,
)


def calculate_crew_impact(db: Session, schedule: Schedule) -> list[dict]:
    if not schedule.parent_schedule_id:
        return []
    previous = {item.scene_id: item for item in db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.parent_schedule_id)).all()}
    current = {item.scene_id: item for item in db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id)).all()}
    changed_scene_ids = {
        scene_id for scene_id, item in current.items()
        if scene_id not in previous
        or item.shooting_date != previous[scene_id].shooting_date
        or item.planned_start != previous[scene_id].planned_start
        or item.location_id != previous[scene_id].location_id
    }
    if not changed_scene_ids:
        return []
    shot_parents = dict(db.execute(select(Shot.id, Shot.scene_id).where(Shot.scene_id.in_(changed_scene_ids))).all())
    requirements = db.scalars(select(Requirement).where(
        (Requirement.scene_id.in_(changed_scene_ids) | Requirement.shot_id.in_(list(shot_parents))),
        Requirement.confirmation_status == "CONFIRMED",
        Requirement.required_resource_id.is_not(None),
    )).all()
    resource_ids = {row.required_resource_id for row in requirements}
    resources = db.scalars(select(Resource).where(Resource.id.in_(resource_ids), Resource.type.in_(["CAST", "CREW"]))).all() if resource_ids else []
    impacts: list[dict] = []
    for resource in resources:
        scenes = []
        for scene_id in changed_scene_ids:
            required = any((req.scene_id or shot_parents.get(req.shot_id)) == scene_id and
                           req.required_resource_id == resource.id for req in requirements)
            if required and scene_id in current:
                item = current[scene_id]
                scenes.append({"scene_id": scene_id, "date": item.shooting_date.isoformat(), "start": item.planned_start.isoformat(timespec="minutes")})
        if scenes:
            impacts.append({
                "resource_id": resource.id, "name": resource.name, "email": resource.email,
                "changed_scenes": scenes, "can_notify": bool(resource.email),
            })
    return impacts


def create_previews(db: Session, project: Project, schedule: Schedule) -> list[Notification]:
    impacts = calculate_crew_impact(db, schedule)
    existing = {row.resource_id: row for row in db.scalars(select(Notification).where(Notification.schedule_id == schedule.id)).all()}
    created: list[Notification] = []
    for impact in impacts:
        if not impact["email"]:
            continue
        rows = ", ".join(f"{scene['date']} at {scene['start']}" for scene in impact["changed_scenes"])
        notification = existing.get(impact["resource_id"])
        if not notification:
            notification = Notification(
                project_id=project.id, schedule_id=schedule.id, resource_id=impact["resource_id"],
                recipient_email=impact["email"], channel="EMAIL", status="PREVIEW",
            )
            db.add(notification)
        notification.subject = f"Schedule V{schedule.version_number} update — {project.name}"
        notification.body = f"Hello {impact['name']}, your production schedule changed: {rows}. Please confirm your availability using the secure link provided when this update is sent."
        created.append(notification)
    db.commit()
    for row in created:
        db.refresh(row)
    return created


def send_notifications(db: Session, notification_ids: list[str], public_base_url: str = "http://localhost:5173") -> list[dict]:
    rows = db.scalars(select(Notification).where(Notification.id.in_(notification_ids))).all()
    if len(rows) != len(set(notification_ids)):
        raise AppError(404, "RESOURCE_NOT_FOUND", "One or more notifications were not found.")
    settings = get_settings()
    results: list[dict] = []
    for notification in rows:
        raw_token = new_confirmation_token()
        confirmation = db.scalar(select(CrewConfirmation).where(CrewConfirmation.notification_id == notification.id))
        if confirmation:
            confirmation.token_hash = token_hash(raw_token)
            confirmation.response = None
            confirmation.responded_at = None
            confirmation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        else:
            confirmation = CrewConfirmation(
                notification_id=notification.id, token_hash=token_hash(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(confirmation)
        confirmation_url = f"{public_base_url.rstrip('/')}/confirm/{raw_token}"
        delivered_body = f"{notification.body}\n\nConfirm availability: {confirmation_url}"
        if settings.demo_email:
            notification.status = "SENT"
        else:
            if not settings.resend_api_key:
                raise AppError(503, "EMAIL_SEND_FAILED", "Resend API key is not configured.")
            try:
                response = httpx.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                    json={
                        "from": "SetRescue <updates@resend.dev>", "to": [notification.recipient_email],
                        "subject": notification.subject, "text": delivered_body,
                    },
                    timeout=15,
                )
            except httpx.HTTPError as exc:
                notification.status = "FAILED"
                db.commit()
                raise AppError(502, "EMAIL_SEND_FAILED", "Crew notification could not be sent.") from exc
            if response.status_code >= 400:
                notification.status = "FAILED"
                db.commit()
                raise AppError(502, "EMAIL_SEND_FAILED", "Crew notification provider rejected the request.")
            notification.status = "SENT"
        notification.sent_at = datetime.now(timezone.utc)
        results.append({
            "notification_id": notification.id, "status": notification.status,
            "recipient_email": notification.recipient_email,
            "confirmation_url": confirmation_url if settings.demo_email else None,
        })
    db.commit()
    return results
