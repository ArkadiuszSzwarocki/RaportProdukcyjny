from datetime import date
from app.utils.queries import QueryHelper

d = date(2026,2,23)
rows = QueryHelper.get_paletki_magazyn(d)
print('get_paletki_magazyn rows:', len(rows))
for r in rows:
    print(r)
