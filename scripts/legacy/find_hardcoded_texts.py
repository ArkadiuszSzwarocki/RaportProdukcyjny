#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import json

# Załaduj istniejące tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

pl_translations = set(translations.get('pl', {}).keys())
pl_values = set(translations.get('pl', {}).values())

# Szukaj tekstów w szablonach
hardcoded_texts = set()

templates_dir = 'templates'
for filename in os.listdir(templates_dir):
    if filename.endswith('.html'):
        filepath = os.path.join(templates_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Szukaj tekstów między tagami HTML
            # Pattern: tekst w cudzysłowach, >tekst<, atrybutach, itp.
            patterns = [
                r'>([A-Z][^<>]{2,}?)<',  # Tekst między tagami > <
                r"title=['\"]([^'\"]{3,}?)['\"]",  # atrybuty title
                r"placeholder=['\"]([^'\"]{3,}?)['\"]",  # atrybuty placeholder
                r'>\s*([A-Z][A-Z\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\.&;:,\-()]{3,}?)\s*<',  # tekst po polsku
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    text = match.strip()
                    # Pomiń bardzo krótkie lub liczby
                    if len(text) > 2 and not text.isdigit() and text not in pl_values:
                        # Pomiń HTML entities, zmienne Jinja, itp.
                        if not any(x in text for x in ['{{', '{%', '&nbsp;', '&#', ' kg', '%)', '|']):
                            hardcoded_texts.add(text)

# Sortuj i wyświetl
print(f"\n{'='*70}")
print(f"ZNALEZIONE HARDKODOWANE TEKSTY W SZABLONACH ({len(hardcoded_texts)})")
print(f"{'='*70}\n")

for text in sorted(hardcoded_texts):
    # Sprawdź czy jest w translations
    if text not in pl_values:
        print(f"  ❌ {text}")
