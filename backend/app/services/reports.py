from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import PreventRun, Project, RecoveryPlan, RecoveryPlanItem, Scene, Schedule, ScheduleItem
from app.services.serializers import parse_json


BRAND = colors.HexColor("#ef5a3c")
INK = colors.HexColor("#17202b")
MUTED = colors.HexColor("#667085")


def _export_path(project_id: str, stem: str) -> Path:
    directory = get_settings().data_dir / "projects" / project_id / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"


def _doc(path: Path, title: str, landscape_mode: bool = False) -> tuple[SimpleDocTemplate, list, dict]:
    styles = getSampleStyleSheet()
    styles["Title"].textColor = INK
    styles["Heading2"].textColor = BRAND
    page = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(str(path), pagesize=page, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=title)
    story = [Paragraph("SETRESCUE AI", styles["Heading2"]), Paragraph(title, styles["Title"]), Spacer(1, 6 * mm)]
    return doc, story, styles


def _table(data: list[list[object]], widths: list[float] | None = None) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def prevent_report(db: Session, project: Project) -> Path:
    run = db.scalar(select(PreventRun).where(PreventRun.project_id == project.id).order_by(PreventRun.started_at.desc()))
    if not run:
        raise AppError(409, "PREVENT_NOT_READY", "Run PREVENT before exporting its report.")
    path = _export_path(project.id, "prevent-readiness")
    doc, story, styles = _doc(path, f"PREVENT Readiness Report — {project.name}")
    story.extend([
        Paragraph(f"Readiness: <b>{run.overall_score:.1f}/100</b> · Status: <b>{run.status.replace('_', ' ')}</b>", styles["Heading2"]),
        Spacer(1, 4 * mm),
    ])
    scores = parse_json(run.category_scores_json, {})
    story.append(_table([["Category", "Score"]] + [[key.replace("_", " ").title(), f"{value:.1f}"] for key, value in scores.items()], [120 * mm, 35 * mm]))
    story.extend([Spacer(1, 6 * mm), Paragraph("Open findings", styles["Heading2"])])
    issues = [["Severity", "Finding", "Recommended action"]]
    for issue in run.issues:
        if issue.status == "OPEN":
            issues.append([issue.severity, Paragraph(issue.title, styles["BodyText"]), Paragraph(issue.recommended_action, styles["BodyText"])])
    story.append(_table(issues if len(issues) > 1 else issues + [["—", "No open findings", "—"]], [25 * mm, 70 * mm, 65 * mm]))
    doc.build(story)
    return path


def recovery_report(db: Session, project: Project, incident_id: str | None = None) -> Path:
    statement = select(RecoveryPlan).join_from(RecoveryPlan, Schedule, RecoveryPlan.base_schedule_id == Schedule.id).where(Schedule.project_id == project.id)
    if incident_id:
        statement = statement.where(RecoveryPlan.incident_id == incident_id)
    plans = db.scalars(statement.order_by(RecoveryPlan.created_at.desc())).all()
    if not plans:
        raise AppError(409, "RECOVERY_PLAN_INVALID", "Generate recovery plans before exporting comparison.")
    latest_incident = plans[0].incident_id
    plans = [plan for plan in plans if plan.incident_id == latest_incident]
    path = _export_path(project.id, "recovery-comparison")
    doc, story, styles = _doc(path, f"Recovery Plan Comparison — {project.name}", landscape_mode=True)
    data = [["Objective", "Status", "Finish", "Delay", "Extra cost", "Moved", "Unresolved"]]
    for plan in sorted(plans, key=lambda item: item.type):
        data.append([
            plan.type.replace("_", " "), plan.status,
            plan.estimated_finish_time.strftime("%d %b %H:%M") if plan.estimated_finish_time else "—",
            f"{plan.estimated_delay_minutes} min", f"{project.currency} {plan.estimated_extra_cost:,.0f}",
            plan.moved_scene_count, plan.unresolved_scene_count,
        ])
    story.append(_table(data, [35 * mm, 25 * mm, 38 * mm, 25 * mm, 40 * mm, 22 * mm, 25 * mm]))
    for plan in sorted(plans, key=lambda item: item.type):
        story.extend([Spacer(1, 7 * mm), Paragraph(plan.type.replace("_", " ").title(), styles["Heading2"]), Paragraph(plan.ai_explanation or "Deterministic plan generated without AI explanation.", styles["BodyText"])])
    doc.build(story)
    return path


def call_sheet_report(db: Session, project: Project, schedule: Schedule) -> Path:
    items = db.scalars(select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id).order_by(ScheduleItem.shooting_date, ScheduleItem.order_index)).all()
    scene_ids = [item.scene_id for item in items]
    scenes = {scene.id: scene for scene in db.scalars(select(Scene).where(Scene.id.in_(scene_ids))).all()} if scene_ids else {}
    path = _export_path(project.id, f"call-sheet-v{schedule.version_number}")
    doc, story, styles = _doc(path, f"Updated Call Sheet V{schedule.version_number} — {project.name}")
    current_day = None
    rows: list[list[object]] = []
    for item in items:
        if current_day != item.shooting_date:
            if rows:
                story.append(_table([["Start", "End", "Scene", "Description", "Minutes"]] + rows, [23 * mm, 23 * mm, 18 * mm, 80 * mm, 20 * mm]))
                story.append(PageBreak())
            current_day = item.shooting_date
            story.append(Paragraph(current_day.strftime("%A, %d %B %Y"), styles["Heading2"]))
            story.append(Spacer(1, 3 * mm))
            rows = []
        scene = scenes.get(item.scene_id)
        rows.append([item.planned_start.strftime("%H:%M"), item.planned_end.strftime("%H:%M"), scene.scene_number if scene else "—", Paragraph(scene.title if scene else "Unknown", styles["BodyText"]), item.planned_duration_minutes])
    if rows:
        story.append(_table([["Start", "End", "Scene", "Description", "Minutes"]] + rows, [23 * mm, 23 * mm, 18 * mm, 80 * mm, 20 * mm]))
    doc.build(story)
    return path
