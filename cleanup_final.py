#!/usr/bin/env python3
# Remove OBSADA, WZNOWIENIE, and TEST ENDPOINTS sections from routes_api.py

with open('routes_api.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find all section markers
markers = {}
for i, line in enumerate(lines):
    if '# ================= OBSADA' in line:
        markers['obsada_start'] = i
    elif '# ================= EMAIL' in line and 'obsada_start' in markers:
        markers['email_start'] = i
    elif '# ================= WZNOWIENIE' in line:
        markers['wznowienie_start'] = i
    elif '# ================= RĘCZNE' in line:
        markers['reczne_start'] = i
    elif '# ================= MAGAZYN' in line and 'reczne_start' in markers:
        markers['magazyn_start'] = i
    elif '# ================= TEST' in line:
        markers['test_start'] = i
    elif '# ================= NOTATKI' in line:
        markers['notatki_start'] = i

print("Found markers:")
for key, val in markers.items():
    print(f"  {key}: line {val + 1}")

# Remove sections in reverse order to preserve indices
sections_to_remove = [
    ('test', markers.get('test_start'), markers.get('notatki_start')),
    ('wznowienie+reczne', markers.get('wznowienie_start'), markers.get('magazyn_start')),
    ('obsada', markers.get('obsada_start'), markers.get('email_start')),
]

new_lines = lines
for name, start, end in sections_to_remove:
    if start is not None and end is not None:
        # Recalculate indices for new_lines
        new_lines_len_before = len(new_lines)
        # Find actual positions in new_lines
        actual_start = None
        actual_end = None
        for i, line in enumerate(new_lines):
            if start == 0 or (i < len(new_lines) - (new_lines_len_before - end)):
                if '# ================= OBSADA' in line and name == 'obsada':
                    actual_start = i
                elif '# ================= WZNOWIENIE' in line and name == 'wznowienie+reczne':
                    actual_start = i
                elif '# ================= TEST' in line and name == 'test':
                    actual_start = i
        
        # Better approach: just search for the markers in new_lines
        actual_start = None
        actual_end = None
        for i, line in enumerate(new_lines):
            if name == 'obsada' and '# ================= OBSADA' in line:
                actual_start = i
            elif name == 'obsada'and '# ================= EMAIL' in line and actual_start is not None:
                actual_end = i
                break
            elif name == 'wznowienie+reczne' and '# ================= WZNOWIENIE' in line:
                actual_start = i
            elif name == 'wznowienie+reczne' and '# ================= MAGAZYN' in line and actual_start is not None:
                actual_end = i
                break
            elif name == 'test' and '# ================= TEST' in line:
                actual_start = i
            elif name == 'test' and '# ================= NOTATKI' in line and actual_start is not None:
                actual_end = i
                break
        
        if actual_start is not None and actual_end is not None:
            removed_count = actual_end - actual_start
            new_lines = new_lines[:actual_start] + new_lines[actual_end:]
            print(f"Removed {name}: lines {actual_start + 1}-{actual_end} ({removed_count} lines)")

# Save result
with open('routes_api.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"\nFinal: {len(lines)} -> {len(new_lines)} lines ({len(lines) - len(new_lines)} deleted)")
