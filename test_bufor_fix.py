"""
Test weryfikujący że przenies_niezrealizowane po naprawie:
1. Używa source_plan_id (stary plan 1428) jako zasyp_id dla buforu
2. Nie tworzy duplikatów (deduplicacja)
"""
import unittest
from unittest.mock import MagicMock, patch, call

# Minimal mock setup to test the key logic
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_buffer_uses_source_plan_id():
    """Sprawdza że bufor jest linkowany do source_plan_id (stary plan), nie new_id"""
    with open('app/services/planning_service.py', 'r', encoding='utf-8') as f:
        src = f.read()
    
    # Sprawdź że nowy kod jest w pliku
    assert 'buf_zasyp_id = plan_data[\'source_plan_id\']' in src, \
        "BŁĄD: Brak kodu 'buf_zasyp_id = plan_data[source_plan_id]'"
    assert '(buf_zasyp_id, next_data_str' in src, \
        "BŁĄD: INSERT do buforu nie używa buf_zasyp_id"
    # Stary błędny kod nie powinien istnieć
    assert '(new_id, next_data_str, plan_data[\'produkt\']' not in src, \
        "BŁĄD: Stary błędny kod z new_id wciąż istnieje!"
    print("✅ przenies_niezrealizowane: bufor używa source_plan_id")

def test_dedup_check_exists():
    """Sprawdza że istnieje deduplicacja - skip jeśli carry-over już istnieje"""
    with open('app/services/planning_service.py', 'r', encoding='utf-8') as f:
        src = f.read()
    
    assert 'already has carry-over' in src or 'already has carry-over on' in src, \
        "BŁĄD: Brak deduplicacji carry-over"
    assert 'SELECT id FROM bufor WHERE zasyp_id=%s AND DATE(data_planu)=%s' in src, \
        "BŁĄD: Brak zapytania sprawdzającego istniejący carry-over"
    print("✅ przenies_niezrealizowane: deduplicacja carry-over istnieje")

def test_przenies_ajax_reads_to_date():
    """Sprawdza że endpoint czyta to_date (a nie tylko data)"""
    with open('app/blueprints/routes_planning.py', 'r', encoding='utf-8') as f:
        src = f.read()
    
    assert "data.get('to_date') or data.get('data')" in src, \
        "BŁĄD: Endpoint nie obsługuje 'to_date' z AJAX"
    print("✅ przenies_zlecenie_ajax: obsługuje zarówno 'to_date' jak i 'data'")

def test_reschedule_finds_buffer_without_date():
    """Sprawdza że reschedule_plan szuka buforu bez ograniczenia daty"""
    with open('app/services/planning_service.py', 'r', encoding='utf-8') as f:
        src = f.read()
    
    assert "WHERE zasyp_id=%s AND status='aktywny'" in src, \
        "BŁĄD: reschedule_plan wciąż szuka buforu z ograniczeniem daty"
    print("✅ reschedule_plan: szuka buforu po zasyp_id bez ograniczenia daty")

def test_db_state():
    """Weryfikuje stan DB po cleanup"""
    from app.db import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Sprawdź 10.03 bufor
    cur.execute("SELECT id, zasyp_id, tonaz_rzeczywisty FROM bufor WHERE DATE(data_planu)='2026-03-10' AND produkt='FLEX MILCH'")
    rows = cur.fetchall()
    assert len(rows) == 1, f"BŁĄD: Oczekiwano 1 wpis bufor na 10.03, jest {len(rows)}: {rows}"
    assert rows[0][1] == 1428, f"BŁĄD: zasyp_id={rows[0][1]}, oczekiwano 1428"
    assert float(rows[0][2]) == 1190.0, f"BŁĄD: tonaz_rz={rows[0][2]}, oczekiwano 1190"
    print(f"✅ DB: bufor 10.03 ma zasyp_id=1428, tonaz_rz=1190 ✓")
    
    # Sprawdź brak zduplikowanych planów  
    cur.execute("SELECT id FROM plan_produkcji WHERE DATE(data_planu)='2026-03-10' AND produkt='FLEX MILCH' AND sekcja='Zasyp'")
    zasyp_rows = cur.fetchall()
    assert len(zasyp_rows) == 1, f"BŁĄD: Zduplikowane plany Zasyp na 10.03: {zasyp_rows}"
    print(f"✅ DB: jeden plan Zasyp na 10.03 (id={zasyp_rows[0][0]})")
    
    conn.close()

if __name__ == '__main__':
    print("=== Testy weryfikacji naprawy ===\n")
    test_buffer_uses_source_plan_id()
    test_dedup_check_exists()
    test_przenies_ajax_reads_to_date()
    test_reschedule_finds_buffer_without_date()
    test_db_state()
    print("\n✅ WSZYSTKIE TESTY ZALICZONE")
