import os
for root, dirs, files in os.walk('app/blueprints'):
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f), 'r', encoding='utf-8') as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if 'raport_palet' in line.lower() or 'raport' in line.lower():
                        print(f'{f}:{i+1} -> {line.strip()}')

