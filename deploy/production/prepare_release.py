#!/usr/bin/env python3
"""Prepare immutable local release inputs from clean source checkouts; never deploy."""
import argparse
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/hub'))
from app.production import tree_hash


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def prepare(curriculum, destination):
    for source in (ROOT, curriculum):
        if git(source, 'status', '--porcelain'):
            raise ValueError(f'Clean committed source required: {source}')
    pin = json.loads((ROOT / 'curriculum/registry/PIN.json').read_text())['pinned_commit']
    if git(curriculum, 'rev-parse', 'HEAD') != pin:
        raise ValueError('CURRICULUM_PIN_MISMATCH')
    content = json.loads((ROOT / 'apps/client/src/generated/publicCurriculumContent.json').read_text())
    if content['sourceCommit'] != pin:
        raise ValueError('READER_SOURCE_MISMATCH')
    if destination.exists():
        raise ValueError('Use a new release directory; never replace a retained release')
    subprocess.run(['python3', str(ROOT / 'scripts/split_public_curriculum.py')], check=True)
    if git(ROOT, 'status', '--porcelain'):
        raise ValueError('Committed split artifacts differ; commit verified projection first')
    subprocess.run(['pnpm', '--dir', str(ROOT / 'apps/client'), 'build'], env={**__import__('os').environ, 'VITE_HUB_SAME_ORIGIN': 'true', 'VITE_PUBLIC_READER': 'true', 'VITE_GUNNCHOS_PORTAL_URL': 'https://gunnchos.com/campus/waike', 'VITE_WAIKE_MOCK_HUB': 'false', 'VITE_HUB_URL': ''}, check=True)
    destination.mkdir(parents=True)
    shutil.copytree(ROOT / 'apps/client/dist', destination / 'reader')
    archive = subprocess.check_output(['git', '-C', str(curriculum), 'archive', pin])
    (destination / 'curriculum').mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination / 'curriculum', filter='data')
    manifest = dict(format='waike-runtime-release-v1', platform_commit=git(ROOT, 'rev-parse', 'HEAD'), curriculum_commit=pin, curriculum_tree_sha256=tree_hash(destination / 'curriculum'), reader_tree_sha256=tree_hash(destination / 'reader'))
    (destination / 'runtime-release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curriculum-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.release')
    args = parser.parse_args()
    prepare(args.curriculum_root.resolve(), args.output.resolve())
