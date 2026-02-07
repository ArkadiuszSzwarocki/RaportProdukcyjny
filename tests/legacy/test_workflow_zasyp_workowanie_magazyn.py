"""
Integration test for Zasyp → Workowanie → Magazyn workflow.

This test verifies the complete workflow:
1. Add szarża (batch) to Zasyp (sekcja='Zasyp')
   → automatically creates buffer in Workowanie
2. Add paletki (packages) to Workowanie buffer
   → each paleta gets status='do_przyjecia' (unconfirmed)
3. Verify that Magazyn can see and confirm the paletki

This test bypasses the Flask app and directly tests the routes.
"""

import pytest
from datetime import date
from app import app, get_db_connection
import db


@pytest.fixture
def client():
    """Create a test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def setup_db():
    """Setup test database."""
    db.setup_database()
    yield
    # Cleanup is handled by test isolation


def test_workflow_zasyp_workowanie_magazyn(client, setup_db):
    """
    Test complete workflow:
    1. Create szarża on Zasyp
    2. Verify buffer created on Workowanie
    3. Add paletki to buffer
    4. Verify Magazyn can see them
    """
    
    # SETUP: Mock session with admin privileges
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 1
        sess['rola'] = 'planista'
        sess['login'] = 'test_admin'
    
    # Step 1: Create test data
    data_planu = str(date.today())
    produkt = "Test_Product_001"
    tonaz = 100  # 100 kg
    typ_produkcji = "worki_zgrzewane_25"

    # Step 2: Add szarża to Zasyp (should auto-create Workowanie buffer)
    response = client.post('/dodaj_plan', data={
        'data_planu': data_planu,
        'produkt': produkt,
        'tonaz': tonaz,
        'sekcja': 'Zasyp',
        'typ_produkcji': typ_produkcji
    }, follow_redirects=False)

    assert response.status_code in [302, 200], f"Failed to add Zasyp plan: {response.status_code}"

    assert response.status_code in [302, 200], f"Failed to add Zasyp plan: {response.status_code}"
    
    # Step 3: Verify Zasyp plan was created
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Zasyp' AND typ_produkcji=%s LIMIT 1",
        (data_planu, produkt, typ_produkcji)
    )
    zasyp_plan = cursor.fetchone()
    assert zasyp_plan is not None, "Zasyp plan not created"
    zasyp_plan_id = zasyp_plan[0]
    
    # Step 4: Verify Workowanie buffer was auto-created
    cursor.execute(
        "SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND typ_produkcji=%s LIMIT 1",
        (data_planu, produkt, typ_produkcji)
    )
    workowanie_plan = cursor.fetchone()
    assert workowanie_plan is not None, "Workowanie buffer not auto-created"
    workowanie_plan_id = workowanie_plan[0]
    
    print(f"✓ Zasyp plan created: id={zasyp_plan_id}")
    print(f"✓ Workowanie buffer auto-created: id={workowanie_plan_id}")
    
    # Step 5: Add paletki to Workowanie buffer
    waga_paleta1 = 25
    waga_paleta2 = 25
    waga_paleta3 = 50
    
    for waga in [waga_paleta1, waga_paleta2, waga_paleta3]:
        response = client.post(
            f'/api/dodaj_palete/{workowanie_plan_id}',
            data={'waga_palety': waga},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert response.status_code in [200, 302], f"Failed to add paleta: {response.status_code}"
        print(f"✓ Added paleta with waga={waga}kg")
    
    # Step 6: Verify paletki were added to Workowanie with correct status
    cursor.execute(
        "SELECT COUNT(*), SUM(waga) FROM palety_workowanie WHERE plan_id=%s AND status='do_przyjecia'",
        (workowanie_plan_id,)
    )
    count_result = cursor.fetchone()
    paleta_count = count_result[0]
    paleta_sum_waga = count_result[1] if count_result[1] else 0
    
    assert paleta_count == 3, f"Expected 3 paletki, got {paleta_count}"
    assert paleta_sum_waga == 100, f"Expected total waga=100, got {paleta_sum_waga}"
    
    print(f"✓ Added {paleta_count} paletki with total waga={paleta_sum_waga}kg")
    
    # Step 7: Verify Magazyn can see the paletki
    cursor.execute(
        "SELECT COUNT(*) FROM palety_workowanie pw "
        "JOIN plan_produkcji p ON pw.plan_id = p.id "
        "WHERE DATE(pw.data_dodania) = %s AND p.sekcja = 'Workowanie' AND pw.waga > 0",
        (data_planu,)
    )
    magazyn_count = cursor.fetchone()[0]
    
    assert magazyn_count >= 3, f"Magazyn should see at least 3 paletki, saw {magazyn_count}"
    
    print(f"✓ Magazyn can see {magazyn_count} paletki")
    
    # Step 8: Verify Workowanie buffer totals are correct
    cursor.execute(
        "SELECT tonaz_rzeczywisty FROM plan_produkcji WHERE id=%s",
        (workowanie_plan_id,)
    )
    tonaz_rzeczywisty = cursor.fetchone()[0]
    
    assert tonaz_rzeczywisty == 100, f"Expected tonaz_rzeczywisty=100, got {tonaz_rzeczywisty}"
    
    print(f"✓ Workowanie buffer tonaz_rzeczywisty={tonaz_rzeczywisty}kg (matches total paletki)")
    
    conn.close()
    
    print("\n✅ Complete workflow test PASSED!")
    print("   Zasyp → auto-create Workowanie buffer → add paletki → Magazyn sees them")



def test_dodaj_palete_only_workowanie():
    """Test that paletki can ONLY be added to Workowanie (not Zasyp)."""
    
    db.setup_database()
    
    data_planu = str(date.today())
    produkt = "Test_Product_002"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create a Zasyp plan
    cursor.execute(
        "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (data_planu, produkt, 50, 'zaplanowane', 'Zasyp', 1, 'worki_zgrzewane_25')
    )
    zasyp_plan_id = cursor.lastrowid
    
    # Create a Magazyn plan
    cursor.execute(
        "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (data_planu, produkt, 50, 'zaplanowane', 'Magazyn', 2, 'worki_zgrzewane_25')
    )
    magazyn_plan_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Mock session with user privileges
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['user_id'] = 1
            sess['rola'] = 'pracownik'
        
        # Test 1: Cannot add paleta to Zasyp plan
        response = client.post(
            f'/api/dodaj_palete/{zasyp_plan_id}',
            data={'waga_palety': 25},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert response.status_code == 400, f"Should reject Zasyp plan, got {response.status_code}"
        
        print(f"✓ Correctly rejected paletka add to Zasyp plan (status={response.status_code})")
        
        # Test 2: Cannot add paleta to Magazyn plan
        response = client.post(
            f'/api/dodaj_palete/{magazyn_plan_id}',
            data={'waga_palety': 25},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert response.status_code == 400, f"Should reject Magazyn plan, got {response.status_code}"
        
        print(f"✓ Correctly rejected paletka add to Magazyn plan (status={response.status_code})")
    
    print("\n✅ Paletka restriction test PASSED!")
    print("   Paletki can ONLY be added to Workowanie")

    print("   Paletki can ONLY be added to Workowanie")


def test_dodaj_palete_rejects_zero_weight():
    """Test that paletki with 0 or negative weight are rejected."""
    
    db.setup_database()
    
    data_planu = str(date.today())
    produkt = "Test_Product_003"
    typ_produkcji = "worki_zgrzewane_25"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create a Workowanie buffer plan
    cursor.execute(
        "INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (data_planu, produkt, 50, 'zaplanowane', 'Workowanie', 1, typ_produkcji)
    )
    workowanie_plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Mock session
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['user_id'] = 1
            sess['rola'] = 'pracownik'
        
        # Test 1: Reject zero weight
        response = client.post(
            f'/api/dodaj_palete/{workowanie_plan_id}',
            data={'waga_palety': 0},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert response.status_code == 400, f"Should reject 0 weight, got {response.status_code}"
        
        print(f"✓ Correctly rejected paleta with 0 weight")
        
        # Test 2: Reject negative weight
        response = client.post(
            f'/api/dodaj_palete/{workowanie_plan_id}',
            data={'waga_palety': -10},
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert response.status_code == 400, f"Should reject negative weight, got {response.status_code}"
        
        print(f"✓ Correctly rejected paleta with negative weight")
    
    print("\n✅ Weight validation test PASSED!")



if __name__ == '__main__':
    pytest.main([__file__, '-v'])
