import codecs
import re

path = 'a:/GitHub/RaportProdukcyjny/app/services/planning/commands/dodaj_plany_batch_command.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Add extract rodzaj_palety
old_extract = "opakowanie_id = p.get('opakowanie_id')"
new_extract = "opakowanie_id = p.get('opakowanie_id')\n            rodzaj_palety = p.get('rodzaj_palety', 'krajowa')"
code = code.replace(old_extract, new_extract)

# Agro Zasyp
old_a_zasyp = "typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
new_a_zasyp = "typ_opakowania, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
code = code.replace(old_a_zasyp, new_a_zasyp)
old_a_zasyp_v = "0, opakowanie_id, etykieta_id, typ_opakowania),"
new_a_zasyp_v = "0, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety),"
code = code.replace(old_a_zasyp_v, new_a_zasyp_v)

# Agro Workowanie
old_a_work = "typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
new_a_work = "typ_opakowania, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
code = code.replace(old_a_work, new_a_work)
old_a_work_v = "0, zasyp_id_agro, opakowanie_id, etykieta_id, typ_opakowania),"
new_a_work_v = "0, zasyp_id_agro, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety),"
code = code.replace(old_a_work_v, new_a_work_v)

# PSD Zasyp
old_p_zasyp = "typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
new_p_zasyp = "typ_opakowania, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
code = code.replace(old_p_zasyp, new_p_zasyp)
old_p_zasyp_v = "0, typ_opakowania),"
new_p_zasyp_v = "0, typ_opakowania, rodzaj_palety),"
code = code.replace(old_p_zasyp_v, new_p_zasyp_v)

# PSD Workowanie
old_p_work = "typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
new_p_work = "typ_opakowania, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'"
code = code.replace(old_p_work, new_p_work)
old_p_work_v = "0, zasyp_id_created, typ_opakowania),"
new_p_work_v = "0, zasyp_id_created, typ_opakowania, rodzaj_palety),"
code = code.replace(old_p_work_v, new_p_work_v)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated dodaj_plany_batch_command.py")
