from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from conftest import unwrap


def _workbook(*rows) -> bytes:
    wb = Workbook()
    sheet = wb.active
    for row in rows:
        sheet.append(list(row))
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    return buffer.getvalue()


def test_tabular_import_is_preview_first_and_idempotent(client):
    project = unwrap(client.post('/api/projects', json={
        'name': 'Sheet import', 'start_date': '2026-10-09', 'end_date': '2026-10-10',
        'budget': 1000, 'currency': 'IDR', 'workday_start': '08:00:00', 'workday_end': '18:00:00',
    }), 201)
    pid = project['id']
    script = _workbook(('Scene', 'Title', 'Description', 'Minutes'), ('01', 'Gate', 'EXT. GATE - DAY', 45), ('02', 'Inside', 'INT. DAY', 30))
    unwrap(client.post(f'/api/projects/{pid}/documents', data={'document_type': 'SCRIPT'},
                       files={'file': ('script.xlsx', script, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}), 201)
    docs = unwrap(client.get(f'/api/projects/{pid}/documents'))
    doc_id = docs[0]['id']
    preview = unwrap(client.get(f'/api/projects/{pid}/documents/{doc_id}/import-preview'))
    assert preview['count'] == 2
    assert not unwrap(client.get(f'/api/projects/{pid}'))['scenes']  # No silent mutations
    response = unwrap(client.post(f'/api/projects/{pid}/documents/{doc_id}/apply-import', json={'version_id': preview['version_id']}))
    assert response['created'] == 2
    repeat = unwrap(client.post(f'/api/projects/{pid}/documents/{doc_id}/apply-import', json={'version_id': preview['version_id']}))
    assert repeat['created'] == 0
    assert repeat['skipped'] == 2

    shots = _workbook(('Scene', 'Shot', 'Description', 'Frame', 'Movement', 'Minutes'),
                       ('01', '01.1', 'Wide', 'WS', 'Static', 10), ('02', '02.1', 'Medium', 'MS', 'Pan', 12))
    unwrap(client.post(f'/api/projects/{pid}/documents', data={'document_type': 'SHOT_LIST'},
                       files={'file': ('shots.xlsx', shots, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}), 201)
    docs = unwrap(client.get(f'/api/projects/{pid}/documents'))
    shots_id = next(doc['id'] for doc in docs if doc['type'] == 'SHOT_LIST')
    shots_preview = unwrap(client.get(f'/api/projects/{pid}/documents/{shots_id}/import-preview'))
    assert unwrap(client.post(f'/api/projects/{pid}/documents/{shots_id}/apply-import',
                              json={'version_id': shots_preview['version_id']}))['created'] == 2
    detail = unwrap(client.get(f'/api/projects/{pid}'))
    assert sum(len(scene['shots']) for scene in detail['scenes']) == 2


def test_tabular_import_rejects_stale_version(client):
    project = unwrap(client.post('/api/projects', json={
        'name': 'Stale import', 'start_date': '2026-10-09', 'end_date': '2026-10-10',
        'budget': 1000, 'currency': 'IDR', 'workday_start': '08:00:00', 'workday_end': '18:00:00',
    }), 201)
    pid = project['id']
    content = _workbook(('Scene', 'Title'), ('01', 'Gate'))
    for _ in range(2):
        unwrap(client.post(f'/api/projects/{pid}/documents', data={'document_type': 'SCRIPT'},
                           files={'file': ('script.xlsx', content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}), 201)
        docs = unwrap(client.get(f'/api/projects/{pid}/documents'))
        doc = docs[0]
        if doc['current_version'] == 1:
            stale_version_id = unwrap(client.get(f'/api/projects/{pid}/documents/{doc["id"]}/import-preview'))['version_id']
    response = client.post(f'/api/projects/{pid}/documents/{doc["id"]}/apply-import', json={'version_id': stale_version_id})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'DOCUMENT_VERSION_OUTDATED'


def test_confirmed_shot_requirement_is_visible_and_blocks_prevent(client):
    project = unwrap(client.post('/api/demo/realistic'), 201)
    pid = project['id']
    detail = unwrap(client.get(f'/api/projects/{pid}'))
    first_shot = detail['scenes'][0]['shots'][0]['id']
    requirement = unwrap(client.post(f'/api/projects/{pid}/requirements', json={
        'shot_id': first_shot,
        'category': 'AUDIO', 'name': 'Shot microphone failure',
        'is_hard_constraint': True, 'confirmation_status': 'CONFIRMED',
        'fulfillment_status': 'FAILED', 'source': 'MANUAL',
    }), 201)
    detail = unwrap(client.get(f'/api/projects/{pid}'))
    assert any(req['id'] == requirement['id'] for req in detail['scenes'][0]['requirements'])
    readiness = unwrap(client.post(f'/api/projects/{pid}/prevent/run'))
    assert readiness['status'] == 'NOT_READY'
    assert any('Shot microphone failure' in issue['title'] for issue in readiness['issues'])


def test_unavailable_resource_window_overrides_existing_available_window(client):
    from datetime import date, time
    from app.database import SessionLocal
    from app.engines.scheduler import _available

    project = unwrap(client.post('/api/demo/realistic'), 201)
    pid = project['id']
    detail = unwrap(client.get(f'/api/projects/{pid}'))
    camera = next(row for row in detail['resources'] if row['subtype'] == 'CAMERA')
    today = date.fromisoformat(project['start_date'])
    with SessionLocal() as db:
        assert _available(db, camera['id'], today, 8 * 60, 9 * 60)
    unwrap(client.post(f'/api/projects/{pid}/resources/{camera["id"]}/availability', json={
        'date': project['start_date'], 'available_from': '08:30:00',
        'available_until': '09:30:00', 'status': 'UNAVAILABLE',
    }), 201)
    with SessionLocal() as db:
        assert not _available(db, camera['id'], today, 8 * 60, 9 * 60)
        assert _available(db, camera['id'], today, 10 * 60, 11 * 60)
