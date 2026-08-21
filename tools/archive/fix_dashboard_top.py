# -*- coding: utf-8 -*-
import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/includes/dashboard_top.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Fix the Poka¿ button
old_poka = "Poka <span class=\"material-icons\" style=\"font-size: 16px; margin-left: 5px;\">settings</span></button>"
new_poka = "Poka</button>"
code = code.replace(old_poka, new_poka)

# Remove the broken span and add correct button
old_span = "<span class=\"material-icons\" style=\"font-size: 20px; color: #7f8c8d; margin-left: 10px;\">settings</span>\n            </div>"
new_span = "</div>"
code = code.replace(old_span, new_span)

# Add the actual printer settings button
if 'openOperatorPrinterSettings()' not in code:
    old_end = "        </div>\n\n        <div class=\"d-flex align-center gap-12 header-stats\">"
    new_end = """            {% if sekcja in ['Workowanie', 'PSD'] or linia == 'AGRO' %}
            <button class="btn-action" onclick="openOperatorPrinterSettings()" title="Wybierz Drukark ZPL" style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 12px; margin-left: 10px; cursor: pointer; display: flex; align-items: center; gap: 5px; color: #475569;">
                <span class="material-icons" style="font-size: 18px; color: #0284c7;">print</span>
                <span class="material-icons" style="font-size: 14px;">settings</span>
            </button>
            {% endif %}
        </div>

        <div class="d-flex align-center gap-12 header-stats">"""
    code = code.replace(old_end, new_end)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Fixed dashboard_top.html")
