import calendar
from datetime import date


def build_employee_summary(cursor, prac_id, d_od, d_do):
    summary = {'obecnosci': 0, 'typy': {}, 'wyjscia_hours': 0.0}
    try:
        cursor.execute(
            "SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s",
            (prac_id, d_od, d_do),
        )
        summary['obecnosci'] = int(cursor.fetchone()[0] or 0)
    except Exception:
        summary['obecnosci'] = 0

    try:
        cursor.execute(
            "SELECT COALESCE(typ, ''), COALESCE(SUM(ilosc_godzin),0) "
            "FROM obecnosc WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s GROUP BY typ",
            (prac_id, d_od, d_do),
        )
        summary['typy'] = {row[0]: float(row[1] or 0) for row in cursor.fetchall()}
    except Exception:
        summary['typy'] = {}

    try:
        cursor.execute(
            "SELECT COALESCE(SUM(TIME_TO_SEC(wyjscie_do)-TIME_TO_SEC(wyjscie_od))/3600,0) "
            "FROM obecnosc WHERE pracownik_id=%s AND typ='Wyjscie prywatne' AND data_wpisu BETWEEN %s AND %s",
            (prac_id, d_od, d_do),
        )
        summary['wyjscia_hours'] = float(cursor.fetchone()[0] or 0)
    except Exception:
        summary['wyjscia_hours'] = 0.0

    try:
        cursor.execute(
            "SELECT COALESCE(urlop_biezacy,0), COALESCE(urlop_zalegly,0), COALESCE(imie_nazwisko,'') "
            "FROM pracownicy WHERE id=%s",
            (prac_id,),
        )
        row = cursor.fetchone()
        summary['urlop_biezacy'] = int(row[0] or 0) if row else 0
        summary['urlop_zalegly'] = int(row[1] or 0) if row else 0
        summary['imie_nazwisko'] = row[2] if row else ''
    except Exception:
        summary['urlop_biezacy'] = 0
        summary['urlop_zalegly'] = 0
        summary['imie_nazwisko'] = ''

    try:
        cursor.execute(
            "SELECT COALESCE(SUM(ilosc_godzin),0) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s",
            (prac_id, d_od, d_do),
        )
        summary['total_work_hours'] = float(cursor.fetchone()[0] or 0)
    except Exception:
        summary['total_work_hours'] = 0.0

    try:
        cursor.execute(
            "SELECT COALESCE(SUM(ilosc_nadgodzin),0) FROM nadgodziny "
            "WHERE pracownik_id=%s AND data BETWEEN %s AND %s AND status='approved'",
            (prac_id, d_od, d_do),
        )
        summary['nadgodziny_hours'] = float(cursor.fetchone()[0] or 0)
    except Exception:
        summary['nadgodziny_hours'] = 0.0

    try:
        cursor.execute(
            "SELECT COUNT(DISTINCT data_wpisu) FROM obecnosc "
            "WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s "
            "AND (typ LIKE %s OR typ LIKE %s OR typ LIKE %s)",
            (prac_id, d_od, d_do, '%Nieobec%', '%L4%', '%Opieka%'),
        )
        summary['nieobecnosc_days'] = int(cursor.fetchone()[0] or 0)
    except Exception:
        summary['nieobecnosc_days'] = 0

    try:
        cursor.execute(
            "SELECT COALESCE(SUM(DATEDIFF(LEAST(data_do,%s), GREATEST(data_od,%s)) + 1), 0) "
            "FROM wnioski_wolne WHERE pracownik_id=%s AND status='approved' "
            "AND typ LIKE %s AND data_do >= %s AND data_od <= %s",
            (d_do, d_od, prac_id, '%Urlop%', d_od, d_do),
        )
        summary['urlop_days_used'] = int(cursor.fetchone()[0] or 0)
    except Exception:
        summary['urlop_days_used'] = 0

    return summary


def build_hours_calendar(cursor, prac_id, year, month):
    _, days_in_month = calendar.monthrange(year, month)
    cal = []

    for day in range(1, days_in_month + 1):
        day_date = date(year, month, day)
        cursor.execute(
            "SELECT COALESCE(SUM(CASE WHEN typ='Wyjscie prywatne' THEN -ilosc_godzin ELSE ilosc_godzin END),0) "
            "FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s",
            (prac_id, day_date),
        )
        hours = float(cursor.fetchone()[0] or 0)

        cursor.execute(
            "SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s "
            "AND (typ LIKE '%%Nieobecno%%' OR typ LIKE '%%Urlop%%' OR typ LIKE '%%L4%%' OR typ LIKE '%%Nieobecnosc%%')",
            (prac_id, day_date),
        )
        hr_count = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            "SELECT COALESCE(typ, '') FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s",
            (prac_id, day_date),
        )
        typ_rows = [row[0] for row in cursor.fetchall()]
        typ_lower = ' '.join([str(t).lower() for t in typ_rows])
        if 'wyj' in typ_lower and 'prywat' in typ_lower:
            typ_label = 'WP'
        elif 'odb' in typ_lower and 'godz' in typ_lower or 'odbior' in typ_lower:
            typ_label = 'OG'
        elif 'opieka' in typ_lower:
            typ_label = 'OP'
        elif 'urlop' in typ_lower:
            typ_label = 'U'
        elif 'l4' in typ_lower or 'nieobec' in typ_lower:
            typ_label = 'N'
        elif 'obec' in typ_lower:
            typ_label = 'Obecny'
        else:
            typ_label = ''

        cursor.execute("SELECT COUNT(1) FROM raporty_koncowe WHERE data_raportu=%s", (day_date,))
        approved_report = int(cursor.fetchone()[0] or 0) > 0
        cursor.execute(
            "SELECT COUNT(1) FROM wnioski_wolne WHERE pracownik_id=%s AND status='approved' AND data_od <= %s AND data_do >= %s",
            (prac_id, day_date, day_date),
        )
        approved_wn = int(cursor.fetchone()[0] or 0) > 0
        approved = approved_report or approved_wn
        if approved_wn:
            hours = 0.0

        leave_status = None
        try:
            cursor.execute(
                "SELECT status FROM wnioski_wolne WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s "
                "ORDER BY zlozono DESC LIMIT 1",
                (prac_id, day_date, day_date),
            )
            result = cursor.fetchone()
            if result:
                leave_status = result[0]
        except Exception:
            leave_status = None

        assigned = False
        try:
            cursor.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (prac_id, day_date))
            assigned = int(cursor.fetchone()[0] or 0) > 0
        except Exception:
            assigned = False

        nadgodziny_hours = 0.0
        try:
            cursor.execute(
                "SELECT COALESCE(SUM(ilosc_nadgodzin), 0) FROM nadgodziny WHERE pracownik_id=%s AND data=%s AND status='approved'",
                (prac_id, day_date),
            )
            nadgodziny_hours = float(cursor.fetchone()[0] or 0)
        except Exception:
            nadgodziny_hours = 0.0

        cal.append(
            {
                'date': day_date,
                'hours': hours,
                'nadgodziny': nadgodziny_hours,
                'total_hours': hours + nadgodziny_hours,
                'hr': hr_count > 0,
                'approved': approved,
                'typ_label': typ_label,
                'leave_status': leave_status,
                'assigned': assigned,
            }
        )

    return cal
