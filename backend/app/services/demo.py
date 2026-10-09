from __future__ import annotations

import hashlib
from datetime import date, time, timedelta
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Document, DocumentVersion, Project, Requirement, Resource, ResourceAvailability, Scene, Shot,
)


SCENE_DATA = [
    ("01", "Rain at the Gate", "EXT. HOUSE GATE - DAY. Arga arrives in clear weather.", 45, 15, "outdoor"),
    ("02", "Kitchen Dialogue", "INT. KITCHEN - DAY. Maya confronts Arga.", 55, 20, "indoor"),
    ("03", "Letter Insert", "INT. STUDY - DAY. Close inserts of a handwritten letter.", 25, 10, "indoor"),
    ("04", "Street Crossing", "EXT. STREET - DAY. Arga crosses through traffic.", 40, 15, "street"),
    ("05", "Silent Hallway", "INT. HALLWAY - DAY. Maya walks toward the study.", 35, 15, "indoor"),
    ("06", "Garden Memory", "EXT. GARDEN - GOLDEN HOUR. A childhood memory.", 45, 20, "garden"),
    ("07", "Night Confession", "INT. LIVING ROOM - NIGHT. The truth is revealed.", 60, 25, "indoor"),
    ("08", "Final Door", "EXT. HOUSE GATE - MORNING. Arga leaves.", 35, 15, "outdoor"),
]


def _write_demo_workbook(project_id: str, kind: str, rows: list[list[object]]) -> tuple[str, str]:
    directory = get_settings().data_dir / "projects" / project_id / "documents"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"demo-{kind.lower().replace('_', '-')}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = kind.title().replace("_", " ")[:31]
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    content = path.read_bytes()
    return str(path.resolve()), hashlib.sha256(content).hexdigest()


def _add_document(db: Session, project_id: str, kind: str, rows: list[list[object]], extracted: str) -> None:
    path, digest = _write_demo_workbook(project_id, kind, rows)
    document = Document(project_id=project_id, type=kind, current_version=1)
    db.add(document)
    db.flush()
    db.add(DocumentVersion(
        document_id=document.id, version_number=1, original_filename=f"Project_Rainfall_{kind}.xlsx",
        local_path=path, file_type=".xlsx", file_hash=digest, extracted_text=extracted,
    ))


