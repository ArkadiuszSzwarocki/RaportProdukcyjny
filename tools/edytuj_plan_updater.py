import re
import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/services/planning/commands/edytuj_plan_command.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add rodzaj_palety to data extraction
code = code.replace("last_seen = data.get('last_updated')", "last_seen = data.get('last_updated')\n        rodzaj_palety = data.get('rodzaj_palety')")

# 2. Add rodzaj_palety to SELECT statement (append before updated_at)
code = code.replace(", opakowanie_id, etykieta_id, updated_at", ", opakowanie_id, etykieta_id, rodzaj_palety, updated_at")
code = code.replace(", NULL as opakowanie_id, NULL as etykieta_id, updated_at", ", NULL as opakowanie_id, NULL as etykieta_id, rodzaj_palety, updated_at")

# 3. Add to updates logic
# before[13] is rodzaj_palety, before[14] is updated_at
code = code.replace("db_updated_at = str(before[13]) if before[13] else ''", "db_updated_at = str(before[14]) if before[14] else ''")

update_logic = """        if rodzaj_palety is not None and rodzaj_palety != before[13]:
            updates.append('rodzaj_palety=%s')
            params.append(rodzaj_palety)
            changes['rodzaj_palety'] = {'before': before[13], 'after': rodzaj_palety}

        if data_planu and data_planu != str(before[4]):"""
code = code.replace("if data_planu and data_planu != str(before[4]):", update_logic)

# 4. Link changes down to Workowanie when Zasyp is edited
code = code.replace("['produkt', 'typ_produkcji', 'nazwa_zlecenia', 'data_planu', 'tonaz', 'opakowanie_id', 'etykieta_id']", "['produkt', 'typ_produkcji', 'nazwa_zlecenia', 'data_planu', 'tonaz', 'opakowanie_id', 'etykieta_id', 'rodzaj_palety']")

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated edytuj_plan_command.py")
