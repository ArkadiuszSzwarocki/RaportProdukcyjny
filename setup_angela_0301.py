from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

pracownik_id = 16  # Andżela Heller
data = date(2026, 3, 1)

print("=== DODAWANIE WPISÓW DLA ANDŻELI NA 01.03.2026 ===")

# 1. Sprawdzić czy już są wpisy
cursor.execute("SELECT COUNT(*) as cnt FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, data))
existing = cursor.fetchone()['cnt']
print(f"Istniejące wpisy na 01.03: {existing}")

# 2. Dodać wpis obecności (jeśli nie ma)
if existing == 0:
    cursor.execute(
        "INSERT INTO obecnosc (pracownik_id, data_wpisu, typ, ilosc_godzin) VALUES (%s, %s, %s, %s)",
        (pracownik_id, data, 'Obecny', 8.0)
    )
    conn.commit()
    print("[✓] Dodano wpis obecności: Obecny, 8h")
else:
    print("[i] Wpisy już istnieją")

# 3. Sprawdzić czy jest w obsadzie
cursor.execute("SELECT COUNT(*) as cnt FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, data))
obsada_count = cursor.fetchone()['cnt']
print(f"Wpisy w obsadzie na 01.03: {obsada_count}")

# 4. Dodać do obsady jeśli nie ma
if obsada_count == 0:
    cursor.execute(
        "INSERT INTO obsada_zmiany (pracownik_id, data_wpisu, sekcja) VALUES (%s, %s, %s)",
        (pracownik_id, data, 'Lab')
    )
    conn.commit()
    print("[✓] Dodano do obsady: Lab")
else:
    print("[i] Już jest w obsadzie")

conn.close()
print("\n[OK] Dane na 01.03.2026 zaktualizowane!")
