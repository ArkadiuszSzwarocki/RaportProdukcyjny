import sys

with open('app/blueprints/magazyny_nowe/api_pallets.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "typ_palety = arc_row['typ_palety'].lower()",
    "new_location = data.get('lokalizacja') or arc_row['lokalizacja_ostatnia']\n        typ_palety = arc_row['typ_palety'].lower()"
)

content = content.replace(
    ", arc_row['lokalizacja_ostatnia'], linia))",
    ", new_location, linia))"
)

content = content.replace(
    "Przywrócono z archiwum. Waga początkowa: {new_weight}', user_login))",
    "Przywrócono z archiwum z wagą: {new_weight}. Dawna lokalizacja: {arc_row[\"lokalizacja_ostatnia\"]}', user_login))"
)

with open('app/blueprints/magazyny_nowe/api_pallets.py', 'w', encoding='utf-8') as f:
    f.write(content)
