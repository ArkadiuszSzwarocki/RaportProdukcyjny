#!/usr/bin/env python3
# Remove WNIOSKI section

with open('routes_api.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

wnioski_start = None
email_start = None

for i, line in enumerate(lines):
    if '# =============== WNIOSKI' in line and wnioski_start is None:
        wnioski_start = i
    if '# ================= EMAIL' in line and wnioski_start is not None:
        email_start = i
        break

if wnioski_start is not None and email_start is not None:
    print(f"Found WNIOSKI at line {wnioski_start + 1}")
    print(f"Found EMAIL at line {email_start + 1}")
    
    new_lines = lines[:wnioski_start] + lines[email_start:]
    
    with open('routes_api.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    old_count = len(lines)
    new_count = len(new_lines)
    print(f"File updated: {old_count} -> {new_count} lines ({old_count - new_count} deleted)")
else:
    print(f"ERROR: wnioski_start={wnioski_start}, email_start={email_start}")
