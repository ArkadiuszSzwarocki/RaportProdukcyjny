import os
for root, dirs, files in os.walk('static/js'):
    for file in files:
        if file.endswith('.js'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'oproz' in content or 'opró¿' in content or 'Opró¿' in content or 'Oproz' in content:
                    print(os.path.join(root, file))
