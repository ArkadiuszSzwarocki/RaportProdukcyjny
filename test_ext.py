import json
with open('app/services/magazyn_dostawy/delivery_command_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'is_external_reception =' in line:
            print(f"{i+1}: {line.strip()}")
