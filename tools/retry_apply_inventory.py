#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ręcznie ponownie zatwierdza sesję inwentaryzacji #9.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db
from app.services.production_inventory_service import ProductionInventoryService

def retry_apply():
    sesja_id = 9
    user_login = 'system-fix'
    
    print("=" * 80)
    print(f"PONOWNE ZATWIERDZANIE SESJI #{sesja_id}")
    print("=" * 80)
    
    # Najpierw cofnij status do CLOSED
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_inwentaryzacja_produkcji_sesje SET status = 'CLOSED' WHERE id = %s", (sesja_id,))
    conn.commit()
    conn.close()
    
    print(f"\n✓ Cofnięto status sesji #{sesja_id} do CLOSED")
    
    # Teraz ponownie zastosuj
    print(f"\n→ Wywołuję apply_inventory()...")
    try:
        success, message = ProductionInventoryService.apply_inventory(sesja_id, user_login)
        if success:
            print(f"✓ SUKCES: {message}")
        else:
            print(f"✗ BŁĄD: {message}")
    except Exception as e:
        print(f"✗ WYJĄTEK: {e}")
        import traceback
        traceback.print_exc()
    
    # Sprawdź wynik
    print("\n" + "=" * 80)
    print("SPRAWDZENIE WYNIKU:")
    print("=" * 80)
    
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT status FROM magazyn_inwentaryzacja_produkcji_sesje WHERE id = %s", (sesja_id,))
    sesja = cursor.fetchone()
    print(f"\nStatus sesji: {sesja['status'] if sesja else 'NIE ZNALEZIONO'}")
    
    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM magazyn_ruch
        WHERE typ_ruchu = 'PRODUKCJA'
        AND komentarz LIKE %s
    """, (f'%Sesja #{sesja_id}%',))
    result = cursor.fetchone()
    print(f"Liczba wpisów PRODUKCJA z sesji #{sesja_id}: {result['cnt']}")
    
    cursor.execute("""
        SELECT 
            id,
            surowiec_nazwa,
            ilosc,
            zbiornik,
            autor_data
        FROM magazyn_ruch
        WHERE typ_ruchu = 'PRODUKCJA'
        AND komentarz LIKE %s
        ORDER BY id DESC
    """, (f'%Sesja #{sesja_id}%',))
    wpisy = cursor.fetchall()
    if wpisy:
        print("\nNowe wpisy PRODUKCJA:")
        for w in wpisy:
            print(f"  ID: {w['id']}, Zbiornik: {w['zbiornik']}, Surowiec: {w['surowiec_nazwa']}, "
                  f"Ilosc: {w['ilosc']}, Data: {w['autor_data']}")
    else:
        print("\nBrak nowych wpisów PRODUKCJA")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 80)

if __name__ == '__main__':
    retry_apply()
