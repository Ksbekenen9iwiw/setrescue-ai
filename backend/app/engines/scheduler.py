from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models import (
    Incident, IncidentImpact, Project, RecoveryCostItem, RecoveryPlan, RecoveryPlanItem,
    Requirement, Resource, ResourceAvailability, Scene, Schedule, ScheduleItem, Shot, WeatherSnapshot,
)

SLOT_MINUTES = 15
UNRESOLVED_PENALTY = 1_000_000


@dataclass(frozen=True)
class Candidate:
    day_index: int
    start_slot: int
    end_slot: int
    shooting_date: date
    start_time: time
    end_time: time
    location_id: str | None
    stability: int
    cost_units: int


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time(total_minutes: int) -> time:
    total_minutes %= 24 * 60
    return time(total_minutes // 60, total_minutes % 60)


def _production_local_day(timestamp: datetime) -> date:
    """Weather reports use the local Windows filming day, not the UTC calendar day."""
    aware = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    return aware.astimezone().date()


def _days(project: Project) -> list[date]:
    count = min(14, (project.end_date - project.start_date).days + 1)
    return [project.start_date + timedelta(days=i) for i in range(max(1, count))]


def _requirements(db: Session, scene_ids: list[str]) -> dict[str, list[Requirement]]:
    grouped: dict[str, list[Requirement]] = {scene_id: [] for scene_id in scene_ids}
    # Shot-level dependencies are hard requirements of their parent scene too.
    shot_to_scene = dict(db.execute(select(Shot.id, Shot.scene_id).where(Shot.scene_id.in_(scene_ids))).all()) if scene_ids else {}
    rows = db.scalars(
        select(Requirement).where(
            (Requirement.scene_id.in_(scene_ids) | Requirement.shot_id.in_(list(shot_to_scene))),
            Requirement.confirmation_status == "CONFIRMED",
        )
    ).all() if scene_ids else []
    for row in rows:
        parent_scene_id = row.scene_id or shot_to_scene.get(row.shot_id)
        if parent_scene_id in grouped:
            grouped[parent_scene_id].append(row)
    return grouped


def _available(db: Session, resource_id: str, day: date, start: int, end: int,
               cache: dict | None = None) -> bool:
    key = (resource_id, day)
    if cache is not None and key in cache:
        status, rows = cache[key]
    else:
        resource = db.get(Resource, resource_id)
        status = resource.status if resource else "UNAVAILABLE"
        rows = db.scalars(
            select(ResourceAvailability).where(
                ResourceAvailability.resource_id == resource_id,
                ResourceAvailability.date == day,
            )
        ).all()
        if cache is not None:
            cache[key] = (status, rows)
    if status != "AVAILABLE":
        return False
    if not rows:
        return True
    # An explicit outage must take precedence over an overlapping normal window.
    if any(row.status == "UNAVAILABLE" and _minutes(row.available_from) < end
           and start < _minutes(row.available_until) for row in rows):
        return False
    return any(
        row.status == "AVAILABLE"
        and _minutes(row.available_from) <= start
        and _minutes(row.available_until) >= end
        for row in rows
    )


def _weather_satisfied(db: Session, project_id: str, location_id: str | None, requirement: Requirement, shooting_day: date) -> bool:
    if not location_id:
        return False
    # Human-reported actual conditions outrank forecast/current weather data.
    latest_manual = db.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.project_id == project_id, WeatherSnapshot.location_id == location_id,
               WeatherSnapshot.type == "MANUAL")
        .order_by(WeatherSnapshot.timestamp.desc())
    )
    latest = db.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.project_id == project_id, WeatherSnapshot.location_id == location_id)
        .order_by(WeatherSnapshot.timestamp.desc())
    )
    if not latest:
        return requirement.fulfillment_status != "FAILED"
    value = (requirement.required_value or "").upper()
    if latest_manual and _production_local_day(latest_manual.timestamp) == shooting_day and ("DRY" in value or "NO_RAIN" in value):
        return (latest_manual.rain_probability or 0) < 30 and latest_manual.weather_code not in {"RAIN", "HEAVY_RAIN"}
    return requirement.fulfillment_status != "FAILED"


def _project_audio_weather_satisfied(db: Session, project_id: str, requirement: Requirement, shooting_day: date) -> bool:
    value = (requirement.required_value or "").upper()
    if "NO_RAIN" not in value:
        return requirement.fulfillment_status != "FAILED"
    latest = db.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.project_id == project_id, WeatherSnapshot.type == "MANUAL")
        .order_by(WeatherSnapshot.timestamp.desc())
    )
    if latest and _production_local_day(latest.timestamp) == shooting_day:
        return (latest.rain_probability or 0) < 30 and latest.weather_code not in {"RAIN", "HEAVY_RAIN"}
    return requirement.fulfillment_status != "FAILED"


