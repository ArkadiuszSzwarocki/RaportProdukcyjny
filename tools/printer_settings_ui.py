import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/includes/dashboard_top.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Add gear icon next to "od:" controls
old_controls = """                <button type="button" class="btn-action" onclick="applyDateRange()" style="background: #3498db; color: #fff; border: none; padding: 5px 15px; border-radius: 4px; font-weight: bold; cursor: pointer;">Poka</button>
            </div>"""

new_controls = """                <button type="button" class="btn-action" onclick="applyDateRange()" style="background: #3498db; color: #fff; border: none; padding: 5px 15px; border-radius: 4px; font-weight: bold; cursor: pointer;">Poka</button>
            </div>
            <button class="btn-action" onclick="openPrinterSettings()" style="background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 10px; cursor: pointer; display: flex; align-items: center;" title="Wybierz Drukarkt ZPL">
                <span class="material-icons" style="font-size: 18px;">print</span>
            </button>"""

code = code.replace(old_controls, new_controls)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated dashboard_top.html with gear icon")
