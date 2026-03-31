"""Shift Close Service — jedyny punkt wejścia dla logiki zakończenia zmiany.

Jedna publiczna funkcja:
    close_shift_and_get_zip(date_str, session_data, form_data) -> (BytesIO, zip_filename)

Zawiera w sobie CAŁĄ logikę:
  - Pobranie notatek zmianowych z bazy
  - Ustalenie imienia lidera
  - Generowanie raportów (XLS, TXT, PDF)
  - Budowę archiwum ZIP w pamięci (nie zależy od CWD)
  - Zawieszenie planów poprzedniego dnia (best-effort)

Nie importuje nic z report_service.py ani report_generation_service.py.
"""

import zipfile
import logging
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path

from app.db import get_db_connection, get_table_name

logger = logging.getLogger(__name__)

# Absolutna ścieżka do katalogu projektu:
#   __file__ = app/services/shift_close_service.py
#   .parent   = app/services/
#   .parent   = app/
#   .parent   = <project_root>/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAPORTY_DIR = _PROJECT_ROOT / 'raporty'
RAPORTY_TEMP_DIR = _PROJECT_ROOT / 'raporty_temp'


# ---------------------------------------------------------------------------
# Publiczny API
# ---------------------------------------------------------------------------

def close_shift_and_get_zip(date_str: str, session_data: dict, form_data: dict, linia: str = 'PSD'):
    """Zamknij zmianę i zwróć archiwum ZIP z raportami.

    Args:
        date_str:     data w formacie 'YYYY-MM-DD'
        session_data: {'pracownik_id': ..., 'login': ...}
        form_data:    {'lider_id': ..., 'lider_prowadzacy_id': ...}
        linia:        'PSD' lub 'Agro'

    Returns:
        (zip_buffer: BytesIO, zip_filename: str)

    Raises:
        RuntimeError: gdy generowanie raportów się nie powiodło
    """
    logger.info("[SHIFT_CLOSE] === START === date=%s", date_str)

    # 1. Notatki zmianowe
    uwagi = _load_shift_notes(date_str, linia=linia)

    # 2. Lider
    lider_name, uwagi_extra = _get_leader_name(session_data, form_data)
    uwagi = uwagi + uwagi_extra

    # 3. Generuj pliki (XLS, TXT, PDF)
    xls_path, txt_path, pdf_path = _generate_report_files(date_str, uwagi, lider_name, linia=linia)

    # 4. Zbuduj ZIP w pamięci
    zip_buffer, zip_filename = _build_zip(xls_path, txt_path, pdf_path, date_str, linia=linia)

    # 5. Zawieś plany poprzedniego dnia (nie blokuje pobierania nawet gdy zawiedzie)
    _suspend_previous_day_plans(date_str, linia=linia)

    logger.info("[SHIFT_CLOSE] === DONE === zip=%s", zip_filename)
    return zip_buffer, zip_filename


# ---------------------------------------------------------------------------
# Prywatne helpery
# ---------------------------------------------------------------------------

def _load_shift_notes(date_str: str, linia: str = 'PSD') -> str:
    uwagi = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        table_notes = get_table_name('shift_notes', linia)
        cursor.execute(
            f"SELECT note, author, created FROM {table_notes} "
            "WHERE DATE(created) = %s ORDER BY created ASC",
            (date_str,)
        )
        notes = cursor.fetchall()
        cursor.close()
        conn.close()
        if notes:
            uwagi = "NOTATKI ZMIANOWE:\n" + "-" * 50 + "\n"
            for note in notes:
                t = note['created'].strftime('%H:%M:%S') if note['created'] else '??:??:??'
                uwagi += f"\n[{t}] {note['author']}:\n{note['note']}\n"
            logger.info("[SHIFT_CLOSE] Zaladowano %d notatek zmianowych", len(notes))
        else:
            logger.info("[SHIFT_CLOSE] Brak notatek zmianowych dla %s", date_str)
    except Exception as exc:
        logger.warning("[SHIFT_CLOSE] Nie mozna zaladowac notatek: %s", exc)
    return uwagi


def _get_leader_name(session_data: dict, form_data: dict):
    lider_name = "Nieznany"
    uwagi_extra = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        lider_id = form_data.get('lider_id') or session_data.get('pracownik_id')
        if lider_id:
            cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (lider_id,))
            row = cursor.fetchone()
            if row and row[0]:
                lider_name = row[0]
        prowadzacy_id = form_data.get('lider_prowadzacy_id')
        if prowadzacy_id:
            cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (prowadzacy_id,))
            row2 = cursor.fetchone()
            if row2 and row2[0]:
                uwagi_extra = f"\nLider prowadzacy: {row2[0]}\n"
        cursor.close()
        conn.close()
        logger.info("[SHIFT_CLOSE] Lider: %s", lider_name)
    except Exception as exc:
        logger.warning("[SHIFT_CLOSE] Nie mozna pobrac lidera: %s", exc)
        lider_name = session_data.get('login', 'Nieznany')
    return lider_name, uwagi_extra


