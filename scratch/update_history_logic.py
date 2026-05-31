import re

def update_file():
    with open('app/services/agro_warehouse_service.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacement 1: Moving to history and deleting instead of marking ZUŻYTE (carryover case)
    old1 = """                    # Mark the old roll in magazyn_opakowania as 0 and location ZUŻYTE (carried over)
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'ZUŻYTE', updated_at = NOW() WHERE id = %s",
                        (al['opakowanie_id'],)
                    )"""
    new1 = """                    # Move to history table and delete from current
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania_historia (oryginalny_id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia) "
                        "SELECT id, nr_palety, nazwa, 0, 'ZUŻYTE', nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia "
                        "FROM magazyn_opakowania WHERE id = %s",
                        (al['opakowanie_id'],)
                    )
                    cursor.execute("DELETE FROM magazyn_opakowania WHERE id = %s", (al['opakowanie_id'],))"""
    
    # Replacement 2: Moving to history and deleting instead of marking ZUŻYTE (different material case)
    old2 = """                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'ZUŻYTE', updated_at = NOW() WHERE id = %s",
                        (al['opakowanie_id'],)
                    )"""
    new2 = """                    cursor.execute(
                        "INSERT INTO magazyn_opakowania_historia (oryginalny_id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia) "
                        "SELECT id, nr_palety, nazwa, 0, 'ZUŻYTE', nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia "
                        "FROM magazyn_opakowania WHERE id = %s",
                        (al['opakowanie_id'],)
                    )
                    cursor.execute("DELETE FROM magazyn_opakowania WHERE id = %s", (al['opakowanie_id'],))"""

    # Replacement 3: Avoid setting location to 'Maszyna' during partial pull
    old3 = """                cursor.execute(
                    "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, 'Maszyna')",
                    (nazwa, ilosc_na_maszyne)
                )"""
    new3 = """                cursor.execute(
                    "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)",
                    (nazwa, ilosc_na_maszyne, lokalizacja)
                )"""

    # Replacement 4: Avoid setting location to 'Maszyna' during full pull
    old4 = """                cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = 'Maszyna' WHERE id = %s", (ilosc_na_maszyne, target_opakowanie_id))"""
    new4 = """                cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (ilosc_na_maszyne, target_opakowanie_id))"""

    content = content.replace(old1, new1)
    content = content.replace(old2, new2)
    content = content.replace(old3, new3)
    content = content.replace(old4, new4)

    with open('app/services/agro_warehouse_service.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Replaced occurrences in agro_warehouse_service.py")

if __name__ == "__main__":
    update_file()
