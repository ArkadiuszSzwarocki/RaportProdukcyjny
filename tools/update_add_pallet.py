import codecs

filepath = 'a:/GitHub/RaportProdukcyjny/templates/warehouse/popups/add_pallet.html'
with open(filepath, 'rb') as f:
    content = f.read()

target3 = b'''      var form = document.getElementById('addPaletaForm');\r\n      if (!form) return;'''
replacement3 = b'''      var form = document.getElementById('addPaletaForm');\r\n      if (!form) return;\r\n      if (typeof window.workowaniePopulatePrinter === 'function') {\r\n          window.workowaniePopulatePrinter(form);\r\n      }'''

if target3 in content:
    content = content.replace(target3, replacement3)
    print("Replaced target3.")
else:
    target3_lf = b'''      var form = document.getElementById('addPaletaForm');\n      if (!form) return;'''
    replacement3_lf = b'''      var form = document.getElementById('addPaletaForm');\n      if (!form) return;\n      if (typeof window.workowaniePopulatePrinter === 'function') {\n          window.workowaniePopulatePrinter(form);\n      }'''
    if target3_lf in content:
        content = content.replace(target3_lf, replacement3_lf)
        print("Replaced target3 (LF).")
        
# For title we can use regex to replace `<h3 class="popup-title">...</h3>`
import re
pattern = b'<h3 class="popup-title">(.*?)</h3>'
replacement = b'<h3 class="popup-title" style="display:flex; justify-content:space-between; align-items:center;">\n    <span>\\1</span>\n    {% if sekcja in [\'Workowanie\', \'Czyszczenie\'] %}\n    <span class="material-icons printer-settings-icon" onclick="openPrinterSettingsModal()" style="cursor:pointer;color:#64748b;font-size:24px;" title="Ustawienia drukarki ZPL">settings</span>\n    {% endif %}\n  </h3>'
content = re.sub(pattern, replacement, content)
print("Replaced title.")

with open(filepath, 'wb') as f:
    f.write(content)
print("Done.")
