# -*- coding: utf-8 -*-
with open('templates/planista.html', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('etykiett...', 'etykietę...')
with open('templates/planista.html', 'w', encoding='utf-8') as f:
    f.write(content)
