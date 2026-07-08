import os
for root, dirs, files in os.walk('app/blueprints/paletyzer'):
    for file in files:
        if file.endswith('.py') or file.endswith('.html'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'oproz' in content.lower() or 'opró¿' in content.lower():
                    print(os.path.join(root, file))
