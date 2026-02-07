#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove duplicate handleLogoError function from layout.html"""

with open('templates/layout.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the duplicate handleLogoError
# We know it's around line 160
in_first_handle = False
first_handle_start = -1
first_handle_end = -1
handle_count = 0

for i, line in enumerate(lines):
    if 'function handleLogoError' in line:
        handle_count += 1
        if handle_count == 1:
            first_handle_start = i
            in_first_handle = True
        else:
            if in_first_handle and first_handle_end == -1:
                first_handle_end = i - 1  # The line before the second handleLogoError
                break

if first_handle_start != -1 and first_handle_end != -1:
    print(f"Found duplicate handleLogoError:")
    print(f"  First occurrence: line {first_handle_start + 1}")
    print(f"  Second occurrence: line {first_handle_end + 2}")
    print(f"  Removing lines {first_handle_start + 1} to {first_handle_end + 1}")
    
    # Remove the first handleLogoError and blank lines
    new_lines = lines[:first_handle_start] + lines[first_handle_end + 1:]
    
    with open('templates/layout.html', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("✓ Duplicate removed")
else:
    print(f"❌ Could not find duplicate (found {handle_count} handleLogoError total)")
