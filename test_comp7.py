import json
with open('app/blueprints/magazyn_dostawy/routes/api_actions.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'COMPLETED' in line:
            print(f"{i+1}: {line.strip()}")
