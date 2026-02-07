#!/usr/bin/env python3
# Extract WNIOSKI section to routes_leaves.py

with open('routes_api.py', 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

# Find WNIOSKI and EMAIL markers
wnioski_start = None
email_start = None

for i, line in enumerate(all_lines):
    if '# =============== WNIOSKI' in line and wnioski_start is None:
        wnioski_start = i
    if '# ================= EMAIL' in line and wnioski_start is not None:
        email_start = i
        break

if wnioski_start is not None and email_start is not None:
    print(f"Found WNIOSKI at line {wnioski_start + 1}")
    print(f"Found EMAIL at line {email_start + 1}")
    
    # Extract WNIOSKI section
    wnioski_lines = all_lines[wnioski_start:email_start]
    
    # Create routes_leaves.py file
    header = '''"""Leave request routes (formerly in routes_api.py WNIOSKI O WOLNE section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime
from db import get_db_connection
from decorators import login_required, roles_required
import json

leaves_bp = Blueprint('leaves', __name__)

'''
    
    # Replace @api_bp.route with @leaves_bp.route
    content = ''
    for line in wnioski_lines:
        content += line.replace('@api_bp.route', '@leaves_bp.route')
    
    # Remove trailing blank lines
    content = content.rstrip() + '\n'
    
    full_content = header + content
    
    with open('routes_leaves.py', 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    lines_written = wnioski_lines.__len__()
    print(f"Created routes_leaves.py with {lines_written} lines extracted from routes_api.py")
else:
    print(f"ERROR: wnioski_start={wnioski_start}, email_start={email_start}")
