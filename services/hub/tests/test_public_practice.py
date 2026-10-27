import hashlib
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def practice(tmp_path, monkeypatch):
    root = Path(os.environ['WAIKE_ROOT'])
    monkeypatch.setenv('WAIKE_ROOT', str(root))
    app = create_app(db_path=tmp_path/'practice.sqlite', seed=False)
    return TestClient(app), root

def submission(root, track='DIGITAL_CONFIDENCE', unit=1):
    manifest = json.loads((root/f'curriculum/canonical_packages/{track}/PACKAGE_MANIFEST.v1.json').read_text())
    folder = root/'curriculum/digital_rc'/manifest['package_dir']
    raw = (folder/f'quizzes/q{unit:02d}.json').read_bytes()
    q = json.loads(raw)
    keys = json.loads((folder/'instructor/answer_keys.json').read_text())['quizzes'][q['quiz_id']]
    return dict(responses={k['id']:k['answer_index'] for k in keys}, quiz_sha256=hashlib.sha256(raw).hexdigest())

def test_all_18_canonical_quizzes_grade_on_server_without_identity(practice):
    client, root = practice
    registry = json.loads((root/'curriculum/taxonomy/eighteen_tracks.json').read_text())
    for track in registry['tracks']:
        for unit in range(1,11):
            payload = submission(root, track['track_id'], unit)
            response = client.post(f"/api/v1/public-practice/{track['track_id']}/{unit}", json=payload)
            assert response.status_code == 200, (track['track_id'],unit,response.text)
            body = response.json()
            assert body['earned'] == body['possible'] > 0
            assert body['persisted'] is False
            assert 'answer_index' not in response.text

def test_partial_wrong_and_version_mismatch(practice):
    client, root = practice
    payload = submission(root)
    first = next(iter(payload['responses']))
    payload['responses'][first] = (payload['responses'][first]+1)%4
    response = client.post('/api/v1/public-practice/DIGITAL_CONFIDENCE/1', json=payload)
    assert response.json()['earned'] == response.json()['possible']-1
    assert not response.json()['feedback'][0]['correct']
    payload['quiz_sha256'] = '0'*64
    assert client.post('/api/v1/public-practice/DIGITAL_CONFIDENCE/1', json=payload).status_code == 409
    payload = submission(root)
    del payload['responses'][first]
    assert client.post('/api/v1/public-practice/DIGITAL_CONFIDENCE/1', json=payload).status_code == 422

@pytest.mark.parametrize('bad', [-1,100,True,'1'])
def test_invalid_choices(practice, bad):
    client, root = practice
    payload = submission(root); payload['responses'][next(iter(payload['responses']))] = bad
    assert client.post('/api/v1/public-practice/DIGITAL_CONFIDENCE/1', json=payload).status_code == 422

def test_unknown_track_and_private_records(practice):
    client, root = practice
    payload = submission(root)
    assert client.post('/api/v1/public-practice/UNKNOWN/1', json=payload).status_code == 404
    assert client.post('/api/v1/public-practice/DIGITAL_CONFIDENCE/11', json=payload).status_code == 404
    assert client.get('/api/v1/quizzes/GENERAL_IT-q01/answer-key').status_code in (401,403)
