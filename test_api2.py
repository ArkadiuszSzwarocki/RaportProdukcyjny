import os
for root, dirs, files in os.walk('static'):
    for file in files:
        if file.endswith('.js'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if '/api/zapisz' in content:
                    print(os.path.join(root, file))
