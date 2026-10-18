"""Read attendance and approved requests without omitting or duplicating leave."""
# cspell:words nieobecno
import re
from datetime import timedelta
import unicodedata


def absence_kind(value):
    raw = str(value or '').strip()
    key = ''.join(c for c in unicodedata.normalize('NFKD', raw.casefold()) if not unicodedata.combining(c)).replace('ł', 'l')
    if key in ('obecny', 'obecnosc', 'nadgodziny', ''):
        return None
    if 'wyj' in key:
        return 'Wyjście prywatne'
    if key in ('l4', 'chorobowe', 'zwolnienie', 'zwolnienie lekarskie'):
        return 'L4'
    if 'nieobecno' in key:
        return 'Nieobecność'
    if 'opiek' in key:
        return 'Opieka'
    return raw


def report_time(value):
    if isinstance(value, timedelta):
        minutes = int(value.total_seconds()) // 60
        return f'{minutes // 60:02d}:{minutes % 60:02d}'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    return str(value or '')[:5]


def merge_absences(attendance, requests, line):
    line = line.upper()
    approved = {str(row['request_id']) for row in requests}
    result = {}
    # Approved requests retain the precise leave type and reason.
    for row in list(requests) + list(attendance):
        assigned = {item.upper() for item in str(row.get('assigned') or '').split(',') if item}
        belongs = line in assigned if assigned else (line == ('AGRO' if row.get('widoczny_agro') else 'PSD'))
        if line != 'ALL' and not belongs:
            continue
        kind = absence_kind(row['typ'])
        if not kind:
            continue
        comment = str(row.get('komentarz') or '').strip()
        origin = re.fullmatch(r'Auto z wniosku #(\d+)', comment)
        if origin and origin.group(1) in approved:
            continue
        time_from, time_to = report_time(row.get('time_from')), report_time(row.get('time_to'))
        # Separate partial-day exits must remain separate; full-day repeats do not.
        key_kind = 'urlop' if 'urlop' in kind.casefold() else kind.casefold()
        key = (row['pracownik_id'], key_kind, time_from, time_to)
        if key not in result:
            if kind == 'Wyjście prywatne' and time_from and time_to:
                comment = f'{comment} ({time_from} - {time_to})'.strip()
            result[key] = {'pracownik': row['pracownik'], 'typ': kind, 'komentarz': comment}
    return sorted(result.values(), key=lambda row: (row['typ'], row['pracownik']))


def load_daily_absences(connection, day, line):
    cursor = connection.cursor(dictionary=True)
    cohort = """LEFT JOIN (
        SELECT current_roster.pracownik_id, GROUP_CONCAT(DISTINCT UPPER(COALESCE(NULLIF(current_roster.linia,''),'PSD'))) AS assigned
        FROM obsada_zmiany current_roster
        WHERE current_roster.data_wpisu=(
            SELECT MAX(previous_roster.data_wpisu) FROM obsada_zmiany previous_roster
            WHERE previous_roster.pracownik_id=current_roster.pracownik_id AND previous_roster.data_wpisu<=%s
        ) GROUP BY current_roster.pracownik_id
    ) roster ON roster.pracownik_id=p.id"""
    try:
        cursor.execute("""SELECT p.id AS pracownik_id,p.imie_nazwisko AS pracownik,
            p.widoczny_agro,roster.assigned,o.typ,o.komentarz,
            o.wyjscie_od AS time_from,o.wyjscie_do AS time_to
            FROM obecnosc o JOIN pracownicy p ON p.id=o.pracownik_id """ + cohort +
            " WHERE o.data_wpisu=%s ORDER BY o.id", (day, day))
        attendance = cursor.fetchall()
        cursor.execute("""SELECT w.id AS request_id,p.id AS pracownik_id,p.imie_nazwisko AS pracownik,
            p.widoczny_agro,roster.assigned,w.typ,w.powod AS komentarz,
            w.czas_od AS time_from,w.czas_do AS time_to
            FROM wnioski_wolne w JOIN pracownicy p ON p.id=w.pracownik_id """ + cohort +
            " WHERE w.status='approved' AND %s BETWEEN w.data_od AND w.data_do ORDER BY w.id", (day, day))
        return merge_absences(attendance, cursor.fetchall(), line)
    finally:
        cursor.close()
