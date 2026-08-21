import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/services/planning/commands/dodaj_szarze_command.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Signature
old_sig = "def execute(conn, cursor, linia, data_planu, produkt, tonaz, typ, plan_id_provided, nr_szarzy, auto_szarza_mode, is_admin, session, request_path, ui_trigger):"
new_sig = "def execute(conn, cursor, linia, data_planu, produkt, tonaz, typ, plan_id_provided, nr_szarzy, auto_szarza_mode, is_admin, session, request_path, ui_trigger, rodzaj_palety='krajowa'):"
code = code.replace(old_sig, new_sig)

# 2. INSERT statement
old_insert = "INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
new_insert = "INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
code = code.replace(old_insert, new_insert)

# 3. Tuple of values
old_values = "(data_planu, produkt, tonaz, 'zaplanowane', 'Workowanie', nk_work, source_typ, 0, zasyp_plan_id)"
new_values = "(data_planu, produkt, tonaz, 'zaplanowane', 'Workowanie', nk_work, source_typ, 0, zasyp_plan_id, rodzaj_palety)"
code = code.replace(old_values, new_values)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated dodaj_szarze_command")
