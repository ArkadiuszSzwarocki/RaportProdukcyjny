import re
import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/planning/creation.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# For dodaj_plan_zaawansowany
old_zaaw = "linia = request.form.get('linia', 'PSD')"
new_zaaw = "linia = request.form.get('linia', 'PSD')\n        rodzaj_palety = request.form.get('rodzaj_palety', 'krajowa')"
code = code.replace(old_zaaw, new_zaaw)

old_zaaw_call = "status='zaplanowane', wymaga_oplaty=wymaga_oplaty, linia=linia,"
new_zaaw_call = "status='zaplanowane', wymaga_oplaty=wymaga_oplaty, linia=linia, rodzaj_palety=rodzaj_palety,"
code = code.replace(old_zaaw_call, new_zaaw_call)

# For dodaj_plan
old_dodaj = "auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()"
new_dodaj = "auto_szarza_mode = str(request.form.get('auto_szarza_mode') or 'manual').strip().lower()\n        rodzaj_palety = request.form.get('rodzaj_palety', 'krajowa')"
code = code.replace(old_dodaj, new_dodaj)

old_dodaj_call = "success, message, plan_id = PlanningMutationService.create_plan(\n                data_planu, produkt, tonaz, sekcja, typ, status='zaplanowane', linia=linia\n            )"
new_dodaj_call = "success, message, plan_id = PlanningMutationService.create_plan(\n                data_planu, produkt, tonaz, sekcja, typ, status='zaplanowane', linia=linia, rodzaj_palety=rodzaj_palety\n            )"
code = code.replace(old_dodaj_call, new_dodaj_call)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated creation.py")
