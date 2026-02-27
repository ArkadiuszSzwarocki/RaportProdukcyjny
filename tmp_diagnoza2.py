import json
from datetime import date, datetime, timedelta
from app.db import get_db_connection

def s(obj):
    if isinstance(obj, (datetime, date)): return obj.isoformat()
    if isinstance(obj, timedelta): return str(obj)
    raise TypeError

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Sprawdź czy id=1215 istnieje (może soft-deleted?)
cursor.execute("SELECT * FROM plan_produkcji WHERE id = 1215")
plan_1215 = cursor.fetchone()

# Historia dla 1215 i 1216
cursor.execute("SELECT * FROM plan_history WHERE plan_id IN (1215, 1216, 1223, 1224) ORDER BY created_at")
history = cursor.fetchall()

# Sprawdź kolumny tabeli (żeby wiedzieć czy jest soft_delete / deleted_at)
cursor.execute("SHOW COLUMNS FROM plan_produkcji")
columns = cursor.fetchall()

# Sprawdź tabele zbliżone do id=1215 (zakres id 1213..1225)
cursor.execute("""
    SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, 
           status, typ_produkcji
    FROM plan_produkcji WHERE id BETWEEN 1213 AND 1225
    ORDER BY id
""")
zakres = cursor.fetchall()

data = {
    "plan_1215": plan_1215,
    "history_1215_1216_1223_1224": history,
    "columns": [c['Field'] for c in columns],
    "id_range_1213_1225": zakres
}

with open('tmp_diagnoza2.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, default=s, indent=4, ensure_ascii=False)
    print("Zapisano do tmp_diagnoza2.json")

conn.close()
