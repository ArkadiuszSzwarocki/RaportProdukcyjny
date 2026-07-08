import os
for root, dirs, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'UPDATE magazyn_dostawy SET' in content or 'UPDATE magazyn_dostawy' in content:
                    print(os.path.join(root, file))
