import os
import re

path = r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\templates\dashboard\_dashboard_production_list.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Change active-agro-split-layout back to Grid
html = re.sub(
    r'<div class="active-agro-split-layout".*?>',
    '<div class="active-agro-split-layout" style="display: grid; grid-template-columns: minmax(400px, 1.1fr) minmax(400px, 1fr); gap: 20px; align-items: start;">',
    html
)
html = html.replace(
    '<div class="agro-split-left" style="flex: 1 1 500px; min-width: 0; display: flex; flex-direction: column; gap: 15px;">',
    '<div class="agro-split-left" style="display: flex; flex-direction: column; gap: 15px;">'
)
html = html.replace(
    '<div class="agro-split-right" style="flex: 1 1 500px; min-width: 0;">',
    '<div class="agro-split-right">'
)

# 2. Add media query inside the inline style block to stack the grid on mobile
if '@media (max-width: 900px)' not in html:
    html = html.replace(
        '.active-agro-details-direct-wrapper .card { max-width: 100% !important; width: 100% !important; margin-left: 0 !important; margin-right: 0 !important; }</style>',
        '.active-agro-details-direct-wrapper .card { max-width: 100% !important; width: 100% !important; margin-left: 0 !important; margin-right: 0 !important; }\n'
        '@media (max-width: 900px) { .active-agro-split-layout { grid-template-columns: 1fr !important; } }</style>'
    )

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Production list layout fixed.')

# 3. Fix the pallet sorting in _dashboard_agro_active_details.html
details_path = r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny\templates\dashboard\_dashboard_agro_active_details.html'
with open(details_path, 'r', encoding='utf-8') as f:
    details_html = f.read()

# Change items_to_render to always reverse, or reverse for AGRO
details_html = re.sub(
    r'{%\s*set items_to_render = fb_palety\|reverse if linia\|upper == \'PSD\' else fb_palety\s*%}',
    r'{% set items_to_render = fb_palety|reverse %}',
    details_html
)
with open(details_path, 'w', encoding='utf-8') as f:
    f.write(details_html)
print('Pallets sorting fixed.')
