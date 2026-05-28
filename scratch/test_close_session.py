from app import create_app
from app.services.inwentaryzacja_service import InwentaryzacjaService
from database import get_db_connection

app = create_app()

with app.app_context():
    # Let's say session 52 is on R06
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM magazyn_inwentaryzacja_sesje WHERE id = 52")
    sesja = cursor.fetchone()
    conn.close()
    
    if sesja:
        loc = sesja['lokalizacja']
        print(f"Session 52 location: {loc}")
        pallets = InwentaryzacjaService.get_pallets_at_location(loc, sesja_id=52)
        print(f"Pallets physically found (expected) by get_pallets_at_location: {len(pallets)}")
        
        system_count = len(pallets)
        counted = len([p for p in pallets if p.get('counted')])
        missing = [p for p in pallets if not p.get('counted')]
        
        print(f"System total: {system_count}")
        print(f"Counted: {counted}")
        print(f"Missing (Not counted): {len(missing)}")
