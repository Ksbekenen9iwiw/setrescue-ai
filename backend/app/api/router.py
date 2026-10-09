from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, not_found, success
from app.core.security import encrypt_secret, token_hash, validate_external_https_url
from app.database import get_db
from app.engines.prevent import run_prevent
from app.engines.scheduler import generate_initial_schedule, generate_recovery_plans, validate_recovery_plan
from app.models import (
    AICache, AISetting, AIUsageLog, CrewConfirmation, Document, DocumentVersion, Incident,
    IncidentImpact, Notification, PreventIssue, PreventRun, Project, RecoveryCostItem,
    RecoveryPlan, RecoveryPlanItem, Requirement, Resource, ResourceAvailability, Scene,
    SceneExecution, Schedule, ScheduleItem, Shot, WeatherSnapshot,
)
from app.schemas import (
    AISettingsUpdate, AvailabilityCreate, ConfirmationResponse, IncidentCreate, IssueAction,
    NotificationSend, ProjectCreate, ProjectUpdate, RecoveryGenerate, RequirementCreate,
    RequirementDecision, ResourceCreate, SceneCreate, SceneUpdate, ShotCreate, WeatherManualCreate,
)
from app.services.ai import call_structured_analysis, test_connection
from app.services.demo import load_realistic_demo
from app.services.documents import save_document
from app.services.notifications import calculate_crew_impact, create_previews, send_notifications
from app.services.reports import call_sheet_report, prevent_report, recovery_report
from app.services.serializers import model_dict, parse_json
from app.services.structured_import import apply as apply_structured_import, preview as preview_structured_import

router = APIRouter()


def project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise not_found("Project")
    return project


def scene_in_project(db: Session, project_id: str, scene_id: str) -> Scene:
    scene = db.scalar(select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id))
    if not scene:
        raise not_found("Scene")
    return scene


def resource_in_project(db: Session, project_id: str, resource_id: str) -> Resource:
    resource = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.project_id == project_id))
    if not resource:
        raise not_found("Resource")
    return resource


def _scene_payload(scene: Scene, shot_requirements: dict[str, list[Requirement]] | None = None) -> dict[str, Any]:
    data = model_dict(scene)
    data["shots"] = [model_dict(shot) for shot in scene.shots]
    data["requirements"] = [model_dict(req) for req in scene.requirements]
    for shot in scene.shots:
        data["requirements"].extend(model_dict(req) for req in (shot_requirements or {}).get(shot.id, []))
    return data


def _schedule_payload(db: Session, schedule: Schedule) -> dict[str, Any]:
    items = db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id).order_by(ScheduleItem.shooting_date, ScheduleItem.order_index)).all()
    scene_ids = [item.scene_id for item in items]
    scenes = {row.id: row for row in db.scalars(select(Scene).where(Scene.id.in_(scene_ids))).all()} if scene_ids else {}
    executions = {row.schedule_item_id: row for row in db.scalars(
        select(SceneExecution).where(SceneExecution.schedule_item_id.in_([item.id for item in items]))
    ).all()} if items else {}
    data = model_dict(schedule)
    data["items"] = []
    for item in items:
        row = model_dict(item)
        scene = scenes.get(item.scene_id)
        row["scene_number"] = scene.scene_number if scene else "?"
        row["scene_title"] = scene.title if scene else "Unknown scene"
        row["scene_status"] = scene.status if scene else "UNKNOWN"
        execution = executions.get(item.id)
        row["actual_start"] = execution.actual_start.isoformat() if execution and execution.actual_start else None
        row["actual_end"] = execution.actual_end.isoformat() if execution and execution.actual_end else None
        row["delay_minutes"] = execution.delay_minutes if execution else 0
        data["items"].append(row)
    return data


def _prevent_payload(run: PreventRun) -> dict[str, Any]:
    data = model_dict(run)
    data["category_scores"] = parse_json(run.category_scores_json, {})
    data["issues"] = [model_dict(issue) | {"proposed_patch": parse_json(issue.proposed_patch_json, None)} for issue in run.issues]
    return data


