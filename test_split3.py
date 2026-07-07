import os
for root, dirs, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if '/api/podzial-palety' in content or 'api_podzial_palety' in content:
                    print(os.path.join(root, file))
