#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt naprawczy: usuwa duplikaty z pola items w tabeli magazyn_dostawy.

Problem: W niektórych przesunięciach pozycje (items) są zduplikowane
w polu JSON, co powoduje że w raporcie przesunięć wyświetlają się
wielokrotnie te same pozycje.

Rozwiązanie: Skrypt deduplikuje items po ID pozycji, zachowując pierwszą
instancję każdej pozycji i usuwając duplikaty.

Użycie:
    python tools/fix_duplicated_items.py
"""

import json
from app.db import get_db_connection


def deduplicate_items(items):
    """Deduplikuje listę items po ID pozycji."""
    if not items:
        return items
    
    seen_ids = set()
    deduped = []
    duplicates_found = 0
    
    for item in items:
        item_id = str(item.get('id', ''))
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            deduped.append(item)
        elif item_id:
            duplicates_found += 1
        else:
            # Item bez ID - zachowaj (choć to nietypowe)
            deduped.append(item)
    
    return deduped, duplicates_found


def main():
    """Główna funkcja naprawcza."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz wszystkie przesunięcia
        cursor.execute("SELECT id, order_ref, items FROM magazyn_dostawy WHERE items IS NOT NULL")
        dostawy = cursor.fetchall()
        
        total_processed = 0
        total_fixed = 0
        total_duplicates_removed = 0
        
        print(f"Znaleziono {len(dostawy)} przesunięć do sprawdzenia...")
        
        for dostawa in dostawy:
            dostawa_id = dostawa['id']
            order_ref = dostawa.get('order_ref', 'BRAK')
            items_json = dostawa.get('items')
            
            if not items_json:
                continue
            
            try:
                items = json.loads(items_json)
            except Exception as e:
                print(f"  ⚠️  Błąd parsowania JSON dla {order_ref} (ID: {dostawa_id}): {e}")
                continue
            
            if not isinstance(items, list):
                continue
            
            original_count = len(items)
            deduped_items, duplicates_found = deduplicate_items(items)
            new_count = len(deduped_items)
            
            total_processed += 1
            
            if duplicates_found > 0:
                # Znaleziono duplikaty - aktualizuj bazę
                cursor.execute(
                    "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                    (json.dumps(deduped_items), dostawa_id)
                )
                total_fixed += 1
                total_duplicates_removed += duplicates_found
                print(f"  ✅ {order_ref} (ID: {dostawa_id}): usunięto {duplicates_found} duplikatów ({original_count} → {new_count} pozycji)")
        
        conn.commit()
        
        print(f"\n" + "="*60)
        print(f"Podsumowanie:")
        print(f"  • Sprawdzono: {total_processed} przesunięć")
        print(f"  • Naprawiono: {total_fixed} przesunięć z duplikatami")
        print(f"  • Usunięto: {total_duplicates_removed} duplikatów")
        print(f"="*60)
        
        if total_fixed > 0:
            print(f"\n✅ Deduplikacja zakończona pomyślnie!")
        else:
            print(f"\nℹ️  Nie znaleziono duplikatów - baza jest OK.")
        
    except Exception as e:
        print(f"\n❌ Błąd podczas naprawy: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
