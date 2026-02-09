"""
Test: Sprawdzenie czy Frontend prawidłowo wyświetla uszkodzone_worki z Workowania dla Zasyp
POST request do routes_planista.get_planista()
"""
import sys
import json
from datetime import date

# Simula co otrzyma frontend
def get_planista_data():
    from app.db import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    dzisiaj = date.today()
    
    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
               tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
        FROM plan_produkcji 
        WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
        ORDER BY kolejnosc
    """, (dzisiaj,))
    
    plany = cursor.fetchall()
    plany_list = [list(p) for p in plany]
    
    # Symuluj calculate_kg_per_hour (ze starej implementacji)
    def calculate_kg_per_hour(typ_prod):
        if typ_prod == 'bigbag':
            return 700
        elif typ_prod == 'workowanie':
            return 600
        return 1000
    
    # Pętla jak w routes_planista
    for p in plany_list:
        waga_plan = p[3] if p[3] else 0
        typ_prod = p[9]
        
        # Oblicz czas
        norma = calculate_kg_per_hour(typ_prod) if typ_prod else calculate_kg_per_hour('bigbag')
        czas_trwania_min = int((waga_plan / norma) * 60) if norma > 0 else 0
        
        # Dodaj czas na indeks 12
        p.append(czas_trwania_min)
        
        # Cross-section mapping - pobierz uszkodzone_worki z Workowania
        sekcja = (p[1] or '').lower()
        if sekcja == 'zasyp':
            cursor.execute(
                "SELECT COALESCE(uszkodzone_worki, 0) FROM plan_produkcji WHERE DATE(data_planu)=%s AND sekcja='Workowanie' AND produkt=%s LIMIT 1",
                (dzisiaj, p[2])
            )
            work_result = cursor.fetchone()
            if work_result:
                p[11] = work_result[0]
    
    conn.close()
    return plany_list

if __name__ == "__main__":
    try:
        plany = get_planista_data()
        
        print("\n" + "="*100)
        print("🔍 TEST: Co otrzyma Frontend z routes_planista.get_planista()")
        print("="*100)
        print(f"\nNaleziono {len(plany)} planów\n")
        
        print("INDEKSY: [0]ID | [1]SEKCJA | [2]PRODUKT | [3]TONAZ | [11]USZKODZONE | [12]CZAS(MIN)\n")
        print("-"*100)
        
        for p in plany[:8]:
            sekcja = (p[1] or '').lower()
            uszkodzone = p[11] if len(p) > 11 else "BRAK"
            czas = p[12] if len(p) > 12 else "BRAK"
            
            status_marker = "✓" if sekcja == 'zasyp' else "•"
            print(f"{status_marker} [{p[0]:3}] {sekcja:12} | {p[2]:25} | {p[3]:6} kg | uszkodzone={uszkodzone:3} | czas={czas:4} min")
        
        print("\n" + "="*100)
        print("✅ Frontend będzie wyświetlać:")
        print("   - Kolumna 'Czas': p[12]")
        print("   - Kolumna 'Uszkodzone Worki': p[11]")
        print("="*100 + "\n")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
