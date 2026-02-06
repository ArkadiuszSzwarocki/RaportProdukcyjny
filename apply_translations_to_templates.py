#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import json

# Załaduj tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

pl_texts = translations.get('pl', {})

# Mapa zastępień (tekst -> klucz)
# Sortujemy od najdłuższych aby uniknąć partial matches
replacements = sorted(
    [(v, k) for k, v in pl_texts.items()],
    key=lambda x: len(x[0]),
    reverse=True
)

templates_dir = 'templates'
modified_files = 0
total_replacements = 0

for filename in os.listdir(templates_dir):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(templates_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    content = original_content
    file_replacements = 0
    
    for pl_text, key in replacements:
        # Pattern: tekst w >...<, nie wewnątrz {{...}}
        # Unikamy polskich znaków specjalnych w regex
        escaped_text = re.escape(pl_text)
        
        # Pattern 1: >Tekst< (między tagami)
        pattern1 = f'>{escaped_text}<'
        replacement1 = f'>{{{{ _(\'{key}\') }}}}<'
        new_content = re.sub(pattern1, replacement1, content)
        file_replacements += len(re.findall(pattern1, content))
        content = new_content
        
        # Pattern 2: title="Tekst"
        pattern2 = f'title=["\']?{escaped_text}["\']?'
        if f'title="{pl_text}"' in content:
            content = content.replace(
                f'title="{pl_text}"',
                f'title="{{{{ _(\'{key}\') }}}}"'
            )
            file_replacements += 1
        
        # Pattern 3: placeholder="Tekst"
        pattern3 = f'placeholder=["\']?{escaped_text}["\']?'
        if f'placeholder="{pl_text}"' in content:
            content = content.replace(
                f'placeholder="{pl_text}"',
                f'placeholder="{{{{ _(\'{key}\') }}}}"'
            )
            file_replacements += 1
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        modified_files += 1
        total_replacements += file_replacements
        print(f"✓ {filename}: {file_replacements} zamian")

print(f"\n{'='*60}")
print(f"Zmodyfikowano {modified_files} plików")
print(f"Razem zamian: {total_replacements}")
print(f"\n⚠️  Sprawdzić ręcznie:\n  - Dialogi/modals z dynamicznym tekstem\n  - Specjalne komunikaty z emoji\n  - Tekst w atrybutach data-*")
