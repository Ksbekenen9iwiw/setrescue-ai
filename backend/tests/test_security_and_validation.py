from __future__ import annotations

from conftest import unwrap


def test_upload_rejects_extension_signature_mismatch(client):
    project = unwrap(client.post("/api/projects", json={
        "name": "Upload test", "start_date": "2026-10-09", "end_date": "2026-10-10",
        "budget": 1000, "currency": "IDR", "workday_start": "08:00:00", "workday_end": "18:00:00",
    }), 201)
    response = client.post(
        f"/api/projects/{project['id']}/documents",
        data={"document_type": "SCRIPT"},
        files={"file": ("script.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DOCUMENT_UNSUPPORTED"


def test_cross_project_resource_reference_is_rejected(client):
    first = unwrap(client.post("/api/demo/realistic"), 201)
    second = unwrap(client.post("/api/projects", json={
        "name": "Other production", "start_date": "2026-10-09", "end_date": "2026-10-10",
        "budget": 1000, "currency": "IDR", "workday_start": "08:00:00", "workday_end": "18:00:00",
    }), 201)
    detail = unwrap(client.get(f"/api/projects/{first['id']}"))
    foreign_location = next(resource for resource in detail["resources"] if resource["type"] == "LOCATION")
    response = client.post(f"/api/projects/{second['id']}/scenes", json={
        "scene_number": "1", "title": "Cross-boundary scene", "location_id": foreign_location["id"],
        "estimated_duration_minutes": 20, "setup_minutes": 5, "priority": 3,
    })
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_ai_key_is_never_returned(client, monkeypatch):
    monkeypatch.setattr("app.api.router.validate_external_https_url", lambda url: url.rstrip("/"))
    saved = unwrap(client.put("/api/settings/ai", json={
        "provider_name": "test", "base_url": "https://example.com/v1", "model": "model-a",
        "api_key": "super-secret-key", "enabled": True,
    }))
    assert "api_key" not in saved
    assert "encrypted_api_key" not in saved
    assert saved["api_key_configured"] is True
    loaded = unwrap(client.get("/api/settings/ai"))
    assert "super-secret-key" not in str(loaded)
    assert "encrypted_api_key" not in loaded


def test_unresolved_plan_cannot_be_approved(client):
    project = unwrap(client.post("/api/demo/realistic"), 201)
    project_id = project["id"]
    detail = unwrap(client.get(f"/api/projects/{project_id}"))
    unwrap(client.post(f"/api/projects/{project_id}/schedule/generate"))
    camera = next(resource for resource in detail["resources"] if resource["subtype"] == "CAMERA")
    for day in (project["start_date"], project["end_date"]):
        unwrap(client.post(f"/api/projects/{project_id}/resources/{camera['id']}/availability", json={
            "date": day, "available_from": "00:00:00", "available_until": "23:59:00", "status": "UNAVAILABLE", "notes": "Stress test",
        }), 201)
    scene = detail["scenes"][0]
    incident = unwrap(client.post(f"/api/projects/{project_id}/incidents", json={
        "category": "EQUIPMENT_FAILURE", "resource_id": camera["id"], "scene_id": scene["id"],
        "title": "Camera unavailable", "description": "No replacement camera.", "estimated_duration_minutes": 1440,
        "affected_scene_ids": [scene["id"]], "impact_type": "BLOCKED",
    }), 201)
    generated = unwrap(client.post(f"/api/incidents/{incident['id']}/recovery/generate", json={"priority": "COST"}))
    draft = next(plan for plan in generated["plans"] if plan["status"] == "DRAFT")
    response = client.post(f"/api/recovery-plans/{draft['id']}/approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "UNRESOLVED_SCENES"
