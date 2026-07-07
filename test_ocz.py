import json
with open('app/blueprints/magazyn_dostawy/routes/transfer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if 'def oczekujace' in line:
            for j in range(i, i+50):
                print(f"{j+1}: {lines[j].strip()}")
            break
