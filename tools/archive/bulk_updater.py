import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/planista_bulk.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Input area
old_inputs = """        <div class="field-group">
          <label for="inpTonaz">Tonaz (kg) <span style="color: #ef4444;">*</span></label>
          <input type="number" id="inpTonaz" min="1" step="1" placeholder="Waga" style="padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1;">
        </div>"""
new_inputs = """        <div class="field-group">
          <label for="inpTonaz">Tonaz (kg) <span style="color: #ef4444;">*</span></label>
          <input type="number" id="inpTonaz" min="1" step="1" placeholder="Waga" style="padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1;">
        </div>
        <div class="field-group">
          <label for="inpRodzajPalety">Rodzaj Palety</label>
          <select id="inpRodzajPalety" style="padding: 10px; border-radius: 6px; border: 1px solid #cbd5e1;">
            <option value="krajowa">Krajowa</option>
            <option value="eksportowa">Eksportowa</option>
          </select>
        </div>"""
code = code.replace(old_inputs, new_inputs)

# Add btn logic
old_btn = "const tonazVal = document.getElementById('inpTonaz').value;\n      const tonaz = tonazVal ? parseFloat(tonazVal) : null;"
new_btn = "const tonazVal = document.getElementById('inpTonaz').value;\n      const tonaz = tonazVal ? parseFloat(tonazVal) : null;\n      const rodzajPalety = document.getElementById('inpRodzajPalety').value;"
code = code.replace(old_btn, new_btn)

old_tr = "tr.innerHTML = `<td><strong>${produkt}</strong></td>` +\n                     `<td>${nr}</td>` +\n                     `<td>${tonaz}</td>`"
new_tr = "tr.innerHTML = `<td><strong>${produkt}</strong></td>` +\n                     `<td>${nr}</td>` +\n                     `<td>${tonaz}</td>` +\n                     `<td>${rodzajPalety === 'eksportowa' ? '<span class=\"badge-eksportowa\">Eksport</span>' : 'Krajowa'}</td>`"
code = code.replace(old_tr, new_tr)

old_dataset = "tr.dataset.produkt = produkt;\n      tr.dataset.nr = nr;\n      tr.dataset.tonaz = tonaz;"
new_dataset = "tr.dataset.produkt = produkt;\n      tr.dataset.nr = nr;\n      tr.dataset.tonaz = tonaz;\n      tr.dataset.rodzaj_palety = rodzajPalety;"
code = code.replace(old_dataset, new_dataset)

old_clear = "document.getElementById('inpTonaz').value = '';"
new_clear = "document.getElementById('inpTonaz').value = '';\n      document.getElementById('inpRodzajPalety').value = 'krajowa';"
code = code.replace(old_clear, new_clear)

# Table headers
old_th = "<th>Tona</th>"
new_th = "<th>Tona</th>\n          <th>Paleta</th>"
code = code.replace(old_th, new_th)

# Build payload
old_payload = "tonaz: parseFloat(r.dataset.tonaz) || 0,"
new_payload = "tonaz: parseFloat(r.dataset.tonaz) || 0,\n        rodzaj_palety: r.dataset.rodzaj_palety || 'krajowa',"
code = code.replace(old_payload, new_payload)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated planista_bulk.html")
