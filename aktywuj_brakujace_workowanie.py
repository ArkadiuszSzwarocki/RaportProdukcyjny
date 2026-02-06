#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt aktywuje (tworzy) brakujące Workowanie dla zleceń Zasyp z dzisiaj.
Te zlecenia zostały utworzone PRZED naprawą auto-tworzenia Workowania.
"""

import mysql.connector
from datetime import datetime, timedelta
from config import DB_CONFIG

def get_db_connection():
    """Nawiąż połączenie z bazą"""
    return mysql.connector.connect(**DB_CONFIG)

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Data dzisiejsza
    today = datetime.now().date()
    
    print(f"🔍 Szukam zleceń Zasyp z dnia: {today}")
    
    # Znajdź wszystkie Zasypy z dzisiaj (tabela: plan_produkcji, sekcja='Zasyp')
    query_zasyp = """
        SELECT id, produkt, tonaz, typ_produkcji, kolejnosc
        FROM plan_produkcji
        WHERE sekcja = 'Zasyp'
        AND data_planu = %s
        ORDER BY id ASC
    """
    
    cursor.execute(query_zasyp, (today,))
    zasypy = cursor.fetchall()
    
    print(f"✅ Znaleziono {len(zasypy)} zleceń Zasyp z dzisiaj:")
    for z in zasypy:
        print(f"   - ID: {z['id']}, Produkt: {z['produkt']}, Tonaz: {z['tonaz']}, Sekcja: {z['typ_produkcji']}")
    
    print("\n📋 Sprawdzam które mają Workowanie...")
    
    brakujace = []
    for zasyp in zasypy:
        zasyp_id = zasyp['id']
        
        # Sprawdź czy istnieje Workowanie dla tego PRODUKTU tego samego dnia
        # (Workowanie nie ma explicit powiązania, ale ma ten sam produkt i data_planu)
        query_workowanie = """
            SELECT id FROM plan_produkcji
            WHERE sekcja = 'Workowanie'
            AND data_planu = %s
            AND produkt = %s
            AND typ_produkcji = %s
        """
        cursor.execute(query_workowanie, (today, zasyp['produkt'], zasyp['typ_produkcji']))
        resultado = cursor.fetchone()
        
        if resultado:
            print(f"   ✓ Zasyp {zasyp_id} ({zasyp['produkt']}) -> Workowanie {resultado['id']} OK")
        else:
            print(f"   ✗ Zasyp {zasyp_id} ({zasyp['produkt']}) -> BRAK Workowania!")
            brakujace.append(zasyp)
    
    if not brakujace:
        print("\n✅ Wszystkie Zasypy mają Workowanie!")
        cursor.close()
        conn.close()
        return
    
    print(f"\n🔧 Tworzę brakujące Workowanie ({len(brakujace)} sztuk)...")
    
    for zasyp in brakujace:
        # Pobierz najwyższą kolejnosc dla dzisiaj
        cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (today,))
        res = cursor.fetchone()
        nowy_kolejnosc = (res['MAX(kolejnosc)'] if res and res['MAX(kolejnosc)'] else 0) + 1
        
        insert_query = """
            INSERT INTO plan_produkcji 
            (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_query, (
            today,                   # data_planu
            zasyp['produkt'],        # produkt
            0,                       # tonaz - na początek 0 dla Workowania
            'w toku',                # status - domyślny status aktywny
            'Workowanie',            # sekcja
            nowy_kolejnosc,          # kolejnosc
            zasyp['typ_produkcji'],  # typ_produkcji
            0                        # tonaz_rzeczywisty - na początek 0
        ))
        
        workowanie_id = cursor.lastrowid
        print(f"   ✅ Utworzono Workowanie ID:{workowanie_id} dla produktu '{zasyp['produkt']}' (Zasyp ID:{zasyp['id']})")
    
    conn.commit()
    print(f"\n✨ Gotowe! Aktywowano {len(brakujace)} brakujących Workowanie")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
