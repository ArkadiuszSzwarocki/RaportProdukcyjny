#!/usr/bin/env python3
# Extract OBSADA and remaining sections in one go using automated approach

import os

with open('routes_api.py', 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

# Define all remaining sections to extract
sections = [
    {
        'name': 'OBSADA',
        'marker_start': '# ================= OBSADA',
        'marker_end': '# ================= EMAIL',
        'output_file': 'routes_schedule.py',
        'blueprint_name': 'schedule_bp',
        'blueprint_var': 'schedule_bp'
    },
    {
        'name': 'Recovery Functions (WZNOWIENIE + RĘCZNE)',
        'marker_start': '# ================= WZNOWIENIE',
        'marker_end': '# ================= MAGAZYN',
        'output_file': 'routes_recovery.py',
        'blueprint_name': 'recovery_bp',
        'blueprint_var': 'recovery_bp'
    },
    {
        'name': 'TEST ENDPOINTS',
        'marker_start': '# ================= TEST',
        'marker_end': '# ================= NOTATKI',
        'output_file': 'routes_testing.py',
        'blueprint_name': 'testing_bp',
        'blueprint_var': 'testing_bp'
    }
]

extracted = []

for section in sections:
    start_idx = None
    end_idx = None
    
    for i, line in enumerate(all_lines):
        if section['marker_start'] in line and start_idx is None:
            start_idx = i
        if section['marker_end'] in line and start_idx is not None:
            end_idx = i
            break
    
    if start_idx is not None and end_idx is not None:
        section_lines = all_lines[start_idx:end_idx]
        
        # Create blueprint header
        header = f'''"""API routes extracted from routes_api.py - {section['name']} section."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from db import get_db_connection
from decorators import login_required, roles_required

{section['blueprint_var']} = Blueprint('{section['blueprint_var'].replace('_bp', '')}', __name__)

'''
        
        # Replace blueprint routes
        content = ''
        for line in section_lines:
            content += line.replace('@api_bp.route', f"@{section['blueprint_var']}.route")
        
        content = content.rstrip() + '\n'
        full_content = header + content
        
        # Write blueprint file
        output_path = section['output_file']
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        extracted.append({
            'file': output_path,
            'lines': len(section_lines),
            'start': start_idx + 1,
            'end': end_idx
        })
        
        print(f"✓ Created {output_path} ({len(section_lines)} lines, lines {start_idx + 1}-{end_idx})")

# Remove all extracted sections from routes_api.py in reverse order to preserve indices
extracted.sort(key=lambda x: x['start'], reverse=True)
for ext in extracted:
    # Find again since indices changed
    pass

print(f"\nExtracted {len(extracted)} sections:")
for ext in extracted:
    print(f"  - {ext['file']}: {ext['lines']} lines")