def load_realistic_demo(db: Session) -> Project:
    today = date.today()
    project = Project(
        name="Project Rainfall", description="Two-day narrative shoot with a weather disruption recovery scenario.",
        start_date=today, end_date=today + timedelta(days=1), budget=85_000_000, currency="IDR",
        workday_start=time(8, 0), workday_end=time(18, 0), default_overtime_rate=300_000,
        default_transport_rate=500_000, default_location_extension_rate=2_000_000,
    )
    db.add(project)
    db.flush()

    locations: dict[str, Resource] = {}
    for key, name, address, lat, lon in [
        ("outdoor", "House Gate", "Kemang, Jakarta Selatan", -6.2607, 106.8133),
        ("indoor", "Family House Interior", "Kemang, Jakarta Selatan", -6.2607, 106.8133),
        ("street", "Quiet Street", "Cilandak, Jakarta Selatan", -6.2890, 106.7920),
        ("garden", "Community Garden", "Ragunan, Jakarta Selatan", -6.3050, 106.8200),
    ]:
        resource = Resource(
            project_id=project.id, name=name, type="LOCATION", subtype="SET", address=address,
            latitude=lat, longitude=lon, default_cost=2_500_000, extension_rate=1_500_000,
        )
        db.add(resource)
        db.flush()
        locations[key] = resource

    resources: dict[str, Resource] = {}
    resource_rows = [
        ("arga", "Raka / Arga", "CAST", "LEAD", "raka@example.test", 3_000_000),
        ("maya", "Dina / Maya", "CAST", "LEAD", "dina@example.test", 3_000_000),
        ("director", "Nadia Putri", "CREW", "DIRECTOR", "nadia@example.test", 2_500_000),
        ("camera", "A-Camera Package", "EQUIPMENT", "CAMERA", None, 2_000_000),
        ("lighting", "LED Lighting Package", "EQUIPMENT", "LIGHTING", None, 1_500_000),
        ("sound", "Location Sound Kit", "EQUIPMENT", "AUDIO", None, 1_000_000),
    ]
    for key, name, type_, subtype, email, cost in resource_rows:
        resource = Resource(
            project_id=project.id, name=name, type=type_, subtype=subtype, email=email,
            default_cost=cost, overtime_rate=300_000 if type_ in {"CAST", "CREW"} else None,
        )
        db.add(resource)
        db.flush()
        resources[key] = resource

    for resource in [*resources.values(), *locations.values()]:
        for offset in range(2):
            available_from = time(13, 0) if resource.id == resources["lighting"].id and offset == 0 else time(7, 0)
            db.add(ResourceAvailability(
                resource_id=resource.id, date=today + timedelta(days=offset), available_from=available_from,
                available_until=time(21, 0), status="AVAILABLE",
                notes="Lighting delivery arrives at 13:00." if available_from == time(13, 0) else "",
            ))

    scenes: list[Scene] = []
    shot_rows: list[list[object]] = [["Scene", "Shot", "Description", "Frame", "Movement", "Minutes"]]
    script_lines: list[str] = []
    for scene_index, (number, title, description, duration, setup, location_key) in enumerate(SCENE_DATA):
        scene = Scene(
            project_id=project.id, scene_number=number, title=title, description=description,
            location_id=locations[location_key].id, estimated_duration_minutes=duration,
            setup_minutes=setup, priority=5 if number in {"01", "02", "07"} else 3,
        )
        db.add(scene)
        db.flush()
        scenes.append(scene)
        script_lines.append(f"SCENE {number}: {title}\n{description}")
        shot_count = 3 if scene_index < 4 else 2
        for shot_index in range(1, shot_count + 1):
            shot = Shot(
                scene_id=scene.id, shot_number=f"{number}.{shot_index}",
                description=f"{title} coverage {shot_index}", frame_size=["WS", "MS", "CU"][shot_index % 3],
                camera_movement="Static" if shot_index % 2 else "Dolly", estimated_duration_minutes=max(5, duration // shot_count), setup_minutes=5,
            )
            db.add(shot)
            shot_rows.append([number, shot.shot_number, shot.description, shot.frame_size, shot.camera_movement, shot.estimated_duration_minutes])

        # Baseline production dependencies are confirmed and deterministic.
        db.add_all([
            Requirement(scene_id=scene.id, category="EQUIPMENT", name="A-Camera available", required_resource_id=resources["camera"].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"),
            Requirement(scene_id=scene.id, category="AUDIO", name="Location sound kit available", required_resource_id=resources["sound"].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"),
            Requirement(scene_id=scene.id, category="LOCATION", name=f"{locations[location_key].name} available", required_resource_id=locations[location_key].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"),
        ])
        if number in {"01", "02", "04", "06", "07", "08"}:
            db.add(Requirement(scene_id=scene.id, category="CAST", name="Arga present", required_resource_id=resources["arga"].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"))
        if number in {"02", "05", "06", "07"}:
            db.add(Requirement(scene_id=scene.id, category="CAST", name="Maya present", required_resource_id=resources["maya"].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"))
        if number in {"02", "05", "07"}:
            db.add(Requirement(scene_id=scene.id, category="LIGHTING", name="LED lighting package", required_resource_id=resources["lighting"].id, is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"))
        if location_key in {"outdoor", "street", "garden"}:
            db.add(Requirement(scene_id=scene.id, category="WEATHER", name="Dry outdoor conditions", required_value="DRY", is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"))

    # Indoor dialogue cannot be used while current rain noise is operationally reported.
    db.add(Requirement(scene_id=scenes[1].id, category="AUDIO", name="No heavy rain noise", required_value="NO_RAIN", is_hard_constraint=True, source="DOCUMENT", confirmation_status="CONFIRMED", fulfillment_status="SATISFIED"))
    # One suggestion demonstrates that AI never creates a hard constraint without review.
    db.add(Requirement(scene_id=scenes[0].id, category="CONTINGENCY", name="Weather-independent fallback scene", required_value="Scene 03", is_hard_constraint=False, source="AI_SUGGESTED", confirmation_status="SUGGESTED", fulfillment_status="UNKNOWN", confidence=0.91))

    _add_document(db, project.id, "SCRIPT", [["Scene", "Title", "Description"]] + [[row[0], row[1], row[2]] for row in SCENE_DATA], "\n\n".join(script_lines))
    _add_document(db, project.id, "SHOT_LIST", shot_rows, "\n".join(" | ".join(map(str, row)) for row in shot_rows))
    call_rows = [["Day", "Start", "Scene", "Location"], [1, "08:00", "01", "House Gate"], [1, "09:15", "03", "Family House Interior"], [1, "13:00", "02", "Family House Interior"], [2, "08:00", "04", "Quiet Street"]]
    _add_document(db, project.id, "CALL_SHEET", call_rows, "\n".join(" | ".join(map(str, row)) for row in call_rows))

    db.commit()
    db.refresh(project)
    return project
