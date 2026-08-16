import codecs

path = 'a:/GitHub/RaportProdukcyjny/templates/planista.html'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_payload = "var payload = { id: id, produkt: prod, tonaz: ton, data_planu: dt, data_produkcji: dp, linia: currentLinia };"
new_payload = """var rpSelect = document.querySelector('#editForm_' + id + ' select[name=\"rodzaj_palety\"]');
        var rp = rpSelect ? rpSelect.value : 'krajowa';
        var payload = { id: id, produkt: prod, tonaz: ton, data_planu: dt, data_produkcji: dp, linia: currentLinia, rodzaj_palety: rp };"""
code = code.replace(old_payload, new_payload)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated payload in planista.html")