def _plan_payload(db: Session, plan: RecoveryPlan) -> dict[str, Any]:
    data = model_dict(plan)
    items = db.scalars(select(RecoveryPlanItem).where(RecoveryPlanItem.recovery_plan_id == plan.id)).all()
    costs = db.scalars(select(RecoveryCostItem).where(RecoveryCostItem.recovery_plan_id == plan.id)).all()
    scene_ids = [item.scene_id for item in items]
    scenes = {row.id: row for row in db.scalars(select(Scene).where(Scene.id.in_(scene_ids))).all()} if scene_ids else {}
    data["items"] = []
    for item in sorted(items, key=lambda value: (value.shooting_date is None, value.shooting_date or datetime.max.date(), value.start_time or datetime.max.time())):
        row = model_dict(item)
        scene = scenes.get(item.scene_id)
        row["scene_number"] = scene.scene_number if scene else "?"
        row["scene_title"] = scene.title if scene else "Unknown scene"
        data["items"].append(row)
    data["cost_breakdown"] = [model_dict(item) for item in costs]
    return data


@router.get("/health")
def health() -> dict:
    return success({"status": "ok", "service": "setrescue-api"})


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> dict:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return success([model_dict(project) for project in projects])


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> dict:
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return success(model_dict(project))


@router.post("/demo/realistic", status_code=201)
def create_demo(db: Session = Depends(get_db)) -> dict:
    project = load_realistic_demo(db)
    return success(model_dict(project))


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    scenes = db.scalars(select(Scene).where(Scene.project_id == project_id).options(selectinload(Scene.shots), selectinload(Scene.requirements)).order_by(Scene.scene_number)).all()
    resources = db.scalars(select(Resource).where(Resource.project_id == project_id).options(selectinload(Resource.availability)).order_by(Resource.type, Resource.name)).all()
    documents = db.scalars(select(Document).where(Document.project_id == project_id).options(selectinload(Document.versions)).order_by(Document.created_at)).all()
    shot_ids = [shot.id for scene in scenes for shot in scene.shots]
    shot_requirements: dict[str, list[Requirement]] = {}
    if shot_ids:
        for req in db.scalars(select(Requirement).where(Requirement.shot_id.in_(shot_ids))).all():
            if req.shot_id and req.scene_id is None:
                shot_requirements.setdefault(req.shot_id, []).append(req)
    data = model_dict(project)
    data["scenes"] = [_scene_payload(scene, shot_requirements) for scene in scenes]
    data["resources"] = [model_dict(resource) | {"availability": [model_dict(value) for value in resource.availability]} for resource in resources]
    data["documents"] = [model_dict(document) | {"versions": [model_dict(value, exclude={"local_path", "extracted_text"}) for value in document.versions]} for document in documents]
    return success(data)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    project.production_state_version += 1
    db.commit()
    return success(model_dict(project))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    db.delete(project)
    db.commit()
    return success({"deleted": True})