def _slot_allowed(
    db: Session,
    project: Project,
    scene: Scene,
    requirements: Iterable[Requirement],
    day: date,
    start: int,
    end: int,
    availability_cache: dict | None = None,
) -> bool:
    for req in requirements:
        if not req.is_hard_constraint:
            continue
        if req.fulfillment_status != "SATISFIED":
            return False
        if req.category == "WEATHER" and not _weather_satisfied(db, project.id, scene.location_id, req, day):
            return False
        if req.category == "AUDIO" and not _project_audio_weather_satisfied(db, project.id, req, day):
            return False
        if req.required_resource_id and not _available(db, req.required_resource_id, day, start, end, availability_cache):
            return False
        if req.category == "TIME" and req.required_value:
            # Supported deterministic values: AFTER=13:00 and BEFORE=18:00.
            try:
                mode, raw = req.required_value.upper().split("=", 1)
                hour, minute = (int(part) for part in raw.split(":"))
                boundary = hour * 60 + minute
                if mode == "AFTER" and start < boundary:
                    return False
                if mode == "BEFORE" and end > boundary:
                    return False
            except (ValueError, TypeError):
                return False
    if scene.location_id and not _available(db, scene.location_id, day, start, end, availability_cache):
        return False
    return True


def _incremental_costs(project: Project, end_minute: int, original: ScheduleItem | None,
                       changed_location: bool) -> list[tuple[str, float, str, float, str]]:
    """Return incremental cost components; don't bill an already-booked second day again."""
    work_end = _minutes(project.workday_end)
    baseline_end = _minutes(original.planned_end) if original else work_end
    additional_overtime_hours = max(0, math.ceil(max(0, end_minute - work_end) / 60)
                                    - math.ceil(max(0, baseline_end - work_end) / 60))
    costs: list[tuple[str, float, str, float, str]] = []
    if additional_overtime_hours and project.default_overtime_rate:
        costs.append(("OVERTIME", additional_overtime_hours, "hour", project.default_overtime_rate,
                      "Additional overtime beyond the baseline scene commitment"))
    if changed_location and project.default_transport_rate:
        costs.append(("TRANSPORT", 1, "move", project.default_transport_rate,
                      "Location changed relative to the baseline"))
    return costs


