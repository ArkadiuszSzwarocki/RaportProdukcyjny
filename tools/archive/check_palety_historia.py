#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt diagnostyczny: sprawdza czy wszystkie palety mają historię.
"""

from app.db import get_db_connection
import json

def check_history():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # 1. Sprawdź palety surowców
    print("=" * 80)
    print("1. PALETY SUROWCÓW (magazyn_surowce)")
    print("=" * 80)
    cur.execute('SELECT id, nr_palety, nazwa, lokalizacja FROM magazyn_surowce ORDER BY id DESC LIMIT 10')
    surowce = cur.fetchall()
    
    for s in surowce:
        cur.execute('SELECT COUNT(*) as cnt FROM palety_historia WHERE paleta_id=%s AND typ_palety="surowiec"', (s['id'],))
        history_cnt = cur.fetchone()['cnt']
        status = "✅" if history_cnt > 0 else "❌"
        print(f"{status} Paleta {s['id']:4d} ({s['nr_palety'] or 'BRAK_NR':20s}): {history_cnt} wpisów historii")
        
        if history_cnt > 0:
            cur.execute('SELECT akcja, data_ruchu, user_login FROM palety_historia WHERE paleta_id=%s AND typ_palety="surowiec" ORDER BY data_ruchu', (s['id'],))
            historia = cur.fetchall()
            for h in historia:
                print(f"    → {h['data_ruchu']} | {h['akcja']:25s} | {h['user_login'] or 'system'}")
    
    # 2. Sprawdź palety opakowań
    print("\n" + "=" * 80)
    print("2. PALETY OPAKOWAŃ (magazyn_opakowania)")
    print("=" * 80)
    cur.execute('SELECT id, nr_palety, nazwa, lokalizacja FROM magazyn_opakowania ORDER BY id DESC LIMIT 10')
    opakowania = cur.fetchall()
    
    for o in opakowania:
        cur.execute('SELECT COUNT(*) as cnt FROM palety_historia WHERE paleta_id=%s AND typ_palety="opakowanie"', (o['id'],))
        history_cnt = cur.fetchone()['cnt']
        status = "✅" if history_cnt > 0 else "❌"
        print(f"{status} Paleta {o['id']:4d} ({o['nr_palety'] or 'BRAK_NR':20s}): {history_cnt} wpisów historii")
        
        if history_cnt > 0:
            cur.execute('SELECT akcja, data_ruchu, user_login FROM palety_historia WHERE paleta_id=%s AND typ_palety="opakowanie" ORDER BY data_ruchu', (o['id'],))
            historia = cur.fetchall()
            for h in historia:
                print(f"    → {h['data_ruchu']} | {h['akcja']:25s} | {h['user_login'] or 'system'}")
    
    # 3. Sprawdź palety wyrobów gotowych
    print("\n" + "=" * 80)
    print("3. PALETY WYROBÓW GOTOWYCH (magazyn_palety)")
    print("=" * 80)
    cur.execute('SELECT id, nr_palety, produkt, lokalizacja FROM magazyn_palety ORDER BY id DESC LIMIT 10')
    palety_wg = cur.fetchall()
    
    for p in palety_wg:
        cur.execute('SELECT COUNT(*) as cnt FROM palety_historia WHERE paleta_id=%s AND typ_palety IN ("wyrob_gotowy", "wyrób gotowy")', (p['id'],))
        history_cnt = cur.fetchone()['cnt']
        status = "✅" if history_cnt > 0 else "❌"
        print(f"{status} Paleta {p['id']:4d} ({p['nr_palety'] or 'BRAK_NR':20s}): {history_cnt} wpisów historii")
        
        if history_cnt > 0:
            cur.execute('SELECT akcja, data_ruchu, user_login FROM palety_historia WHERE paleta_id=%s AND typ_palety IN ("wyrob_gotowy", "wyrób gotowy") ORDER BY data_ruchu', (p['id'],))
            historia = cur.fetchall()
            for h in historia:
                print(f"    → {h['data_ruchu']} | {h['akcja']:25s} | {h['user_login'] or 'system'}")
    
    # 4. Statystyki
    print("\n" + "=" * 80)
    print("4. STATYSTYKI")
    print("=" * 80)
    
    # Surowce
    cur.execute('SELECT COUNT(*) as cnt FROM magazyn_surowce')
    total_surowce = cur.fetchone()['cnt']
    cur.execute('SELECT COUNT(DISTINCT paleta_id) as cnt FROM palety_historia WHERE typ_palety="surowiec"')
    with_history_surowce = cur.fetchone()['cnt']
    print(f"Surowce: {with_history_surowce}/{total_surowce} palet ma historię ({with_history_surowce/total_surowce*100 if total_surowce > 0 else 0:.1f}%)")
    
    # Opakowania
    cur.execute('SELECT COUNT(*) as cnt FROM magazyn_opakowania')
    total_opakowania = cur.fetchone()['cnt']
    cur.execute('SELECT COUNT(DISTINCT paleta_id) as cnt FROM palety_historia WHERE typ_palety="opakowanie"')
    with_history_opakowania = cur.fetchone()['cnt']
    print(f"Opakowania: {with_history_opakowania}/{total_opakowania} palet ma historię ({with_history_opakowania/total_opakowania*100 if total_opakowania > 0 else 0:.1f}%)")
    
    # Wyroby gotowe
    cur.execute('SELECT COUNT(*) as cnt FROM magazyn_palety')
    total_wg = cur.fetchone()['cnt']
    cur.execute('SELECT COUNT(DISTINCT paleta_id) as cnt FROM palety_historia WHERE typ_palety IN ("wyrob_gotowy", "wyrób gotowy")')
    with_history_wg = cur.fetchone()['cnt']
    print(f"Wyroby gotowe: {with_history_wg}/{total_wg} palet ma historię ({with_history_wg/total_wg*100 if total_wg > 0 else 0:.1f}%)")
    
    # 5. Palety bez historii
    print("\n" + "=" * 80)
    print("5. PRZYKŁADY PALET BEZ HISTORII")
    print("=" * 80)
    
    cur.execute("""
        SELECT 'surowiec' as typ, s.id, s.nr_palety, s.nazwa, s.lokalizacja, s.created_at
        FROM magazyn_surowce s
        LEFT JOIN palety_historia h ON s.id = h.paleta_id AND h.typ_palety = 'surowiec'
        WHERE h.id IS NULL
        ORDER BY s.created_at DESC
        LIMIT 5
    """)
    bez_historii = cur.fetchall()
    
    if bez_historii:
        print("Surowce bez historii:")
        for row in bez_historii:
            print(f"  ❌ ID={row['id']}, Nr={row['nr_palety'] or 'BRAK'}, {row['nazwa']}, lokalizacja={row['lokalizacja']}, utworzono={row['created_at']}")
    else:
        print("✅ Wszystkie surowce mają historię")
    
    cur.execute("""
        SELECT 'opakowanie' as typ, o.id, o.nr_palety, o.nazwa, o.lokalizacja, o.created_at
        FROM magazyn_opakowania o
        LEFT JOIN palety_historia h ON o.id = h.paleta_id AND h.typ_palety = 'opakowanie'
        WHERE h.id IS NULL
        ORDER BY o.created_at DESC
        LIMIT 5
    """)
    bez_historii = cur.fetchall()
    
    if bez_historii:
        print("\nOpakowania bez historii:")
        for row in bez_historii:
            print(f"  ❌ ID={row['id']}, Nr={row['nr_palety'] or 'BRAK'}, {row['nazwa']}, lokalizacja={row['lokalizacja']}, utworzono={row['created_at']}")
    else:
        print("\n✅ Wszystkie opakowania mają historię")
    
    cur.execute("""
        SELECT 'wyrob_gotowy' as typ, p.id, p.nr_palety, p.produkt, p.lokalizacja, p.data_potwierdzenia
        FROM magazyn_palety p
        LEFT JOIN palety_historia h ON p.id = h.paleta_id AND h.typ_palety IN ('wyrob_gotowy', 'wyrób gotowy')
        WHERE h.id IS NULL
        ORDER BY p.data_potwierdzenia DESC
        LIMIT 5
    """)
    bez_historii = cur.fetchall()
    
    if bez_historii:
        print("\nWyroby gotowe bez historii:")
        for row in bez_historii:
            print(f"  ❌ ID={row['id']}, Nr={row['nr_palety'] or 'BRAK'}, {row['produkt']}, lokalizacja={row['lokalizacja']}, potwierdzono={row['data_potwierdzenia']}")
    else:
        print("\n✅ Wszystkie wyroby gotowe mają historię")
    
    conn.close()

if __name__ == '__main__':
    check_history()
