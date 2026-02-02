from db import get_db_connection, setup_database

print("Uruchamianie migracji bazy danych...")
setup_database()
print("✅ Migracja zakończona!")