@router.get("/projects/{project_id}/dashboard")
def dashboard(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    prevent = db.scalar(select(PreventRun).where(PreventRun.project_id == project_id).options(selectinload(PreventRun.issues)).order_by(PreventRun.started_at.desc()))
    schedule = db.scalar(select(Schedule).where(Schedule.project_id == project_id, Schedule.status == "ACTIVE").order_by(Schedule.version_number.desc()))
    incidents = db.scalars(select(Incident).where(Incident.project_id == project_id).order_by(Incident.reported_at.desc()).limit(5)).all()
    totals = {
        "scenes": db.scalar(select(func.count()).select_from(Scene).where(Scene.project_id == project_id)) or 0,
        "completed": db.scalar(select(func.count()).select_from(Scene).where(Scene.project_id == project_id, Scene.status == "COMPLETED")) or 0,
        "resources": db.scalar(select(func.count()).select_from(Resource).where(Resource.project_id == project_id)) or 0,
        "open_incidents": db.scalar(select(func.count()).select_from(Incident).where(Incident.project_id == project_id, Incident.status != "RESOLVED")) or 0,
    }
    return success({
        "project": model_dict(project), "totals": totals,
        "prevent": _prevent_payload(prevent) if prevent else None,
        "active_schedule": _schedule_payload(db, schedule) if schedule else None,
        "recent_incidents": [model_dict(row) for row in incidents],
    })


@router.get("/projects/{project_id}/documents")
def list_documents(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    documents = db.scalars(select(Document).where(Document.project_id == project_id).options(selectinload(Document.versions))).all()
    return success([model_dict(doc) | {"versions": [model_dict(version, exclude={"local_path", "extracted_text"}) for version in doc.versions]} for doc in documents])


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(
    project_id: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    project = project_or_404(db, project_id)
    try:
        version = await save_document(db, project_id, document_type.upper(), file)
    finally:
        await file.close()
    project.production_state_version += 1
    db.commit()
    return success(model_dict(version, exclude={"local_path", "extracted_text"}))


@router.post("/projects/{project_id}/documents/analyze")
def analyze_documents(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    versions = db.scalars(
        select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.project_id == project_id, DocumentVersion.version_number == Document.current_version)
    ).all()
    if not versions:
        raise AppError(409, "DOCUMENT_PARSE_FAILED", "Upload at least one document before AI analysis.")
    scenes = db.scalars(select(Scene).where(Scene.project_id == project_id)).all()
    scene_map = {scene.scene_number: scene for scene in scenes}
    analysis, cache_hit, tokens = call_structured_analysis(
        db, f"{project_id}:PREVENT_EXTRACTION", "\n\n".join(version.extracted_text for version in versions),
        {"project": project.name, "scene_numbers": list(scene_map)},
    )
    accepted, unknown = 0, []
    for output in analysis.scenes:
        scene = scene_map.get(output.scene_number)
        if not scene:
            unknown.append(output.scene_number)
            continue
        for suggestion in output.detected_requirements:
            duplicate = db.scalar(select(Requirement.id).where(
                Requirement.scene_id == scene.id, Requirement.name == suggestion.name,
                Requirement.confirmation_status != "REJECTED",
            ))
            if duplicate:
                continue
            db.add(Requirement(
                scene_id=scene.id, category=suggestion.category, name=suggestion.name,
                required_value=suggestion.source_reason[:255], is_hard_constraint=False,
                source="AI_SUGGESTED", confirmation_status="SUGGESTED", fulfillment_status="UNKNOWN",
                confidence=suggestion.confidence,
            ))
            accepted += 1
    db.commit()
    return success({"suggestions_created": accepted, "unknown_scene_references": unknown, "cache_hit": cache_hit, "token_usage": tokens})


@router.get("/projects/{project_id}/documents/{document_id}/import-preview")
def preview_document_import(project_id: str, document_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    return success(preview_structured_import(db, project_id, document_id))


@router.post("/projects/{project_id}/documents/{document_id}/apply-import")
def apply_document_import(project_id: str, document_id: str, payload: dict[str, str], db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    expected = payload.get("version_id")
    if not expected:
        raise AppError(422, "VALIDATION_ERROR", "A preview version_id is required before applying an import.")
    return success(apply_structured_import(db, project, document_id, expected))


@router.post("/projects/{project_id}/scenes", status_code=201)
def create_scene(project_id: str, payload: SceneCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    if payload.location_id:
        resource = resource_in_project(db, project_id, payload.location_id)
        if resource.type != "LOCATION":
            raise AppError(422, "RESOURCE_NOT_FOUND", "location_id must identify a project location.")
    scene = Scene(project_id=project_id, **payload.model_dump())
    db.add(scene)
    project.production_state_version += 1
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "SCENE_NUMBER_EXISTS", "Scene number already exists in this project.") from exc
    db.refresh(scene)
    return success(model_dict(scene))


@router.patch("/projects/{project_id}/scenes/{scene_id}")
def update_scene(project_id: str, scene_id: str, payload: SceneUpdate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    scene = scene_in_project(db, project_id, scene_id)
    values = payload.model_dump(exclude_unset=True)
    if values.get("location_id"):
        resource = resource_in_project(db, project_id, values["location_id"])
        if resource.type != "LOCATION":
            raise AppError(422, "RESOURCE_NOT_FOUND", "location_id must identify a project location.")
    for key, value in values.items():
        setattr(scene, key, value)
    project.production_state_version += 1
    db.commit()
    return success(model_dict(scene))


@router.post("/projects/{project_id}/scenes/{scene_id}/shots", status_code=201)
def add_shot(project_id: str, scene_id: str, payload: ShotCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    scene_in_project(db, project_id, scene_id)
    shot = Shot(scene_id=scene_id, **payload.model_dump())
    db.add(shot)
    project.production_state_version += 1
    db.commit()
    db.refresh(shot)
    return success(model_dict(shot))


@router.get("/projects/{project_id}/resources")
def list_resources(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    rows = db.scalars(select(Resource).where(Resource.project_id == project_id).options(selectinload(Resource.availability)).order_by(Resource.type, Resource.name)).all()
    return success([model_dict(row) | {"availability": [model_dict(item) for item in row.availability]} for row in rows])


@router.post("/projects/{project_id}/resources", status_code=201)
def create_resource(project_id: str, payload: ResourceCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    resource = Resource(project_id=project_id, **payload.model_dump(mode="json"))
    db.add(resource)
    project.production_state_version += 1
    db.commit()
    db.refresh(resource)
    return success(model_dict(resource))


@router.post("/projects/{project_id}/resources/{resource_id}/availability", status_code=201)
def add_availability(project_id: str, resource_id: str, payload: AvailabilityCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    resource_in_project(db, project_id, resource_id)
    item = ResourceAvailability(resource_id=resource_id, **payload.model_dump())
    db.add(item)
    project.production_state_version += 1
    db.commit()
    db.refresh(item)
    return success(model_dict(item))


@router.post("/projects/{project_id}/requirements", status_code=201)
def create_requirement(project_id: str, payload: RequirementCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    if not payload.scene_id and not payload.shot_id:
        raise AppError(422, "INVALID_REQUIREMENT", "A requirement must reference a scene or shot.")
    scene = scene_in_project(db, project_id, payload.scene_id) if payload.scene_id else None
    if payload.shot_id:
        shot = db.scalar(select(Shot).join(Scene).where(Shot.id == payload.shot_id, Scene.project_id == project_id))
        if not shot:
            raise not_found("Shot")
        if scene and shot.scene_id != scene.id:
            raise AppError(422, "INVALID_REQUIREMENT", "Shot does not belong to the selected scene.")
    if payload.required_resource_id:
        resource_in_project(db, project_id, payload.required_resource_id)
    values = payload.model_dump()
    if values["source"] == "AI_SUGGESTED":
        values["confirmation_status"] = "SUGGESTED"
        values["is_hard_constraint"] = False
    requirement = Requirement(**values)
    db.add(requirement)
    project.production_state_version += 1
    db.commit()
    db.refresh(requirement)
    return success(model_dict(requirement))


@router.post("/projects/{project_id}/requirements/{requirement_id}/decision")
def decide_requirement(project_id: str, requirement_id: str, payload: RequirementDecision, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    requirement = db.get(Requirement, requirement_id)
    if requirement and requirement.scene_id:
        owned = db.scalar(select(Scene.id).where(Scene.id == requirement.scene_id, Scene.project_id == project_id))
    elif requirement and requirement.shot_id:
        owned = db.scalar(select(Shot.id).join(Scene).where(Shot.id == requirement.shot_id, Scene.project_id == project_id))
    else:
        owned = None
    if not owned:
        requirement = None
    if not requirement:
        raise not_found("Requirement")
    requirement.confirmation_status = payload.decision
    if payload.decision == "CONFIRMED" and payload.is_hard_constraint is not None:
        requirement.is_hard_constraint = payload.is_hard_constraint
    if payload.decision == "REJECTED":
        requirement.is_hard_constraint = False
    project.production_state_version += 1
    db.commit()
    return success(model_dict(requirement))


@router.get("/projects/{project_id}/prevent")
def latest_prevent(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    run = db.scalar(select(PreventRun).where(PreventRun.project_id == project_id).options(selectinload(PreventRun.issues)).order_by(PreventRun.started_at.desc()))
    return success(_prevent_payload(run) if run else None)


@router.post("/projects/{project_id}/prevent/run")
def execute_prevent(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    run = run_prevent(db, project)
    run = db.scalar(select(PreventRun).where(PreventRun.id == run.id).options(selectinload(PreventRun.issues)))
    return success(_prevent_payload(run))


@router.get("/projects/{project_id}/prevent/issues/{issue_id}/preview")
def preview_issue_patch(project_id: str, issue_id: str, db: Session = Depends(get_db)) -> dict:
    issue = db.scalar(select(PreventIssue).join(PreventRun).where(PreventIssue.id == issue_id, PreventRun.project_id == project_id))
    if not issue:
        raise not_found("PREVENT issue")
    return success({"issue_id": issue.id, "patch": parse_json(issue.proposed_patch_json, None), "requires_confirmation": True})


@router.post("/projects/{project_id}/prevent/issues/{issue_id}")
def act_on_issue(project_id: str, issue_id: str, payload: IssueAction, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    issue = db.scalar(select(PreventIssue).join(PreventRun).where(PreventIssue.id == issue_id, PreventRun.project_id == project_id))
    if not issue:
        raise not_found("PREVENT issue")
    patch = parse_json(issue.proposed_patch_json, None)
    if payload.confirm_patch:
        if not patch:
            raise AppError(422, "INVALID_PATCH", "This issue has no proposed patch.")
        if patch.get("action") == "ADD_PLACEHOLDER_SHOT":
            scene = scene_in_project(db, project_id, patch.get("scene_id", ""))
            db.add(Shot(scene_id=scene.id, shot_number=f"{scene.scene_number}.NEW", description="Placeholder shot — edit before production", frame_size="TBD", camera_movement="TBD", estimated_duration_minutes=10, setup_minutes=5))
        else:
            raise AppError(422, "INVALID_PATCH", "Unsupported proposed patch.")
    issue.status = payload.action
    project.production_state_version += 1
    db.commit()
    return success(model_dict(issue))


@router.get("/projects/{project_id}/schedule")
def list_schedules(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    schedules = db.scalars(select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.version_number.desc())).all()
    return success([_schedule_payload(db, schedule) for schedule in schedules])


@router.post("/projects/{project_id}/schedule/generate")
def create_initial_schedule(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    existing = db.scalar(select(Schedule).where(Schedule.project_id == project_id, Schedule.status == "ACTIVE"))
    if existing:
        raise AppError(409, "ACTIVE_SCHEDULE_EXISTS", "Use recovery to replace an active schedule.")
    schedule = generate_initial_schedule(db, project)
    return success(_schedule_payload(db, schedule))


def _execute_scene(scene_id: str, action: str, db: Session) -> dict:
    item = db.scalar(
        select(ScheduleItem).join(Schedule).where(ScheduleItem.scene_id == scene_id, Schedule.status == "ACTIVE")
    )
    scene = db.get(Scene, scene_id)
    if not scene or not item:
        raise not_found("Scheduled scene")
    project = project_or_404(db, scene.project_id)
    execution = db.scalar(select(SceneExecution).where(SceneExecution.schedule_item_id == item.id))
    now = datetime.now(timezone.utc)
    if not execution:
        execution = SceneExecution(scene_id=scene.id, schedule_item_id=item.id)
        db.add(execution)
    if action == "start":
        if scene.status == "COMPLETED":
            raise AppError(409, "SCENE_ALREADY_COMPLETED", "A completed scene cannot be restarted.")
        execution.actual_start = execution.actual_start or now
        execution.status = "IN_PROGRESS"
        scene.status, scene.is_locked = "IN_PROGRESS", True
    elif action == "complete":
        if not execution.actual_start or execution.status != "IN_PROGRESS":
            raise AppError(409, "SCENE_NOT_STARTED", "Start the scene before completing it.")
        execution.actual_end = now
        execution.actual_duration_minutes = max(0, int((now - execution.actual_start.replace(tzinfo=execution.actual_start.tzinfo or timezone.utc)).total_seconds() // 60))
        execution.delay_minutes = max(0, execution.actual_duration_minutes - item.planned_duration_minutes)
        execution.status = "COMPLETED"
        scene.status, scene.is_locked = "COMPLETED", True
    else:
        execution.status = "BLOCKED"
        scene.status, scene.is_locked = "BLOCKED", False
    project.production_state_version += 1
    db.commit()
    return success(model_dict(execution) | {"scene_status": scene.status, "meaningful_delay": execution.delay_minutes >= 15})


@router.post("/scenes/{scene_id}/start")
def start_scene(scene_id: str, db: Session = Depends(get_db)) -> dict:
    return _execute_scene(scene_id, "start", db)


@router.post("/scenes/{scene_id}/complete")
def complete_scene(scene_id: str, db: Session = Depends(get_db)) -> dict:
    return _execute_scene(scene_id, "complete", db)


@router.post("/scenes/{scene_id}/block")
def block_scene(scene_id: str, db: Session = Depends(get_db)) -> dict:
    return _execute_scene(scene_id, "block", db)


@router.get("/projects/{project_id}/incidents")
def list_incidents(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    rows = db.scalars(select(Incident).where(Incident.project_id == project_id).options(selectinload(Incident.impacts)).order_by(Incident.reported_at.desc())).all()
    return success([model_dict(row) | {"impacts": [model_dict(impact) for impact in row.impacts]} for row in rows])


@router.post("/projects/{project_id}/incidents", status_code=201)
def create_incident(project_id: str, payload: IncidentCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    if payload.resource_id:
        resource_in_project(db, project_id, payload.resource_id)
    if payload.scene_id:
        scene_in_project(db, project_id, payload.scene_id)
    affected = list(dict.fromkeys(payload.affected_scene_ids + ([payload.scene_id] if payload.scene_id else [])))
    for scene_id in affected:
        scene_in_project(db, project_id, scene_id)
    values = payload.model_dump(exclude={"affected_scene_ids", "impact_type"})
    incident = Incident(project_id=project_id, **values)
    db.add(incident)
    db.flush()
    for scene_id in affected:
        db.add(IncidentImpact(incident_id=incident.id, scene_id=scene_id, resource_id=payload.resource_id, impact_type=payload.impact_type, severity="CRITICAL", confirmed=True))
        scene = scene_in_project(db, project_id, scene_id)
        if scene.status not in {"COMPLETED", "IN_PROGRESS"}:
            scene.status = "BLOCKED"
    project.production_state_version += 1
    db.commit()
    db.refresh(incident)
    return success(model_dict(incident) | {"affected_scene_ids": affected})


@router.post("/incidents/{incident_id}/recovery/generate")
def recover(incident_id: str, payload: RecoveryGenerate, db: Session = Depends(get_db)) -> dict:
    incident = db.get(Incident, incident_id)
    if not incident:
        raise not_found("Incident")
    project = project_or_404(db, incident.project_id)
    plans = generate_recovery_plans(db, project, incident)
    ordering = {"TIME": "FASTEST", "COST": "CHEAPEST", "STABILITY": "MINIMUM_CHANGE"}
    recommended = ordering[payload.priority]
    rows = sorted((_plan_payload(db, plan) for plan in plans), key=lambda item: (item["type"] != recommended, item["score"]))
    return success({"priority": payload.priority, "recommended_type": recommended, "plans": rows})


@router.get("/projects/{project_id}/recovery")
def list_recovery(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    plans = db.scalars(
        select(RecoveryPlan).join(Incident).where(Incident.project_id == project_id).order_by(RecoveryPlan.created_at.desc())
    ).all()
    return success([_plan_payload(db, plan) for plan in plans])


@router.post("/recovery-plans/{plan_id}/approve")
def approve_recovery(plan_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        if db.bind and db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        plan = db.scalar(select(RecoveryPlan).where(RecoveryPlan.id == plan_id).with_for_update())
        if not plan:
            raise not_found("Recovery plan")
        incident = db.get(Incident, plan.incident_id)
        if not incident:
            raise not_found("Incident")
        project = db.scalar(select(Project).where(Project.id == incident.project_id).with_for_update())
        if not project:
            raise not_found("Project")
        validate_recovery_plan(db, project, plan)
        base = db.get(Schedule, plan.base_schedule_id)
        max_version = db.scalar(select(func.max(Schedule.version_number)).where(Schedule.project_id == project.id)) or 0
        new_schedule = Schedule(
            project_id=project.id, version_number=max_version + 1, type="RECOVERY", status="ACTIVE",
            parent_schedule_id=base.id, approved_at=datetime.now(timezone.utc),
        )
        db.add(new_schedule)
        db.flush()
        plan_items = db.scalars(select(RecoveryPlanItem).where(RecoveryPlanItem.recovery_plan_id == plan.id)).all()
        scenes = {row.id: row for row in db.scalars(select(Scene).where(Scene.project_id == project.id)).all()}
        ordered = sorted(plan_items, key=lambda row: (row.shooting_date, row.start_time))
        for index, item in enumerate(ordered):
            scene = scenes[item.scene_id]
            start_minutes = item.start_time.hour * 60 + item.start_time.minute
            end_minutes = item.end_time.hour * 60 + item.end_time.minute
            db.add(ScheduleItem(
                schedule_id=new_schedule.id, scene_id=item.scene_id, shooting_date=item.shooting_date,
                planned_start=item.start_time, planned_end=item.end_time,
                planned_duration_minutes=end_minutes - start_minutes, location_id=item.location_id, order_index=index,
            ))
            if scene.status not in {"COMPLETED", "IN_PROGRESS"}:
                scene.status = "READY"
        base.status = "SUPERSEDED"
        plan.status = "APPROVED"
        project.production_state_version += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(new_schedule)
    previews = create_previews(db, project, new_schedule)
    return success({
        "schedule": _schedule_payload(db, new_schedule),
        "crew_impact": calculate_crew_impact(db, new_schedule),
        "notification_previews": [model_dict(row) for row in previews],
    })


@router.get("/schedules/{schedule_id}/crew-impact")
def crew_impact(schedule_id: str, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise not_found("Schedule")
    return success(calculate_crew_impact(db, schedule))


@router.post("/schedules/{schedule_id}/notifications/preview")
def preview_notifications(schedule_id: str, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise not_found("Schedule")
    project = project_or_404(db, schedule.project_id)
    rows = create_previews(db, project, schedule)
    return success([model_dict(row) for row in rows])


@router.post("/schedules/{schedule_id}/notifications/send")
def send_schedule_notifications(schedule_id: str, payload: NotificationSend, request: Request, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise not_found("Schedule")
    owned = db.scalar(select(func.count()).select_from(Notification).where(Notification.schedule_id == schedule_id, Notification.id.in_(payload.notification_ids))) or 0
    if owned != len(set(payload.notification_ids)):
        raise not_found("Notification")
    frontend_url = request.headers.get("origin") or "http://localhost:5173"
    if frontend_url not in {"http://localhost:5173", "http://127.0.0.1:5173"}:
        frontend_url = "http://localhost:5173"
    return success(send_notifications(db, payload.notification_ids, frontend_url))


@router.get("/confirmations/{token}")
def get_confirmation(token: str, db: Session = Depends(get_db)) -> dict:
    if len(token) < 32 or len(token) > 128:
        raise not_found("Confirmation")
    confirmation = db.scalar(select(CrewConfirmation).where(CrewConfirmation.token_hash == token_hash(token)))
    if not confirmation:
        raise not_found("Confirmation")
    expires = confirmation.expires_at.replace(tzinfo=confirmation.expires_at.tzinfo or timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise AppError(410, "CONFIRMATION_EXPIRED", "This confirmation link has expired.")
    notification = db.get(Notification, confirmation.notification_id)
    return success({"recipient": notification.recipient_email, "subject": notification.subject, "response": confirmation.response, "expires_at": confirmation.expires_at.isoformat()})


@router.post("/confirmations/{token}")
def respond_confirmation(token: str, payload: ConfirmationResponse, db: Session = Depends(get_db)) -> dict:
    if len(token) < 32 or len(token) > 128:
        raise not_found("Confirmation")
    confirmation = db.scalar(select(CrewConfirmation).where(CrewConfirmation.token_hash == token_hash(token)))
    if not confirmation:
        raise not_found("Confirmation")
    expires = confirmation.expires_at.replace(tzinfo=confirmation.expires_at.tzinfo or timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise AppError(410, "CONFIRMATION_EXPIRED", "This confirmation link has expired.")
    notification = db.get(Notification, confirmation.notification_id)
    schedule = db.get(Schedule, notification.schedule_id)
    project = project_or_404(db, notification.project_id)
    confirmation.response = payload.response
    confirmation.responded_at = datetime.now(timezone.utc)
    invalidated = False
    if payload.response == "UNAVAILABLE":
        items = db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id)).all()
        scene_ids = [item.scene_id for item in items]
        shot_parents = dict(db.execute(select(Shot.id, Shot.scene_id).where(Shot.scene_id.in_(scene_ids))).all())
        requirements = db.scalars(select(Requirement).where(
            Requirement.required_resource_id == notification.resource_id,
            Requirement.confirmation_status == "CONFIRMED",
            (Requirement.scene_id.in_(scene_ids) | Requirement.shot_id.in_(list(shot_parents))),
        )).all()
        required_scene_ids = {req.scene_id or shot_parents.get(req.shot_id) for req in requirements}
        for item in items:
            if item.scene_id in required_scene_ids:
                existing = db.scalar(select(ResourceAvailability).where(
                    ResourceAvailability.resource_id == notification.resource_id,
                    ResourceAvailability.date == item.shooting_date,
                ))
                if existing:
                    existing.status = "UNAVAILABLE"
                    existing.notes = "Crew member responded unavailable to schedule update."
                else:
                    db.add(ResourceAvailability(
                        resource_id=notification.resource_id, date=item.shooting_date,
                        available_from=item.planned_start, available_until=item.planned_end,
                        status="UNAVAILABLE", notes="Crew member responded unavailable to schedule update.",
                    ))
                invalidated = True
        if invalidated:
            project.production_state_version += 1
    db.commit()
    return success({"response": confirmation.response, "schedule_no_longer_valid": invalidated})


@router.get("/projects/{project_id}/weather")
def get_weather(project_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    rows = db.scalars(select(WeatherSnapshot).where(WeatherSnapshot.project_id == project_id).order_by(WeatherSnapshot.timestamp.desc())).all()
    return success([model_dict(row) for row in rows])


@router.post("/projects/{project_id}/weather/manual", status_code=201)
def report_weather(project_id: str, payload: WeatherManualCreate, db: Session = Depends(get_db)) -> dict:
    project = project_or_404(db, project_id)
    location = resource_in_project(db, project_id, payload.location_id)
    if location.type != "LOCATION":
        raise AppError(422, "RESOURCE_NOT_FOUND", "Weather must reference a project location.")
    snapshot = WeatherSnapshot(project_id=project_id, type="MANUAL", source="Production Manager", **payload.model_dump())
    db.add(snapshot)
    project.production_state_version += 1
    db.commit()
    db.refresh(snapshot)
    return success(model_dict(snapshot))


@router.post("/projects/{project_id}/weather/{location_id}/refresh")
def refresh_weather(project_id: str, location_id: str, db: Session = Depends(get_db)) -> dict:
    project_or_404(db, project_id)
    location = resource_in_project(db, project_id, location_id)
    if location.type != "LOCATION" or location.latitude is None or location.longitude is None:
        raise AppError(422, "WEATHER_UNAVAILABLE", "Location needs valid coordinates for weather forecast.")
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": location.latitude, "longitude": location.longitude, "current": "temperature_2m,weather_code", "hourly": "precipitation_probability", "forecast_days": 2},
            timeout=12,
        )
        response.raise_for_status()
        raw = response.json()
        current = raw["current"]
        rain_values = (raw.get("hourly") or {}).get("precipitation_probability") or []
        snapshot = WeatherSnapshot(
            project_id=project_id, location_id=location_id, type="CURRENT",
            temperature=float(current.get("temperature_2m")) if current.get("temperature_2m") is not None else None,
            rain_probability=float(rain_values[0]) if rain_values else None,
            weather_code=str(current.get("weather_code", "")), source="Open-Meteo",
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise AppError(502, "WEATHER_UNAVAILABLE", "Weather provider is currently unavailable.") from exc
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return success(model_dict(snapshot))


@router.get("/projects/{project_id}/reports/prevent")
def export_prevent(project_id: str, db: Session = Depends(get_db)) -> FileResponse:
    project = project_or_404(db, project_id)
    path = prevent_report(db, project)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/projects/{project_id}/reports/recovery")
def export_recovery(project_id: str, incident_id: str | None = None, db: Session = Depends(get_db)) -> FileResponse:
    project = project_or_404(db, project_id)
    if incident_id:
        incident = db.scalar(select(Incident).where(Incident.id == incident_id, Incident.project_id == project_id))
        if not incident:
            raise not_found("Incident")
    path = recovery_report(db, project, incident_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/projects/{project_id}/reports/call-sheet/{schedule_id}")
def export_call_sheet(project_id: str, schedule_id: str, db: Session = Depends(get_db)) -> FileResponse:
    project = project_or_404(db, project_id)
    schedule = db.scalar(select(Schedule).where(Schedule.id == schedule_id, Schedule.project_id == project_id))
    if not schedule:
        raise not_found("Schedule")
    path = call_sheet_report(db, project, schedule)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/settings/ai")
def get_ai_settings(db: Session = Depends(get_db)) -> dict:
    setting = db.scalar(select(AISetting).order_by(AISetting.updated_at.desc()))
    if not setting:
        return success({"provider_name": "siaptuan.my.id", "base_url": "https://siaptuan.my.id/v1", "model": "", "enabled": False, "api_key_configured": False})
    return success(model_dict(setting, exclude={"encrypted_api_key"}) | {"api_key_configured": bool(setting.encrypted_api_key)})


@router.put("/settings/ai")
def update_ai_settings(payload: AISettingsUpdate, db: Session = Depends(get_db)) -> dict:
    base_url = validate_external_https_url(str(payload.base_url))
    setting = db.scalar(select(AISetting).order_by(AISetting.updated_at.desc()))
    if not setting:
        setting = AISetting()
        db.add(setting)
    setting.provider_name = payload.provider_name
    setting.base_url = base_url
    setting.model = payload.model
    setting.enabled = payload.enabled
    if payload.api_key:
        setting.encrypted_api_key = encrypt_secret(payload.api_key)
    db.commit()
    db.refresh(setting)
    return success(model_dict(setting, exclude={"encrypted_api_key"}) | {"api_key_configured": bool(setting.encrypted_api_key)})


@router.post("/settings/ai/test")
def test_ai(db: Session = Depends(get_db)) -> dict:
    setting = db.scalar(select(AISetting).order_by(AISetting.updated_at.desc()))
    if not setting:
        raise AppError(422, "AI_CONNECTION_FAILED", "Save AI settings before testing.")
    return success(test_connection(setting))


@router.get("/settings/ai/usage")
def ai_usage(db: Session = Depends(get_db)) -> dict:
    logs = db.scalars(select(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(100)).all()
    return success({
        "logs": [model_dict(row) for row in logs],
        "totals": {
            "tokens": sum(row.total_tokens for row in logs),
            "calls": sum(not row.cache_hit for row in logs),
            "cache_hits": sum(row.cache_hit for row in logs),
        },
    })
