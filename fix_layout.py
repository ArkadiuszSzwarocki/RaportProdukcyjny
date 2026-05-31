import os

path = r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\templates\dashboard\_dashboard_production_list.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Force the wrapper to span all grid columns (bypassing cache)
if '<style>.cards .active-agro-details-direct-wrapper' not in html:
    html = html.replace(
        '<div id="details-{{ p[0] }}" class="active-agro-details-direct-wrapper" style="width: 100%;">',
        '<style>.cards .active-agro-details-direct-wrapper { grid-column: 1 / -1 !important; width: 100% !important; max-width: 100% !important; }\n'
        '.active-agro-details-direct-wrapper .card { max-width: 100% !important; width: 100% !important; margin-left: 0 !important; margin-right: 0 !important; }</style>\n'
        '<div id="details-{{ p[0] }}" class="active-agro-details-direct-wrapper" style="width: 100%;">'
    )

# 2. Change split layout to flex so it gracefully flows
html = html.replace(
    '<div class="active-agro-split-layout" style="display: grid; grid-template-columns: minmax(400px, 1.1fr) minmax(400px, 1fr); gap: 20px; align-items: start;">',
    '<div class="active-agro-split-layout" style="display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start;">'
)
html = html.replace(
    '<div class="agro-split-left" style="display: flex; flex-direction: column; gap: 15px;">',
    '<div class="agro-split-left" style="flex: 1 1 500px; min-width: 0; display: flex; flex-direction: column; gap: 15px;">'
)
html = html.replace(
    '<div class="agro-split-right">',
    '<div class="agro-split-right" style="flex: 1 1 500px; min-width: 0;">'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Replaced layout successfully.')
