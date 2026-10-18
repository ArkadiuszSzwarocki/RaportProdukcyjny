"""Transactional attendance writes; callers commit or roll back the whole request."""


def lock_employee(cursor, employee_id):
    cursor.execute("SELECT id FROM pracownicy WHERE id=%s FOR UPDATE", (employee_id,))
    if not cursor.fetchone():
        raise ValueError("Nie znaleziono pracownika.")


def insert_attendance_once(cursor, day, employee_id, kind, hours, comment,
                           time_from=None, time_to=None):
    # The employee row must be locked before this check. Preserve distinct exits.
    cursor.execute(
        "SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s "
        "AND typ=%s AND wyjscie_od <=> %s AND wyjscie_do <=> %s LIMIT 1",
        (employee_id, day, kind, time_from, time_to),
    )
    if cursor.fetchone():
        return False
    cursor.execute(
        "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, "
        "komentarz, wyjscie_od, wyjscie_do) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (day, employee_id, kind, hours, comment, time_from, time_to),
    )
    return True