def _build_candidates(
    db: Session,
    project: Project,
    scene: Scene,
    reqs: list[Requirement],
    original: ScheduleItem | None,
    blocked_until: datetime | None,
    availability_cache: dict | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    duration_slots = math.ceil((scene.estimated_duration_minutes + scene.setup_minutes) / SLOT_MINUTES)
    work_start = _minutes(project.workday_start)
    # Allow up to two hours overtime, costed by the engine.
    latest = min(24 * 60 - SLOT_MINUTES, _minutes(project.workday_end) + 120)
    for day_idx, shooting_day in enumerate(_days(project)):
        first_slot = work_start // SLOT_MINUTES
        last_start = latest // SLOT_MINUTES - duration_slots
        for start_slot in range(first_slot, last_start + 1):
            start_minute = start_slot * SLOT_MINUTES
            end_minute = (start_slot + duration_slots) * SLOT_MINUTES
            start_dt = datetime.combine(shooting_day, _time(start_minute), tzinfo=timezone.utc)
            if blocked_until and start_dt < blocked_until:
                continue
            if not _slot_allowed(db, project, scene, reqs, shooting_day, start_minute, end_minute, availability_cache):
                continue
            if original:
                same_day = shooting_day == original.shooting_date
                same_slot = same_day and _time(start_minute) == original.planned_start
                changed_location = scene.location_id != original.location_id
                stability = 0 if same_slot else (1 if same_day else 3)
                if changed_location:
                    stability += 4
            else:
                changed_location = False
                stability = day_idx
            candidates.append(Candidate(
                day_index=day_idx,
                start_slot=start_slot + day_idx * 96,
                end_slot=start_slot + duration_slots + day_idx * 96,
                shooting_date=shooting_day,
                start_time=_time(start_minute),
                end_time=_time(end_minute),
                location_id=scene.location_id,
                stability=stability,
                cost_units=int(round(sum(quantity * rate for _, quantity, _, rate, _ in
                                         _incremental_costs(project, end_minute, original, changed_location)) / 1000)),
            ))
    return candidates


def _solve(
    scene_candidates: dict[str, list[Candidate]],
    objective: str,
    allow_unresolved: bool,
) -> tuple[dict[str, Candidate | None], int]:
    model = cp_model.CpModel()
    choices: dict[tuple[str, int], cp_model.IntVar] = {}
    unresolved: dict[str, cp_model.IntVar] = {}
    for scene_id, candidates in scene_candidates.items():
        vars_for_scene = []
        for index, _candidate in enumerate(candidates):
            var = model.new_bool_var(f"pick_{scene_id}_{index}")
            choices[(scene_id, index)] = var
            vars_for_scene.append(var)
        unresolved_var = model.new_bool_var(f"unresolved_{scene_id}")
        unresolved[scene_id] = unresolved_var
        if allow_unresolved:
            model.add(sum(vars_for_scene) + unresolved_var == 1)
        else:
            model.add(unresolved_var == 0)
            model.add(sum(vars_for_scene) == 1)

    # Optional intervals avoid quadratic pairwise overlap clauses on demo-sized projects.
    intervals = [
        model.new_optional_fixed_size_interval_var(
            candidate.start_slot, candidate.end_slot - candidate.start_slot,
            choices[(sid, idx)], f"slot_{sid}_{idx}"
        )
        for sid, rows in scene_candidates.items() for idx, candidate in enumerate(rows)
    ]
    if intervals:
        model.add_no_overlap(intervals)

    max_end = model.new_int_var(0, 14 * 96 + 96, "finish")
    for sid, candidates in scene_candidates.items():
        for index, candidate in enumerate(candidates):
            model.add(max_end >= candidate.end_slot).only_enforce_if(choices[(sid, index)])

    unresolved_term = sum(unresolved.values()) * UNRESOLVED_PENALTY
    if objective == "FASTEST":
        model.minimize(unresolved_term + max_end * 100 + sum(
            candidate.stability * choices[(sid, idx)]
            for sid, candidates in scene_candidates.items() for idx, candidate in enumerate(candidates)
        ))
    elif objective == "CHEAPEST":
        model.minimize(unresolved_term + sum(
            candidate.cost_units * choices[(sid, idx)]
            for sid, candidates in scene_candidates.items() for idx, candidate in enumerate(candidates)
        ) + max_end)
    else:
        model.minimize(unresolved_term + sum(
            candidate.stability * 1000 * choices[(sid, idx)]
            for sid, candidates in scene_candidates.items() for idx, candidate in enumerate(candidates)
        ) + max_end)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 8
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise AppError(409, "SCHEDULE_INFEASIBLE", "No schedule satisfies the confirmed hard constraints.")
    result: dict[str, Candidate | None] = {}
    for sid, candidates in scene_candidates.items():
        selected = next((candidate for idx, candidate in enumerate(candidates) if solver.value(choices[(sid, idx)])), None)
        result[sid] = selected
    return result, int(solver.objective_value)


def generate_initial_schedule(db: Session, project: Project) -> Schedule:
    if db.scalar(select(Schedule.id).where(Schedule.project_id == project.id, Schedule.status == "ACTIVE")):
        raise AppError(409, "SCHEDULE_ALREADY_ACTIVE", "Use recovery to create a new version of an active schedule.")
    scenes = db.scalars(select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)).all()
    if not scenes:
        raise AppError(409, "SCHEDULE_INFEASIBLE", "Add at least one scene before generating a schedule.")
    reqs = _requirements(db, [scene.id for scene in scenes])
    availability_cache: dict = {}
    candidates = {scene.id: _build_candidates(db, project, scene, reqs[scene.id], None, None, availability_cache) for scene in scenes}
    if any(not values for values in candidates.values()):
        raise AppError(409, "SCHEDULE_INFEASIBLE", "One or more scenes have no valid slot under confirmed constraints.")
    solved, _ = _solve(candidates, "MINIMUM_CHANGE", allow_unresolved=False)
    versions = db.scalars(select(Schedule.version_number).where(Schedule.project_id == project.id)).all()
    schedule = Schedule(project_id=project.id, version_number=max(versions, default=0) + 1, type="INITIAL", status="ACTIVE", approved_at=datetime.now(timezone.utc))
    db.add(schedule)
    db.flush()
    ordered = sorted(((sid, candidate) for sid, candidate in solved.items() if candidate), key=lambda row: row[1].start_slot)
    scene_map = {scene.id: scene for scene in scenes}
    for index, (scene_id, candidate) in enumerate(ordered):
        scene = scene_map[scene_id]
        db.add(ScheduleItem(
            schedule_id=schedule.id, scene_id=scene_id, shooting_date=candidate.shooting_date,
            planned_start=candidate.start_time, planned_end=candidate.end_time,
            planned_duration_minutes=scene.estimated_duration_minutes + scene.setup_minutes,
            location_id=candidate.location_id, order_index=index,
        ))
        scene.status = "READY"
    project.status = "PRODUCTION"
    project.production_state_version += 1
    db.commit()
    db.refresh(schedule)
    return schedule


