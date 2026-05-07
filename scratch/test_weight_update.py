from app.services.magazyny_nowe_service import MagazynyNoweService
from app.db import get_db_connection, get_table_name

def test_update():
    # Test updating a Surowiec on AGRO
    # Let's find one first
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('magazyn_surowce', 'AGRO')
    cursor.execute(f"SELECT id, stan_magazynowy FROM {table} WHERE stan_magazynowy > 0 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print("No pallets found for testing.")
        return
        
    p_id = row['id']
    old_w = row['stan_magazynowy']
    new_w = old_w - 10
    
    print(f"Testing update for {table} ID {p_id}: {old_w} -> {new_w}")
    
    success, msg = MagazynyNoweService.update_weight(p_id, 'Surowiec', new_w, 'test_user', 'AGRO')
    print(f"Result: {success}, {msg}")
    
    # Verify
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT stan_magazynowy FROM {table} WHERE id = %s", (p_id,))
    row_new = cursor.fetchone()
    conn.close()
    
    if row_new:
        print(f"New weight in DB: {row_new['stan_magazynowy']}")
        if row_new['stan_magazynowy'] == new_w:
            print("SUCCESS: Weight updated correctly.")
        else:
            print("FAILURE: Weight did not change!")
    else:
        print("FAILURE: Pallet disappeared!")

if __name__ == "__main__":
    test_update()
