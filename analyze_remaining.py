#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analiza pozostałych tekstów - wyodrębnia rzeczywiste UI."""

import re
import os
import sys
from collections import defaultdict

# Ustaw UTF-8 dla stdout
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Pattern dla polskich znaków
polish_pattern = r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]'

templates_dir = 'templates'
exclude_patterns = [
    r'^\s*//',  # Komentarze JS
    r'^\s*\{#',  # Komentarze Jinja HTML
    r'if\s*\(',  # Warunkowe JS (javascript)
    r'confirm\(',  # JS confirm
    r'alert\(',  # JS alert
    r'showToast\(',  # JS funkcja
    r'console\.',  # Console log
    r'onclick=',  # Inline handler
    r'onClick=',  # React handler
    r'{%.*%}',  # Jinja tags
    r'{{.*}}',  # Jinja interpolation
]

files_to_check = {}
real_ui_texts = defaultdict(list)

# Przeskanuj templates
for root, dirs, files in os.walk(templates_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    # Pomiń linie już przetłumaczone
                    if '{{ _(' in line:
                        continue
                    
                    # Sprawdź czy linia ma polskie znaki
                    if re.search(polish_pattern, line):
                        # Sprawdź czy nie to komentarz/JS
                        is_excluded = False
                        for pattern in exclude_patterns:
                            if re.search(pattern, line):
                                is_excluded = True
                                break
                        
                        if not is_excluded:
                            # Wyodrębnij sam tekst
                            text = line.strip()[:100]
                            real_ui_texts[filepath].append((line_num, text))

# Wydrukuj wyniki posortowane
print("=" * 80)
print("RZECZYWISTE UI TEKSTY DO PRZETŁUMACZENIA (bez JS/komentarzy)")
print("=" * 80)

for filepath in sorted(real_ui_texts.keys()):
    print(f"\n[FILE] {filepath}")
    for line_num, text in real_ui_texts[filepath]:
        print(f"   [{line_num:3d}] {text}")

# Statystyka
total_lines = sum(len(v) for v in real_ui_texts.values())
print(f"\n{'=' * 80}")
print(f"RAZEM: {total_lines} rzeczywistych UI tekstów")
print(f"PLIKI: {len(real_ui_texts)}")
