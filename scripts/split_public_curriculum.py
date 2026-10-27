#!/usr/bin/env python3
"""Split the canonical public projection for Vite course-level loading.

No curriculum is authored here. Input remains the canonical exporter output;
all course bytes/identifiers and source hashes are preserved.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / 'apps/client/src/generated'


def split():
    bundle = json.loads((GENERATED / 'publicCurriculumContent.json').read_text())
    chunks = GENERATED / 'publicCurriculumChunks'
    chunks.mkdir(exist_ok=True)
    keep = set()
    for track in bundle['tracks']:
        track_id = track['trackId']
        if not track_id.replace('_', '').isalnum() or track_id != track_id.upper():
            raise ValueError('Invalid canonical track identifier')
        target = chunks / f'{track_id}.json'; keep.add(target.name)
        target.write_text(json.dumps(track, ensure_ascii=False, separators=(',', ':')) + '\n')
    for stale in chunks.glob('*.json'):
        if stale.name not in keep: stale.unlink()
    index = dict(sourceCommit=bundle['sourceCommit'], tracks=[{k:t[k] for k in ('trackId', 'offlinePackDeclared', 'contentRootSha256')} for t in bundle['tracks']])
    (GENERATED / 'publicCurriculumIndex.json').write_text(json.dumps(index, indent=2) + '\n')
    return index

if __name__ == '__main__': split()
