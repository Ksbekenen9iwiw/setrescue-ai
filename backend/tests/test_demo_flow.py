from __future__ import annotations

from conftest import unwrap


def test_realistic_demo_prevent_schedule_and_recovery(client):
    project = unwrap(client.post("/api/demo/realistic"), 201)
    project_id = project["id"]

    detail = unwrap(client.get(f"/api/projects/{project_id}"))
    assert len(detail["scenes"]) == 8
    assert sum(len(scene["shots"]) for scene in detail["scenes"]) == 20
    assert len(detail["documents"]) == 3

    prevent = unwrap(client.post(f"/api/projects/{project_id}/prevent/run"))
    assert prevent["status"] in {"NEEDS_REVIEW", "READY"}
    assert prevent["overall_score"] >= 0
    assert any(issue["title"].startswith("Confirmation needed") for issue in prevent["issues"])

    schedule = unwrap(client.post(f"/api/projects/{project_id}/schedule/generate"))
    assert schedule["status"] == "ACTIVE"
    assert schedule["version_number"] == 1
    assert len(schedule["items"]) == 8

    scene = detail["scenes"][0]
    location = next(resource for resource in detail["resources"] if resource["id"] == scene["location_id"])
    unwrap(client.post(f"/api/projects/{project_id}/weather/manual", json={
        "location_id": location["id"], "temperature": 27, "rain_probability": 100, "weather_code": "HEAVY_RAIN",
    }), 201)
    incident = unwrap(client.post(f"/api/projects/{project_id}/incidents", json={
        "category": "WEATHER", "scene_id": scene["id"], "title": "Unexpected heavy rain",
        "description": "Exterior blocked and dialogue has rain noise.", "estimated_duration_minutes": 180,
        "affected_scene_ids": [scene["id"]], "impact_type": "BLOCKED",
    }), 201)
    generated = unwrap(client.post(f"/api/incidents/{incident['id']}/recovery/generate", json={"priority": "TIME"}))
    assert {plan["type"] for plan in generated["plans"]} == {"FASTEST", "CHEAPEST", "MINIMUM_CHANGE"}
    assert generated["recommended_type"] == "FASTEST"

    valid = next((plan for plan in generated["plans"] if plan["status"] == "VALID"), None)
    assert valid is not None
    approved = unwrap(client.post(f"/api/recovery-plans/{valid['id']}/approve"))
    assert approved["schedule"]["version_number"] == 2
    assert approved["schedule"]["status"] == "ACTIVE"

    schedules = unwrap(client.get(f"/api/projects/{project_id}/schedule"))
    assert {row["status"] for row in schedules} == {"ACTIVE", "SUPERSEDED"}

    pdf = client.get(f"/api/projects/{project_id}/reports/call-sheet/{approved['schedule']['id']}")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_outdated_recovery_plan_is_rejected(client):
    project = unwrap(client.post("/api/demo/realistic"), 201)
    project_id = project["id"]
    detail = unwrap(client.get(f"/api/projects/{project_id}"))
    unwrap(client.post(f"/api/projects/{project_id}/schedule/generate"))
    scene = detail["scenes"][0]
    incident = unwrap(client.post(f"/api/projects/{project_id}/incidents", json={
        "category": "OTHER", "scene_id": scene["id"], "title": "Short interruption",
        "description": "Verified set interruption.", "estimated_duration_minutes": 30,
        "affected_scene_ids": [scene["id"]], "impact_type": "BLOCKED",
    }), 201)
    generated = unwrap(client.post(f"/api/incidents/{incident['id']}/recovery/generate", json={"priority": "STABILITY"}))
    valid = next(plan for plan in generated["plans"] if plan["status"] == "VALID")

    unwrap(client.patch(f"/api/projects/{project_id}", json={"description": "State changed after plan generation."}))
    response = client.post(f"/api/recovery-plans/{valid['id']}/approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RECOVERY_PLAN_OUTDATED"
