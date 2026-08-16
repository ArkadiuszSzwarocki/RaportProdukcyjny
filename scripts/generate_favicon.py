#!/usr/bin/env python3
"""Generate static/favicon.ico from static/agro_logo.png using Pillow.

Run from repository root:

python -m pip install pillow
python scripts/generate_favicon.py

The script writes `static/favicon.ico` (16/32/48 sizes).
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except Exception:
    print('Pillow not installed. Run: python -m pip install pillow', file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
IN_PNG = ROOT / 'static' / 'agro_logo.png'
OUT_ICO = ROOT / 'static' / 'favicon.ico'

if not IN_PNG.exists():
    print(f'Input PNG not found: {IN_PNG}', file=sys.stderr)
    sys.exit(1)

try:
    im = Image.open(IN_PNG)
    im.save(OUT_ICO, sizes=[(16,16),(32,32),(48,48)])
    print(f'Wrote {OUT_ICO}')
except Exception as e:
    print('Failed to generate favicon.ico:', e, file=sys.stderr)
    sys.exit(3)
