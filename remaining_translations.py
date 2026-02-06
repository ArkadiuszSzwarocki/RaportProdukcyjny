#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

pl_translations = set(translations.get('pl', {}).keys())
pl_values = set(translations.get('pl', {}).values())

hardcoded_texts = set()

templates_dir = 'templates'
for filename in os.listdir(templates_dir):
    if filename.endswith('.html'):
        filepath = os.path.join(templates_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
            patterns = [
                r'>([A-Z][^<>]{2,}?)<',
                r"title=['\"]([^'\"]{3,}?)['\"]",
                r"placeholder=['\"]([^'\"]{3,}?)['\"]",
                r'>\s*([A-Z][A-Z\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\.&;:,\-()]{3,}?)\s*<',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    text = match.strip()
                    if len(text) > 2 and not text.isdigit() and text not in pl_values:
                        if not any(x in text for x in ['{{', '{%', '&nbsp;', '&#', ' kg', '%)', '|', '_(']):
                            hardcoded_texts.add(text)

print("\nZOSTALO DO PRZELOUMACZENIA:")
print(f"Liczba tekstow: {len(hardcoded_texts)}\n")

for text in sorted(hardcoded_texts)[:100]:
    print(f"  {text}")

if len(hardcoded_texts) > 100:
    print(f"\n... i jeszcze {len(hardcoded_texts) - 100} tekstow")
