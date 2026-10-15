"""Stateless formative practice. No gradebook, identity, or attempt records.

Uses canonical quiz items and private keys from the configured curriculum root.
The public bundle contains stems only. Authenticated assessment remains in the
existing ActivityEngine and authorization-scoped routes.
"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

router = APIRouter(prefix='/api/v1/public-practice', tags=['formative practice'])

class Responses(BaseModel):
    model_config = ConfigDict(extra='forbid')
    responses: dict[str, StrictInt] = Field(min_length=1, max_length=60)
    quiz_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def source(root: Path | None, track: str, unit: int):
    if root is None:
        raise HTTPException(503, 'Canonical curriculum is not configured')
    root = Path(root)
    registry = json.loads((root/'curriculum/taxonomy/eighteen_tracks.json').read_text())
    if track not in {t['track_id'] for t in registry['tracks']} or not 1 <= unit <= 10:
        raise HTTPException(404, 'Unknown course or unit')
    manifest = json.loads((root/f'curriculum/canonical_packages/{track}/PACKAGE_MANIFEST.v1.json').read_text())
    folder = (root/'curriculum/digital_rc'/manifest['package_dir']).resolve()
    if not folder.is_relative_to((root/'curriculum/digital_rc').resolve()):
        raise HTTPException(503, 'Invalid canonical package')
    return folder

@router.post('/{track}/{unit}')
def evaluate(track: str, unit: int, payload: Responses, request: Request):
    import hashlib
    folder = source(request.app.state.waike_root, track, unit)
    path = folder/f'quizzes/q{unit:02d}.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != payload.quiz_sha256:
        raise HTTPException(409, 'Quiz version changed. Refresh the course before retrying.')
    quiz = json.loads(raw)
    keys = json.loads((folder/'instructor/answer_keys.json').read_text())['quizzes'].get(quiz['quiz_id'])
    if not isinstance(keys, list):
        raise HTTPException(503, 'Practice evaluation is unavailable for this quiz')
    lookup = {k['id']:k for k in keys}
    items = quiz['items']
    if set(payload.responses) != {i['id'] for i in items}:
        raise HTTPException(422, 'Answer every question exactly once')
    feedback = []
    for item in items:
        value = payload.responses[item['id']]
        if item.get('kind') != 'mcq' or not 0 <= value < len(item.get('choices', [])):
            raise HTTPException(422, 'Unsupported question or invalid response')
        key = lookup.get(item['id'])
        if key is None or not isinstance(key.get('answer_index'), int):
            raise HTTPException(503, 'Canonical evaluation is incomplete')
        feedback.append(dict(id=item['id'], correct=value == key['answer_index'], explanation=key.get('explanation','Review the lesson and try again.')))
    return dict(kind='formative_practice', persisted=False, earned=sum(f['correct'] for f in feedback), possible=len(items), feedback=feedback)
