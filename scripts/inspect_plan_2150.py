from app.db import get_db_connection
import json

plan_id_zasyp = 2150
plan_id_workowanie = 2151

conn = get_db_connection()
cur = conn.cursor()

# plan_history
cur.execute("SELECT id, action, changes, user_login, created_at FROM plan_history WHERE plan_id=%s ORDER BY id DESC LIMIT 50", (plan_id_zasyp,))
history = cur.fetchall()

# szarze for zasyp
cur.execute("SELECT id, waga, data_dodania, godzina, pracownik_id, status, uwagi FROM szarze WHERE plan_id=%s ORDER BY id DESC", (plan_id_zasyp,))
szarze = cur.fetchall()

# palety for zasyp and workowanie
cur.execute("SELECT id, plan_id, waga, tara, data_dodania FROM palety_workowanie WHERE plan_id IN (%s,%s) ORDER BY id DESC", (plan_id_zasyp, plan_id_workowanie))
palety = cur.fetchall()

result = {
    'plan_id_zasyp': plan_id_zasyp,
    'plan_id_workowanie': plan_id_workowanie,
    'plan_history': history,
    'szarze': szarze,
    'palety_workowanie': palety
}

print(json.dumps(result, default=str, ensure_ascii=False, indent=2))
conn.close()