def generate_recovery_plans(db: Session, project: Project, incident: Incident) -> list[RecoveryPlan]:
    base = db.scalar(select(Schedule).where(Schedule.project_id == project.id, Schedule.status == "ACTIVE").order_by(Schedule.version_number.desc()))
    if not base:
        raise AppError(409, "SCHEDULE_INFEASIBLE", "An active schedule is required before recovery.")
    items = db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == base.id)).all()
    original = {item.scene_id: item for item in items}
    scenes = db.scalars(select(Scene).where(Scene.project_id == project.id).order_by(Scene.scene_number)).all()
    schedulable = [scene for scene in scenes if scene.status not in {"COMPLETED", "IN_PROGRESS"}]
    locked = [scene for scene in scenes if scene.status in {"COMPLETED", "IN_PROGRESS"}]
    reqs = _requirements(db, [scene.id for scene in schedulable])
    impacted_ids = set(db.scalars(select(IncidentImpact.scene_id).where(IncidentImpact.incident_id == incident.id, IncidentImpact.confirmed.is_(True))).all())
    disruption_start = min(
        (datetime.combine(original[sid].shooting_date, original[sid].planned_start, tzinfo=timezone.utc) for sid in impacted_ids if sid in original),
        default=datetime.combine(project.start_date, project.workday_start, tzinfo=timezone.utc),
    )
    blocked_until = disruption_start + timedelta(minutes=incident.estimated_duration_minutes or 180)
    candidates: dict[str, list[Candidate]] = {}
    availability_cache: dict = {}
    for scene in schedulable:
        scene_block = blocked_until if scene.id in impacted_ids else disruption_start
        candidates[scene.id] = _build_candidates(db, project, scene, reqs[scene.id], original.get(scene.id), scene_block, availability_cache)

    # Remove prior unapproved outputs for this incident, preserving audit-worthy approved records.
    old = db.scalars(select(RecoveryPlan).where(RecoveryPlan.incident_id == incident.id, RecoveryPlan.status != "APPROVED")).all()
    for row in old:
        db.delete(row)
    db.flush()

    plans: list[RecoveryPlan] = []
    for objective in ("FASTEST", "CHEAPEST", "MINIMUM_CHANGE"):
        solved, objective_score = _solve(candidates, objective, allow_unresolved=True)
        selected = [candidate for candidate in solved.values() if candidate]
        unresolved_count = sum(candidate is None for candidate in solved.values())
        finish_candidate = max(selected, key=lambda c: c.end_slot) if selected else None
        moved = sum(
            candidate is None
            or scene_id not in original
            or candidate.shooting_date != original[scene_id].shooting_date
            or candidate.start_time != original[scene_id].planned_start
            for scene_id, candidate in solved.items()
        )
        baseline_finish = max((datetime.combine(i.shooting_date, i.planned_end, tzinfo=timezone.utc) for i in items), default=disruption_start)
        finish = datetime.combine(finish_candidate.shooting_date, finish_candidate.end_time, tzinfo=timezone.utc) if finish_candidate else None
        delay = max(0, int((finish - baseline_finish).total_seconds() // 60)) if finish else 0
        status = "DRAFT" if unresolved_count else "VALID"
        plan = RecoveryPlan(
            incident_id=incident.id, base_schedule_id=base.id, base_state_version=project.production_state_version,
            type=objective, status=status, estimated_finish_time=finish, estimated_delay_minutes=delay,
            moved_scene_count=moved, unresolved_scene_count=unresolved_count, score=float(objective_score),
            ai_explanation=_local_explanation(objective, moved, unresolved_count, delay),
        )
        db.add(plan)
        db.flush()
        total_cost = 0.0
        for scene in locked:
            prior = original.get(scene.id)
            if prior:
                db.add(RecoveryPlanItem(
                    recovery_plan_id=plan.id, scene_id=scene.id, shooting_date=prior.shooting_date,
                    start_time=prior.planned_start, end_time=prior.planned_end, location_id=prior.location_id,
                    action="KEEP", reason="Completed or in-progress scene remains locked.",
                ))
        for scene in schedulable:
            candidate = solved[scene.id]
            prior = original.get(scene.id)
            if candidate is None:
                db.add(RecoveryPlanItem(recovery_plan_id=plan.id, scene_id=scene.id, action="UNRESOLVED", reason="No slot satisfies all confirmed hard constraints."))
                continue
            same = prior and candidate.shooting_date == prior.shooting_date and candidate.start_time == prior.planned_start
            action = "KEEP" if same else "MOVE"
            db.add(RecoveryPlanItem(
                recovery_plan_id=plan.id, scene_id=scene.id, shooting_date=candidate.shooting_date,
                start_time=candidate.start_time, end_time=candidate.end_time, location_id=candidate.location_id,
                action=action, reason="Kept in place." if same else f"Moved to satisfy the {objective.lower().replace('_', ' ')} objective and hard constraints.",
            ))
            changed_location = bool(prior and candidate.location_id != prior.location_id)
            end_minute = _minutes(candidate.end_time)
            for category, quantity, unit, rate, description in _incremental_costs(project, end_minute, prior, changed_location):
                amount = quantity * rate
                total_cost += amount
                db.add(RecoveryCostItem(
                    recovery_plan_id=plan.id, category=category, quantity=quantity, unit=unit,
                    rate=rate, amount=amount, description=f"Scene {scene.scene_number}: {description}.",
                ))
        plan.estimated_extra_cost = total_cost
        plans.append(plan)
    db.commit()
    return plans


def validate_recovery_plan(db: Session, project: Project, plan: RecoveryPlan) -> None:
    if plan.status != "VALID" or plan.unresolved_scene_count:
        raise AppError(409, "UNRESOLVED_SCENES", "A draft or unresolved recovery plan cannot be approved.")
    if plan.base_state_version != project.production_state_version:
        raise AppError(409, "RECOVERY_PLAN_OUTDATED", "Production conditions have changed.")
    base = db.get(Schedule, plan.base_schedule_id)
    if not base or base.project_id != project.id or base.status != "ACTIVE":
        raise AppError(409, "RECOVERY_PLAN_OUTDATED", "The base schedule is no longer active.")
    items = db.scalars(select(RecoveryPlanItem).where(RecoveryPlanItem.recovery_plan_id == plan.id)).all()
    if any(item.action == "UNRESOLVED" or not item.shooting_date or not item.start_time or not item.end_time for item in items):
        raise AppError(409, "UNRESOLVED_SCENES", "Every scene must have a valid slot before approval.")
    scene_ids = [item.scene_id for item in items]
    scenes = {scene.id: scene for scene in db.scalars(select(Scene).where(Scene.id.in_(scene_ids), Scene.project_id == project.id)).all()}
    if len(scenes) != len(set(scene_ids)):
        raise AppError(409, "RECOVERY_PLAN_INVALID", "Recovery plan contains an unknown scene.")
    reqs = _requirements(db, scene_ids)
    availability_cache: dict = {}
    intervals: list[tuple[datetime, datetime, str]] = []
    base_items = {item.scene_id: item for item in db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == base.id)).all()}
    for item in items:
        scene = scenes[item.scene_id]
        if scene.status in {"COMPLETED", "IN_PROGRESS"}:
            previous = base_items.get(scene.id)
            if not previous or item.shooting_date != previous.shooting_date or item.start_time != previous.planned_start:
                raise AppError(409, "RECOVERY_PLAN_INVALID", "Completed and in-progress scenes must remain fixed.")
        start_minute, end_minute = _minutes(item.start_time), _minutes(item.end_time)
        if end_minute <= start_minute or not _slot_allowed(db, project, scene, reqs.get(scene.id, []), item.shooting_date, start_minute, end_minute, availability_cache):
            raise AppError(409, "RECOVERY_PLAN_INVALID", "A planned slot no longer satisfies confirmed hard constraints.", {"scene_id": scene.id})
        start_dt = datetime.combine(item.shooting_date, item.start_time, tzinfo=timezone.utc)
        end_dt = datetime.combine(item.shooting_date, item.end_time, tzinfo=timezone.utc)
        intervals.append((start_dt, end_dt, scene.id))
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise AppError(409, "RECOVERY_PLAN_INVALID", "Recovery plan contains overlapping scenes.")


def _local_explanation(objective: str, moved: int, unresolved: int, delay: int) -> str:
    labels = {"FASTEST": "earliest finish", "CHEAPEST": "lowest calculated incremental cost", "MINIMUM_CHANGE": "least schedule disruption"}
    result = f"Prioritizes {labels[objective]}; moves {moved} scene(s) with an estimated {delay}-minute delay."
    if unresolved:
        result += f" {unresolved} scene(s) remain unresolved, so this plan cannot be approved."
    return result
