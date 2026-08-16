# -*- coding: utf-8 -*-
import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/planista.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# For edit form
old_edit = "html += '<div class=\"form-group\"><label>Data produkcji (opcjonalnie):</label><input id=\"e_prod_date_' + id + '\" name=\"data_produkcji\" type=\"date\" value=\"' + dataProdukcji + '\" style=\"width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;\"></div>';"
new_edit = old_edit + "\n        html += '<div class=\"form-group\"><label>Rodzaj palety:</label><select name=\"rodzaj_palety\" style=\"width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;\"><option value=\"krajowa\">Krajowa (Zwyk\u0142a)</option><option value=\"eksportowa\" ' + (plan.rodzaj_palety === 'eksportowa' ? 'selected' : '') + '>Eksportowa</option></select></div>';"
code = code.replace(old_edit, new_edit)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated planista.html")
