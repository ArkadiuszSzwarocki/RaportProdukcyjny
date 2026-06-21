import re
import sys
import subprocess

try:
    with open('A:/GitHub/RaportProdukcyjny/templates/includes/_layout_scripts.html', 'r', encoding='utf-8') as f:
        text = f.read()

    text = text.replace('<script>', '')
    text = text.replace('</script>', '')
    text = re.sub(r'\{%.*?%\}', '', text)
    text = re.sub(r'\{\{.*?\}\}', '""', text)

    with open('test_syntax.js', 'w', encoding='utf-8') as out:
        out.write(text)

    res = subprocess.run(['node', '-c', 'test_syntax.js'], capture_output=True, text=True)
    if res.returncode != 0:
        print('Syntax Error in _layout_scripts.html:')
        print(res.stderr)
    else:
        print('Syntax OK in _layout_scripts.html')
except Exception as e:
    print(f"Error: {e}")
