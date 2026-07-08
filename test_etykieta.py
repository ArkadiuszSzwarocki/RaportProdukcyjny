import os
for root, dirs, files in os.walk('app/blueprints'):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'etykieta' in line.lower() and '@' in line and '.route' in line:
                        print(f"{os.path.join(root, file)}: {line.strip()}")
