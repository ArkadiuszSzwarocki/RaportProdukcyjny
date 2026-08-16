import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/planning/creation.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_call = "ui_trigger=ui_trigger\n                        )"
new_call = "ui_trigger=ui_trigger,\n                            rodzaj_palety=rodzaj_palety\n                        )"
code = code.replace(old_call, new_call)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated creation.py with DodajSzarzeCommand")