def _generate_report_files(date_str: str, uwagi: str, lider_name: str, linia: str = 'PSD'):
    """Wywołaj generator raportów i zwróć ABSOLUTNE ścieżki Path (lub None)."""
    from scripts.generator_raportow import generuj_paczke_raportow

    RAPORTY_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    RAPORTY_DIR.mkdir(parents=True, exist_ok=True)

    xls_raw, txt_raw, pdf_raw = generuj_paczke_raportow(date_str, uwagi, lider_name, linia=linia)
    logger.info("[SHIFT_CLOSE] Generator zwrocil: xls=%s txt=%s pdf=%s", xls_raw, txt_raw, pdf_raw)

    xls_abs = _resolve_path(xls_raw)
    txt_abs = _resolve_path(txt_raw)
    pdf_abs = _resolve_pdf_path(pdf_raw)

    logger.info(
        "[SHIFT_CLOSE] Sciezki absolutne: xls=%s(ok=%s) txt=%s(ok=%s) pdf=%s(ok=%s)",
        xls_abs, xls_abs and xls_abs.exists(),
        txt_abs, txt_abs and txt_abs.exists(),
        pdf_abs, pdf_abs and pdf_abs.exists(),
    )
    return xls_abs, txt_abs, pdf_abs


def _resolve_path(path_raw):
    """Zwróć Path absolutny jeśli plik istnieje, w przeciwnym razie None."""
    if not path_raw:
        return None
    p = Path(path_raw)
    if p.is_absolute() and p.exists():
        return p
    # relatywna do korzenia projektu
    p2 = _PROJECT_ROOT / p
    if p2.exists():
        return p2
    return None


def _resolve_pdf_path(pdf_path_raw):
    """PDF jest zapisywany przez scripts/raporty.py do RAPORTY_DIR —
    generator zwraca tylko nazwę pliku (np. 'Raport_2026-03-10.pdf').
    Szukamy pliku po nazwie w RAPORTY_DIR."""
    if not pdf_path_raw:
        return None
    p = Path(pdf_path_raw)
    # ścieżka absolutna i plik istnieje — użyj wprost
    if p.is_absolute() and p.exists():
        return p
    # szukaj po nazwie w RAPORTY_DIR (scripts/raporty.py zapisuje tam PDF)
    by_name = RAPORTY_DIR / p.name
    if by_name.exists():
        return by_name
    # względna do korzenia projektu
    p2 = _PROJECT_ROOT / p
    if p2.exists():
        return p2
    logger.warning("[SHIFT_CLOSE] Plik PDF nie znaleziony: raw=%s, proba=%s", pdf_path_raw, by_name)
    return None


def _build_zip(xls_path, txt_path, pdf_path, date_str: str, linia: str = 'PSD'):
    """Zbuduj ZIP w pamięci (BytesIO) ze wszystkich plików raportów."""
    buf = BytesIO()
    added = 0
    missing = []
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path, label in [(xls_path, 'XLS'), (txt_path, 'TXT'), (pdf_path, 'PDF')]:
            if path and Path(path).exists():
                zf.write(str(path), arcname=Path(path).name)
                added += 1
                logger.info("[SHIFT_CLOSE] Dodano do ZIP: %s", Path(path).name)
            else:
                missing.append(label)
                logger.warning("[SHIFT_CLOSE] Plik niedostepny, pomijam: %s = %s", label, path)
    if added == 0:
        raise RuntimeError(
            f"Zaden plik raportu nie zostal znaleziony. "
            f"Brakujace: {', '.join(missing)}. "
            f"XLS={xls_path}, TXT={txt_path}, PDF={pdf_path}"
        )
    if missing:
        logger.warning("[SHIFT_CLOSE] ZIP niekompletny — brakuje: %s", missing)
    buf.seek(0)
    zip_filename = f"Raporty_{linia}_{date_str}.zip"
    logger.info("[SHIFT_CLOSE] ZIP gotowy: %s (%d plikow, brakuje=%s)", zip_filename, added, missing)
    return buf, zip_filename


def _suspend_previous_day_plans(date_str: str, linia: str = 'PSD'):
    """Zawieś plany z poprzedniego dnia (best-effort, nie rzuca wyjątku)."""
    try:
        prev_day = (datetime.strptime(date_str, '%Y-%m-%d').date() - timedelta(days=1)).strftime('%Y-%m-%d')
        table_plan = get_table_name('plan_produkcji', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE {table_plan} SET status = 'wstrzymane' "
            "WHERE DATE(data_planu) = %s AND status = 'w toku'",
            (prev_day,)
        )
        count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("[SHIFT_CLOSE] Zawieszono %d planow dla %s", count, prev_day)
    except Exception as exc:
        logger.warning("[SHIFT_CLOSE] Nie mozna zawiesc planow poprzedniego dnia: %s", exc)
