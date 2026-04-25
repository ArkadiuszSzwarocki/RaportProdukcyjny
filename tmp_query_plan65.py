import json
from app.db import get_db_connection, get_table_name

plan_id = 65
linie = ["AGRO", "PSD"]
bases = ["plan_produkcji", "szarze", "dosypki"]

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

try:
    print("=== MAPOWANIE TABEL (get_table_name) ===")
    mapping = {}
    for linia in linie:
        mapping[linia] = {b: get_table_name(b, linia) for b in bases}
        print(f"Linia {linia}:")
        for b in bases:
            print(f"  {b} -> {mapping[linia][b]}")

    print("\n=== SPRAWDZENIE ISTNIENIA plan id=65 ===")
    found_lines = []
    for linia in linie:
        plan_table = get_table_name("plan_produkcji", linia)
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {plan_table} WHERE id = %s", (plan_id,))
        cnt = cur.fetchone()["cnt"]
        exists = cnt > 0
        print(f"Linia {linia}, tabela {plan_table}: exists={exists}, count={cnt}")
        if exists:
            found_lines.append(linia)

    if not found_lines:
        print("\nBRAK plan id=65 w plan_produkcji (PSD) i plan_produkcji_agro (AGRO).")
    else:
        print(f"\n=== DANE SZCZEGÓŁOWE DLA WŁAŚCIWEJ LINII: {', '.join(found_lines)} ===")
        for linia in found_lines:
            plan_table = get_table_name("plan_produkcji", linia)
            szarze_table = get_table_name("szarze", linia)

            print(f"\n--- LINIA {linia} ---")

            cur.execute(
                f"SELECT id, sekcja, status, tonaz_rzeczywisty FROM {plan_table} WHERE id = %s",
                (plan_id,),
            )
            plan_rows = cur.fetchall()
            print("plan(id,sekcja,status,tonaz_rzeczywisty):")
            print(json.dumps(plan_rows, ensure_ascii=False, indent=2, default=str))

            cur.execute(
                f"SELECT id, nr_szarzy, waga, data_dodania FROM {szarze_table} WHERE plan_id = %s ORDER BY id",
                (plan_id,),
            )
            szarze_rows = cur.fetchall()
            print("szarze(plan_id=65: id,nr_szarzy,waga,data_dodania):")
            print(json.dumps(szarze_rows, ensure_ascii=False, indent=2, default=str))

            cur.execute(
                "SELECT linia, szarza_nr, etap, czas_start, czas_stop "
                "FROM zasyp_etapy WHERE plan_id = %s AND UPPER(linia) = %s "
                "ORDER BY szarza_nr, etap, id",
                (plan_id, linia),
            )
            etapy_rows = cur.fetchall()
            print("zasyp_etapy(plan_id=65: linia,szarza_nr,etap,czas_start,czas_stop):")
            print(json.dumps(etapy_rows, ensure_ascii=False, indent=2, default=str))
finally:
    cur.close()
    conn.close()
