import os
for root, dirs, files in os.walk('app/services'):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if "COMPLETED" in content:
                    print(file)
