import os
import mysql.connector
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load .env
load_dotenv()

DB_CONFIG = {
    'host': 'raportprodukcji.mycloudnas.com',
    'port': 3307,
    'database': 'biblioteka',
    'user': 'biblioteka',
    'password': os.getenv('DB_PASSWORD'),
    'charset': 'utf8mb4'
}

TEST_DATE = '2026-04-05'
TEST_PRODUCT = 'TEST AGRO PRODUCT ' + datetime.now().strftime('%H%M%S')

def run_test():
    print(f"--- STARTING FULL AGRO WORKFLOW TEST ---")
    print(f"Product: {TEST_PRODUCT}")
    print(f"Date: {TEST_DATE}\n")
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. ADD ZASYP PLAN
        print("[1/9] Adding AGRO Zasyp plan...")
        cursor.execute("""
            INSERT INTO plan_produkcji_agro (data_planu, produkt, tonaz, sekcja, status, kolejnosc, typ_produkcji, tonaz_rzeczywisty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (TEST_DATE, TEST_PRODUCT, 5000, 'Zasyp', 'zaplanowane', 1, 'agro', 0))
        zasyp_id = cursor.lastrowid
        print(f"      Zasyp plan added: ID={zasyp_id}")
        
        # 2. START ZASYP
        print("[2/9] Starting Zasyp plan (w toku)...")
        cursor.execute("UPDATE plan_produkcji_agro SET status='w toku', real_start=NOW() WHERE id=%s", (zasyp_id,))
        
        # 3. ADD SZARŻA
        print("[3/9] Adding batch (szarża) to AGRO Zasyp...")
        cursor.execute("""
            INSERT INTO szarze_agro (plan_id, waga, data_dodania, status)
            VALUES (%s, %s, NOW(), 'zarejestrowana')
        """, (zasyp_id, 1000))
        szarza_id = cursor.lastrowid
        print(f"      Batch added: ID={szarza_id}")
        
        # 4. ADD DOSYPKA
        print("[4/9] Adding extra (dosypka) to AGRO batch...")
        cursor.execute("""
            INSERT INTO dosypki_agro (plan_id, szarza_id, nazwa, kg, data_zlecenia, potwierdzone)
            VALUES (%s, %s, %s, %s, NOW(), 0)
        """, (zasyp_id, szarza_id, 'TEST SUROWIEC', 25.5))
        dosypka_id = cursor.lastrowid
        print(f"      Extra added: ID={dosypka_id}")
        
        # 5. CONFIRM DOSYPKA
        print("[5/9] Confirming AGRO extra...")
        cursor.execute("""
            UPDATE dosypki_agro 
            SET potwierdzone = 1, data_potwierdzenia = NOW() 
            WHERE id = %s
        """, (dosypka_id,))
        # Also update plan realized tonnage (simulate part of it)
        cursor.execute("UPDATE plan_produkcji_agro SET tonaz_rzeczywisty = 1000 WHERE id=%s", (zasyp_id,))
        
        # 6. ADD WORKOWANIE PLAN
        print("[6/9] Adding AGRO Workowanie plan (linked to Zasyp)...")
        cursor.execute("""
            INSERT INTO plan_produkcji_agro (data_planu, produkt, tonaz, sekcja, status, kolejnosc, typ_produkcji, zasyp_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (TEST_DATE, TEST_PRODUCT, 5000, 'Workowanie', 'zaplanowane', 1, 'agro', zasyp_id))
        workowanie_id = cursor.lastrowid
        print(f"      Workowanie plan added: ID={workowanie_id}")
        
        # 7. START WORKOWANIE
        print("[7/9] Starting Workowanie (w toku)...")
        cursor.execute("UPDATE plan_produkcji_agro SET status='w toku', real_start=NOW() WHERE id=%s", (workowanie_id,))
        
        # 8. ADD PALLET
        print("[8/9] Adding pallet for AGRO Workowanie...")
        cursor.execute("""
            INSERT INTO palety_agro (plan_id, waga, status, data_dodania)
            VALUES (%s, %s, 'do_przyjecia', NOW())
        """, (workowanie_id, 1000))
        paleta_id = cursor.lastrowid
        print(f"      Pallet added: ID={paleta_id}")
        
        # 9. CONFIRM PALLET IN WAREHOUSE
        print("[9/9] Confirming pallet in AGRO warehouse...")
        cursor.execute("UPDATE palety_agro SET status='przyjeta', data_potwierdzenia=NOW() WHERE id=%s", (paleta_id,))
        # Add to history
        cursor.execute("""
            INSERT INTO magazyn_palety_agro (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, user_login)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (paleta_id, workowanie_id, TEST_DATE, TEST_PRODUCT, 1000, 'TEST_BOT'))
        
        conn.commit()
        print("\n[SUCCESS] Entire AGRO workflow completed successfully in DB!")
        
        # VERIFICATION
        print("\n--- FINAL VERIFICATION ---")
        cursor.execute("SELECT id, status, sekcja, tonaz_rzeczywisty FROM plan_produkcji_agro WHERE produkt=%s", (TEST_PRODUCT,))
        plans = cursor.fetchall()
        for p in plans:
            print(f"Plan ID {p['id']} ({p['sekcja']}): Status = {p['status']}, Tonnage Real = {p['tonaz_rzeczywisty']}kg")
        
        cursor.execute("SELECT COUNT(*) as cnt FROM szarze_agro WHERE plan_id=%s", (zasyp_id,))
        print(f"Batches in DB: {cursor.fetchone()['cnt']}")
        
        cursor.execute("SELECT COUNT(*) as cnt FROM palety_agro WHERE plan_id=%s AND status='przyjeta'", (workowanie_id,))
        print(f"Confirmed pallets in DB: {cursor.fetchone()['cnt']}")
        
        cursor.execute("SELECT COUNT(*) as cnt FROM magazyn_palety_agro WHERE produkt=%s", (TEST_PRODUCT,))
        print(f"Warehouse entries: {cursor.fetchone()['cnt']}")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    run_test()
