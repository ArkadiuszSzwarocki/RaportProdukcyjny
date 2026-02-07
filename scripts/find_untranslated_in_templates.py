#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Szuka tekstów w szablonach które mogą nie być tłumaczone
"""
import os
import re
from pathlib import Path

templates_dir = Path('templates')

# Lista plików do sprawdzenia
files_to_check = list(templates_dir.glob('*.html'))

print("=" * 80)
print("SPRAWDZANIE SZABLONÓW POD KĄTEM BEZ-PRZETŁUMACZONYCH TEKSTÓW")
print("=" * 80)
print()

# Szukamy linii które zawierają > tekst < ale nie {{ _(
untranslated_found = False

for html_file in sorted(files_to_check):
    with open(html_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Szukamy linii ze zwykłym tekstem (nie w {{ _() }})
    for line_num, line in enumerate(lines, 1):
        # Szukamy > tekst < (zwykły tekst HTML)
        matches = re.findall(r'>([^<{]+)<', line)
        
        for match in matches:
            text = match.strip()
            
            # Pomiń puste i bardzo krótkie
            if len(text) < 3:
                continue
            
            # Pomiń liczby, daty
            if re.match(r'^[\d\/\-\.,\s:]*$', text):
                continue
            
            # Pomiń tekst w {{ _() }}
            if '{{' in line or '{%' in line:
                continue
            
            # Jeśli to tekst po polsku (ma polskie znaki)
            if any(c in text for c in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ'):
                untranslated_found = True
                print(f"🔴 {html_file.name}:{line_num}")
                print(f"   > {text}")
                print()

if not untranslated_found:
    print("✓ Nie znaleziono oczywistych nie przetłumaczonych tekstów ze znakami polskimi!")
    print()
    print("Jeśli widać nie przetłumaczone teksty w przeglądarce, mogą to być:")
    print("  - Teksty generowane przez JavaScript")
    print("  - Wartości z bazy danych")
    print("  - Atrybuty HTML (name, id, type)")
    print("  - Słowa kluczowe bez polskich znaków (typ: 'Status', 'Plan')")
