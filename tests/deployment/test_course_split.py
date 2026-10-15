"""Verify lazy transport is a byte-equivalent projection, never a second course source."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
GENERATED=ROOT/'apps/client/src/generated'


def test_every_lazy_course_matches_canonical_projection():
    bundle=json.loads((GENERATED/'publicCurriculumContent.json').read_text())
    index=json.loads((GENERATED/'publicCurriculumIndex.json').read_text())
    assert index['sourceCommit']==bundle['sourceCommit']
    assert len(index['tracks'])==len(bundle['tracks'])==18
    expected={track['trackId'] for track in bundle['tracks']}
    assert {p.stem for p in (GENERATED/'publicCurriculumChunks').glob('*.json')}==expected
    for track in bundle['tracks']:
        chunk=json.loads((GENERATED/'publicCurriculumChunks'/f"{track['trackId']}.json").read_text())
        assert chunk==track
        assert len(chunk['lessons'])==10
        assert next(t for t in index['tracks'] if t['trackId']==track['trackId'])['contentRootSha256']==chunk['contentRootSha256']
        def inspect(node):
            if isinstance(node,dict):
                assert not set(node) & {'answer_index','session_token','password_hash','grades','submissions'}
                for value in node.values():inspect(value)
            elif isinstance(node,list):
                for value in node:inspect(value)
        inspect(chunk)
    assert (GENERATED/'publicCurriculumIndex.json').stat().st_size<5000


def test_initial_module_never_imports_the_aggregate():
    for source in (ROOT/'apps/client/src').rglob('*'):
        if source.suffix in {'.ts','.tsx'} and not source.name.endswith(('.test.ts','.test.tsx')):
            assert 'generated/publicCurriculumContent.json' not in source.read_text()
