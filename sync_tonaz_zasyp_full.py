#!/usr/bin/env python
"""
Synchronizuj tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki potwierdzone)
dla Zasypu (dla wszystkich produktów, włączając HOLENDRA)
"""
from app.db import get_db_connection
from datetime import date

def sync_tonaz_rzeczywisty_zasyp(target_date=None):
    """Synchronuzuj tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki)"""
    if target_date is None:
        target_date = date.today()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print(f'\n{"="*80}')
    print(f'SYNCHRONIZACJA: tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki)')
    print(f'DATA: {target_date}')
    print(f'SEKCJA: ZASYP')
    print(f'{"="*80}\n')
    
    # Pobierz wszystkie plany Zasypu w podanym dniu
    cursor.execute('''
        SELECT id, produkt, tonaz_rzeczywisty as tonaz_db, status
        FROM plan_produkcji
        WHERE sekcja='Zasyp' AND DATE(data_planu)=%s AND is_deleted=0
        ORDER BY produkt
    ''', (target_date,))
    
    plans = cursor.fetchall()
    
    total_updated = 0
    
    for plan in plans:
        plan_id = plan['id']
        produkt = plan['produkt']
        tonaz_db_old = plan['tonaz_db'] or 0
        
        # Oblicz SUM(szarże)
        cursor.execute('''
            SELECT COALESCE(SUM(waga), 0) as szarze_sum
            FROM szarze
            WHERE plan_id=%s
        ''', (plan_id,))
        
        szarze_result = cursor.fetchone()
        szarze_sum = szarze_result['szarze_sum'] if szarze_result else 0
        
        # Oblicz SUM(dosypki potwierdzone)
        cursor.execute('''
            SELECT COALESCE(SUM(kg), 0) as dosypki_sum
            FROM dosypki
            WHERE plan_id=%s AND potwierdzone=1
        ''', (plan_id,))
        
        dosypki_result = cursor.fetchone()
        dosypki_sum = dosypki_result['dosypki_sum'] if dosypki_result else 0
        
        # Oblicz nową wartość
        tonaz_rzeczywisty_new = szarze_sum + dosypki_sum
        
        # Porównaj
        if abs(tonaz_db_old - tonaz_rzeczywisty_new) > 0.01:
            cursor.execute('''
                UPDATE plan_produkcji
                SET tonaz_rzeczywisty = %s
                WHERE id = %s
            ''', (tonaz_rzeczywisty_new, plan_id))
            
            print(f'✓ {produkt:20} | {tonaz_db_old:8.0f} kg → {tonaz_rzeczywisty_new:8.0f} kg | szarże={szarze_sum:7.0f} + dosypki={dosypki_sum:7.0f}')
            total_updated += 1
        else:
            print(f'✓ {produkt:20} | OK {tonaz_rzeczywisty_new:8.0f} kg | szarże={szarze_sum:7.0f} + dosypki={dosypki_sum:7.0f}')
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f'\n{"="*80}')
    print(f'✅ SYNCHRONIZACJA ZAKOŃCZONA')
    print(f'Zaktualizowano: {total_updated} planów')
    print(f'{"="*80}\n')

if __name__ == '__main__':
    sync_tonaz_rzeczywisty_zasyp()
