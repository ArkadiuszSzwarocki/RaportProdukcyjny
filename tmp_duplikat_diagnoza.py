import sys
import json
from datetime import date, datetime, timedelta
from app.db import get_db_connection

def default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def main():
    conn = get_db_connection()
    if not conn:
        print("Brak połączenia z bazą.")
        sys.exit(1)
    
    cursor = conn.cursor(dictionary=True)
    
    # -- wszystkie zlecenia workowanie dzisiaj z pełnymi polami --
    cursor.execute("""
        SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty,
               status, real_start, real_stop, kolejnosc, zasyp_id, typ_produkcji
        FROM plan_produkcji 
        WHERE data_planu = '2026-02-27' AND sekcja = 'Workowanie'
        ORDER BY id
    """)
    workowania = cursor.fetchall()
    
    # -- powiązane zlecenia Zasyp dla POLMLEK 100% --
    cursor.execute("""
        SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty,
               status, real_start, real_stop, real_start, typ_produkcji
        FROM plan_produkcji 
        WHERE data_planu = '2026-02-27'
          AND produkt = 'POLMLEK 100 %'
        ORDER BY id
    """)
    polmlek_all = cursor.fetchall()
    
    # -- szarże dla POLMLEK 100% --
    cursor.execute("""
        SELECT s.id, s.plan_id, s.waga, s.data_dodania, s.godzina, s.status,
               pp.produkt, pp.sekcja
        FROM szarze s
        JOIN plan_produkcji pp ON s.plan_id = pp.id
        WHERE pp.data_planu = '2026-02-27'
          AND pp.produkt = 'POLMLEK 100 %'
        ORDER BY s.id
    """)
    szarze = cursor.fetchall()
    
    data = {
        "workowania_dzisiaj": workowania,
        "polmlek_100_wszystkie": polmlek_all,
        "szarze_polmlek": szarze
    }
    
    with open('tmp_duplikat_diagnoza.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, default=default_serializer, indent=4, ensure_ascii=False)
        print("Zapisano do tmp_duplikat_diagnoza.json")
        
    conn.close()

if __name__ == '__main__':
    main()
