import mysql.connector
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv(override=True)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3307))
DB_USER = os.getenv('DB_USER', 'biblioteka')
DB_PASS = os.getenv('DB_PASSWORD', '')
DB_NAME = 'biblioteka_testowa'

def seed_orders():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        cursor = conn.cursor()
        
        today = date.today().strftime('%Y-%m-%d')
        
        # Produkty testowe (pobrane z Twojej bazy surowców/receptur jeśli to możliwe, 
        # ale tutaj użyjemy generycznych nazw dla pewności)
        psd_products = [
            "Karma dla psa Premium 10kg",
            "Karma dla kota Sensitive 2kg",
            "Przysmaki treningowe 500g",
            "Mieszanka witaminowa Forte"
        ]
        
        agro_products = [
            "Nawóz uniwersalny NPK 25kg",
            "Zasyp Agro Mix A",
            "Zasyp Agro Mix B",
            "Zasyp Agro Mix C",
            "Podłoże torfowe 50L",
            "Ekstrakt z alg 5L",
            "Środek ochronny Eko 1L",
            "Nawóz dolistny Super"
        ]

        print(f"[*] Dodawanie zleceń do bazy {DB_NAME} na dzień {today}...")

        # Dodaj zlecenia PSD
        for i, prod in enumerate(psd_products):
            cursor.execute("""
                INSERT INTO plan_produkcji (produkt, tonaz, status, data_planu, linia, sekcja, kolejnosc)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (prod, 5000 + (i*1000), 'zaplanowane', today, 'PSD', 'Workowanie', i+1))

        # Dodaj zlecenia AGRO
        for i, prod in enumerate(agro_products):
            cursor.execute("""
                INSERT INTO plan_produkcji_agro (produkt, tonaz, status, data_planu, sekcja, kolejnosc)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (prod, 2000 + (i*500), 'zaplanowane', today, 'Zasyp', i+1))

        conn.commit()
        print(f"[OK] Dodano {len(psd_products)} zleceń PSD oraz {len(agro_products)} zleceń AGRO.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[BŁĄD]: {e}")

if __name__ == "__main__":
    seed_orders()
