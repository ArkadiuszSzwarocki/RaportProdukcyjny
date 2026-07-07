import os
for root, dirs, files in os.walk('static/js'):
    for file in files:
        if file.endswith('.js'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                if 'prompt(' in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if 'prompt(' in line:
                            print(f"{os.path.join(root, file)}:{i+1}: {line.strip()}")
