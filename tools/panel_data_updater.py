import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/blueprints/planista/panel_data.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Update load_primary_plan_rows
old_query_zasyp = "COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,\n               zasyp_id, data_produkcji\n        FROM {table_plan}\n        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')"
new_query_zasyp = "COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,\n               zasyp_id, data_produkcji, rodzaj_palety\n        FROM {table_plan}\n        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')"
code = code.replace(old_query_zasyp, new_query_zasyp)

old_query_work = "COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,\n               zasyp_id, data_produkcji\n        FROM {table_plan}\n        WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'"
new_query_work = "COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia,\n               zasyp_id, data_produkcji, rodzaj_palety\n        FROM {table_plan}\n        WHERE data_planu = %s AND LOWER(sekcja) = 'workowanie'"
code = code.replace(old_query_work, new_query_work)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated panel_data.py")
