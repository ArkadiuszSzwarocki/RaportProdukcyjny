import codecs

path = 'a:/GitHub/RaportProdukcyjny/app/utils/queries_split/production.py'
with codecs.open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_select = "data_planu, zasyp_id, COALESCE(odrzuty_przesiewacz, 0) as odrzuty_przesiewacz {extra_cols} \""
new_select = "data_planu, zasyp_id, COALESCE(odrzuty_przesiewacz, 0) as odrzuty_przesiewacz, rodzaj_palety {extra_cols} \""
code = code.replace(old_select, new_select)

with codecs.open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated queries_split/production.py")
