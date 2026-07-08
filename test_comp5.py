import json
with open('app/blueprints/magazyn_dostawy/routes/reception.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'COMPLETED' in line:
            print(f"{i+1}: {line.strip()}")
