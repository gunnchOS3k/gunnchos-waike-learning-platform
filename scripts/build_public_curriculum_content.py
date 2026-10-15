#!/usr/bin/env python3
"""Regenerate public reader output through the canonical curriculum exporter.

Usage: python3 scripts/build_public_curriculum_content.py --curriculum-root PATH
This replaces the earlier slide-based projection. Offline signed-pack production
continues through the existing pack compiler and must be reviewed separately.
"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--curriculum-root',type=Path,required=True)
args=parser.parse_args()
source=args.curriculum_root.resolve()
if subprocess.check_output(['git','status','--porcelain'],cwd=source,text=True).strip():
    raise SystemExit('Commit the canonical curriculum before exporting a source-bound delivery artifact.')
subprocess.run([sys.executable,str(source/'scripts/export_browser_curriculum.py'),'--output',str(ROOT/'apps/client/src/generated/publicCurriculumContent.json')],check=True)
