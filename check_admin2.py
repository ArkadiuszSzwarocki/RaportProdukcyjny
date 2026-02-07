from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check uzytkownicy table structure
print("Table uzytkownicy structure:")
cursor.execute("DESC uzytkownicy")
cols = cursor.fetchall()
for col in cols:
    print(f"  {col[0]:20s} {col[1]}")

print("\nAdmin users:")
cursor.execute("SELECT id, login, rola FROM uzytkownicy WHERE rola='admin' OR login='admin'")
admins = cursor.fetchall()
if admins:
    for admin in admins:
        print(f"  ID {admin[0]}: {admin[1]} ({admin[2]})")
else:
    print("  ✗ No admin found!")

conn.close()
