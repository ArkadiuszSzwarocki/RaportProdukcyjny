#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Przeskanuj szablony pod kątem nie przetłumaczonych polskich tekstów"""
import re
import os
from pathlib import Path

# Litera przej znaki polskie
polish_pattern = r'[ąćęłńóśźż]'

templates_dir = Path('templates')
findings = []

for html_file in templates_dir.rglob('*.html'):
    with open(html_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines, 1):
        # Pomiń linię jeśli zawiera {{ _()
        if '{{ _(' in line or '{#' in line:
            continue
        
        # Szukaj polskich liter w tekście HTML
        if re.search(polish_pattern, line):
            # Pomiń atrybuty i komentarze
            clean_line = re.sub(r'<[^>]+>', '', line).strip()
            if clean_line and not clean_line.startswith('{#'):
                # Szukaj słów polskich (co najmniej 3 znaki)
                words = re.findall(r'[a-ząćęłńóśźż]{3,}', clean_line, re.IGNORECASE)
                if words:
                    findings.append({
                        'file': html_file.name,
                        'line': line_num,
                        'text': clean_line[:80]
                    })

print(f'ZNALEZIONO: {len(findings)} potencjalnych nie przetłumaczonych tekstów\n')
for f in findings[:20]:
    print(f"[{f['file']}:{f['line']}] {f['text']}")

if len(findings) > 20:
    print(f"\n... i {len(findings) - 20} więcej")

print(f'\nRazem: {len(findings)} tekstów do sprawdzenia')
