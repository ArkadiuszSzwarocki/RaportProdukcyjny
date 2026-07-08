import os
for root, dirs, files in os.walk('static/js/magazyn_dostawy'):
    for file in files:
        if file.endswith('.js'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'fetch(' in content or '$.ajax(' in content:
                    print(file)
