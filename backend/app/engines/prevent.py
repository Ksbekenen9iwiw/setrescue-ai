from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Document, DocumentVersion, PreventIssue, PreventRun, Project, Requirement, Scene, Shot


CATEGORY_WEIGHTS = {
    "SHOT_SCENE_COMPLETENESS": 0.20,
    "CAST": 0.15,
    "EQUIPMENT": 0.15,
    "LOCATION": 0.10,
    "SCHEDULE_FEASIBILITY": 0.15,
    "QUALITY": 0.15,
    "CONTINGENCY": 0.10,
}
FULFILLMENT_VALUE = {"SATISFIED": 1.0, "UNKNOWN": 0.5, "FAILED": 0.0}


def requirement_bucket(category: str) -> str:
    return {
        "CAST": "CAST",
        "EQUIPMENT": "EQUIPMENT",
        "LIGHTING": "QUALITY",
        "AUDIO": "QUALITY",
        "QUALITY": "QUALITY",
        "LOCATION": "LOCATION",
        "WEATHER": "LOCATION",
        "TIME": "SCHEDULE_FEASIBILITY",
        "DEPENDENCY": "SCHEDULE_FEASIBILITY",
        "CONTINGENCY": "CONTINGENCY",
    }.get(category, "SHOT_SCENE_COMPLETENESS")


def document_state_hash(db: Session, project_id: str) -> str:
    hashes = db.scalars(
        select(DocumentVersion.file_hash)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.project_id == project_id)
        .order_by(Document.id, DocumentVersion.version_number)
    ).all()
    return hashlib.sha256("|".join(hashes).encode()).hexdigest()


def run_prevent(db: Session, project: Project) -> PreventRun:
    scenes = db.scalars(
        select(Scene).where(Scene.project_id == project.id).options(selectinload(Scene.shots), selectinload(Scene.requirements))
    ).all()
    scene_ids = [scene.id for scene in scenes]
    shot_parents = dict(db.execute(select(Shot.id, Shot.scene_id).where(Shot.scene_id.in_(scene_ids))).all()) if scene_ids else {}
    requirements = db.scalars(
        select(Requirement).where(
            Requirement.scene_id.in_(scene_ids) | Requirement.shot_id.in_(list(shot_parents))
        )
    ).all() if scene_ids else []
    requirements_by_scene: dict[str, list[Requirement]] = {scene.id: [] for scene in scenes}
    for req in requirements:
        parent_id = req.scene_id or shot_parents.get(req.shot_id)
        if parent_id in requirements_by_scene:
            requirements_by_scene[parent_id].append(req)

    values: dict[str, list[float]] = defaultdict(list)
    for scene in scenes:
        values["SHOT_SCENE_COMPLETENESS"].append(1.0 if scene.shots else 0.0)
    for req in requirements:
        if req.confirmation_status == "REJECTED":
            continue
        values[requirement_bucket(req.category)].append(FULFILLMENT_VALUE.get(req.fulfillment_status, 0.5))

    category_scores: dict[str, float] = {}
    for category in CATEGORY_WEIGHTS:
        entries = values.get(category, [])
        category_scores[category] = round((sum(entries) / len(entries) if entries else 0.5) * 100, 1)

    run = PreventRun(project_id=project.id, document_state_hash=document_state_hash(db, project.id))
    db.add(run)
    db.flush()

    issues: list[PreventIssue] = []
    if not scenes:
        issues.append(PreventIssue(
            prevent_run_id=run.id, severity="CRITICAL", category="COMPLETENESS",
            title="No scenes defined", description="Add scenes before production readiness can be verified.",
            recommended_action="Import documents or add scenes manually.", source="RULE",
        ))
    for scene in scenes:
        if not scene.shots:
            issues.append(PreventIssue(
                prevent_run_id=run.id, scene_id=scene.id, severity="WARNING", category="COMPLETENESS",
                title=f"Scene {scene.scene_number} has no shots",
                description="Shot-level requirements cannot be fully validated.",
                recommended_action="Add or import a shot list for this scene.", source="RULE",
                proposed_patch_json=json.dumps({"action": "ADD_PLACEHOLDER_SHOT", "scene_id": scene.id}),
            ))
        confirmed = [r for r in requirements_by_scene[scene.id] if r.confirmation_status == "CONFIRMED"]
        if not confirmed:
            issues.append(PreventIssue(
                prevent_run_id=run.id, scene_id=scene.id, severity="WARNING", category="REQUIREMENTS",
                title=f"Scene {scene.scene_number} has no confirmed requirements",
                description="Shootability cannot be verified without confirmed dependencies.",
                recommended_action="Review and confirm suggested requirements.", source="RULE",
            ))
    for req in requirements:
        if req.confirmation_status == "SUGGESTED":
            issues.append(PreventIssue(
                prevent_run_id=run.id, scene_id=req.scene_id, shot_id=req.shot_id, severity="INFO",
                category=req.category, title=f"Confirmation needed: {req.name}",
                description="An AI/document suggestion is not yet authoritative.",
                recommended_action="Confirm or reject this requirement.", source=req.source,
            ))
        if req.confirmation_status == "CONFIRMED" and req.is_hard_constraint and req.fulfillment_status == "FAILED":
            issues.append(PreventIssue(
                prevent_run_id=run.id, scene_id=req.scene_id, shot_id=req.shot_id, severity="CRITICAL",
                category=req.category, title=f"Hard requirement failed: {req.name}",
                description="A confirmed hard constraint is not satisfied.",
                recommended_action="Restore the dependency or revise the production plan.", source="RULE",
            ))

    db.add_all(issues)
    weighted = sum(category_scores[key] * weight for key, weight in CATEGORY_WEIGHTS.items())
    critical_count = sum(i.severity == "CRITICAL" for i in issues)
    warning_count = sum(i.severity == "WARNING" for i in issues)
    pending_count = sum(r.confirmation_status == "SUGGESTED" for r in requirements)
    penalty = min(20, critical_count * 10 + warning_count * 3 + pending_count * 2)
    score = max(0.0, round(weighted - penalty, 1))
    hard_blocker = any(
        r.confirmation_status == "CONFIRMED" and r.is_hard_constraint and r.fulfillment_status == "FAILED"
        for r in requirements
    ) or not scenes
    important_unknown = any(
        r.confirmation_status == "CONFIRMED" and r.is_hard_constraint and r.fulfillment_status == "UNKNOWN"
        for r in requirements
    )
    if hard_blocker:
        status = "NOT_READY"
    elif score >= 85 and critical_count == 0 and not important_unknown and pending_count == 0:
        status = "READY"
    else:
        status = "NEEDS_REVIEW"

    run.overall_score = score
    run.status = status
    run.category_scores_json = json.dumps(category_scores)
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
