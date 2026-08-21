import os
import re

directory = 'c:/Users/arkad/Documents/GitHub/RaportProdukcyjny/templates'

for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find lists containing 'admin'
            # Look for: [ ... 'admin' ... ]
            def repl(m):
                list_content = m.group(1)
                # Check if 'masteradmin' is already there
                if "'masteradmin'" in list_content or '"masteradmin"' in list_content:
                    return m.group(0)
                else:
                    # Insert 'masteradmin' next to 'admin'
                    new_list = list_content.replace("'admin'", "'admin', 'masteradmin'")
                    return '[' + new_list + ']'

            new_content = re.sub(r'\[([^\]]*\'admin\'[^\]]*)\]', repl, content)

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
