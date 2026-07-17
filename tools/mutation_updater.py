import re
import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/services/planning/mutation.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Update create_plan signature
code = re.sub(r"def create_plan\(data_planu, produkt, tonaz, sekcja, typ_produkcji='worki_zgrzewane_25', \n?.*?status='zaplanowane', wymaga_oplaty=False, nazwa_zlecenia=None, typ_zlecenia=None, zasyp_id=None, \n?.*?linia='PSD'\):", 
              "def create_plan(data_planu, produkt, tonaz, sekcja, typ_produkcji='worki_zgrzewane_25', status='zaplanowane', wymaga_oplaty=False, nazwa_zlecenia=None, typ_zlecenia=None, zasyp_id=None, linia='PSD', rodzaj_palety='krajowa'):", code)

# Update INSERT statements
# We need to add rodzaj_palety to columns and values.
code = code.replace(
    "(data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id)\n                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    "(data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id, rodzaj_palety)\n                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

code = code.replace(
    ", zasyp_id))",
    ", zasyp_id, rodzaj_palety))"
)

# Wait, the replace above string format might be too fragile if spacing is off.
# Let's use regex for INSERT INTO {table_plan}
def insert_replacer(match):
    columns = match.group(1)
    values = match.group(2)
    args = match.group(3)
    if 'rodzaj_palety' not in columns:
        columns = columns.replace(')', ', rodzaj_palety)')
        values = values.replace(')', ', %s)')
        # Add rodzaj_palety to args tuple
        if args.endswith('))'):
            args = args[:-2] + ', rodzaj_palety))'
        elif args.endswith(')'):
            args = args[:-1] + ', rodzaj_palety)'
    return f"INSERT INTO {{table_plan}} \n                          {columns}\n                          VALUES {values}\n                      \"\"\", {args}"

# Since regex is tricky over multiple lines, it's safer to read line by line.
lines = code.split('\n')
for i, line in enumerate(lines):
    if "(data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id)" in line:
        lines[i] = line.replace(')', ', rodzaj_palety)')
    elif "(data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, nazwa_zlecenia, typ_zlecenia, zasyp_id, linia)" in line:
        lines[i] = line.replace(')', ', rodzaj_palety)')
    elif "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" in line:
        lines[i] = line.replace(')', ', %s)')
    elif "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" in line:
        lines[i] = line.replace(')', ', %s)')
    elif '", (data_planu, produkt, tonaz, initial_status,' in line:
        # It's the execution line
        lines[i] = line.replace('))', ', rodzaj_palety))').replace(', rodzaj_palety, rodzaj_palety))', ', rodzaj_palety))')
    elif '", (data_planu, produkt, 0, initial_status,' in line:
        lines[i] = line.replace('))', ', rodzaj_palety))').replace(', rodzaj_palety, rodzaj_palety))', ', rodzaj_palety))')

code = '\n'.join(lines)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated create_plan")
