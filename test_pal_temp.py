import os
for root, dirs, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'paletyz' in content.lower():
                    print(os.path.join(root, file))
