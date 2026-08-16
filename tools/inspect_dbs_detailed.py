import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

date_str = '2026-05-19'

def inspect_db(db_name):
    print(f"\n=================== INSPECTING: {db_name} ===================")
    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name
        )
        cursor = conn.cursor(dictionary=True)
        
        # 1. plan_produkcji (PSD)
        cursor.execute("SELECT id, data_planu, sekcja, produkt, tonaz, status FROM plan_produkcji WHERE data_planu = %s", (date_str,))
        psd_plans = cursor.fetchall()
        print(f"plan_produkcji (PSD) for {date_str}: {len(psd_plans)} records")
        for p in psd_plans:
            print(f"  ID {p['id']}: {p['sekcja']} - {p['produkt']} ({p['tonaz']}t, status: {p['status']})")
            
        # 2. plan_produkcji_agro (AGRO)
        cursor.execute("SELECT id, data_planu, sekcja, produkt, tonaz, status FROM plan_produkcji_agro WHERE data_planu = %s", (date_str,))
        agro_plans = cursor.fetchall()
        print(f"plan_produkcji_agro (AGRO) for {date_str}: {len(agro_plans)} records")
        for p in agro_plans:
            print(f"  ID {p['id']}: {p['sekcja']} - {p['produkt']} ({p['tonaz']}t, status: {p['status']})")
            
        # Let's see other related tables count
        psd_plan_ids = [p['id'] for p in psd_plans]
        agro_plan_ids = [p['id'] for p in agro_plans]
        
        if psd_plan_ids:
            # szarze
            cursor.execute(f"SELECT COUNT(*) FROM szarze WHERE plan_id IN ({','.join(map(str, psd_plan_ids))})")
            print(f"  szarze (PSD): {cursor.fetchone()['COUNT(*)']} records")
            # palety_workowanie
            cursor.execute(f"SELECT COUNT(*) FROM palety_workowanie WHERE plan_id IN ({','.join(map(str, psd_plan_ids))})")
            print(f"  palety_workowanie (PSD): {cursor.fetchone()['COUNT(*)']} records")
            # bufor
            cursor.execute(f"SELECT COUNT(*) FROM bufor WHERE zasyp_id IN ({','.join(map(str, psd_plan_ids))})")
            print(f"  bufor (PSD): {cursor.fetchone()['COUNT(*)']} records")
            # dosypki
            cursor.execute(f"SELECT COUNT(*) FROM dosypki WHERE plan_id IN ({','.join(map(str, psd_plan_ids))})")
            print(f"  dosypki (PSD): {cursor.fetchone()['COUNT(*)']} records")
            
        if agro_plan_ids:
            # szarze_agro
            cursor.execute(f"SELECT COUNT(*) FROM szarze_agro WHERE plan_id IN ({','.join(map(str, agro_plan_ids))})")
            print(f"  szarze_agro (AGRO): {cursor.fetchone()['COUNT(*)']} records")
            # palety_agro
            cursor.execute(f"SELECT COUNT(*) FROM palety_agro WHERE plan_id IN ({','.join(map(str, agro_plan_ids))})")
            print(f"  palety_agro (AGRO): {cursor.fetchone()['COUNT(*)']} records")
            # bufor_agro
            cursor.execute(f"SELECT COUNT(*) FROM bufor_agro WHERE zasyp_id IN ({','.join(map(str, agro_plan_ids))})")
            print(f"  bufor_agro (AGRO): {cursor.fetchone()['COUNT(*)']} records")
            
        # zasyp_etapy and parameters for both
        cursor.execute("SELECT COUNT(*) FROM zasyp_etapy WHERE data_planu = %s", (date_str,))
        print(f"zasyp_etapy: {cursor.fetchone()['COUNT(*)']} records")
        cursor.execute("SELECT COUNT(*) FROM zasyp_etapy_parametry WHERE data_planu = %s", (date_str,))
        print(f"zasyp_etapy_parametry: {cursor.fetchone()['COUNT(*)']} records")
        
        # mom_rozliczenia
        cursor.execute("SELECT COUNT(*) FROM mom_rozliczenia WHERE data_planu = %s", (date_str,))
        print(f"mom_rozliczenia: {cursor.fetchone()['COUNT(*)']} records")
        
        # agro_workowanie_rozliczenie
        cursor.execute("SELECT COUNT(*) FROM agro_workowanie_rozliczenie WHERE data_planu = %s", (date_str,))
        print(f"agro_workowanie_rozliczenie: {cursor.fetchone()['COUNT(*)']} records")

        conn.close()
    except Exception as e:
        print("Error inspecting database:", e)

inspect_db('biblioteka_testowa')
inspect_db('biblioteka')
