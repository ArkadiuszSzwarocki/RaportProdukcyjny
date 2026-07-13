"""Serwis podziału palet — skalowalna logika biznesowa z zapisem historii."""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any

from app.db import get_db_connection, get_table_name
from app.utils.pallet_id import generate_pallet_id

LINIE = ('AGRO', 'PSD')
INVENTORY_SOURCES = frozenset({'surowiec', 'opakowanie', 'dodatek'})
FINISHED_SOURCES = frozenset({'magazyn', 'produkcja'})

HISTORIA_TYP: dict[str, str] = {
    'magazyn': 'wyrob_gotowy',
    'produkcja': 'wyrob_gotowy',
    'surowiec': 'surowiec',
    'opakowanie': 'opakowanie',
    'dodatek': 'dodatek',
}

PALLET_ID_TYPE: dict[str, str] = {
    'magazyn': 'wyrób gotowy',
    'produkcja': 'wyrób gotowy',
    'surowiec': 'surowiec',
    'opakowanie': 'opakowanie',
    'dodatek': 'dodatek',
}

SSCC_SEARCH_SPECS: tuple[dict[str, Any], ...] = (
    {
        'source': 'magazyn',
        'table_base': 'magazyn_palety',
        'select': (
            "id, nr_palety, waga_netto AS waga, produkt, COALESCE(lokalizacja, IF(%s='AGRO', 'MGW02', 'MGW01')) AS lokalizacja, "
            "plan_id, 'magazyn' AS source, %s AS linia, data_planu"
        ),
        'where': "UPPER(nr_palety) = UPPER(%s) AND waga_netto > 0",
    },
    {
        'source': 'produkcja',
        'table_base': 'palety_workowanie',
        'select': (
            "pw.id, pw.nr_palety, pw.waga, p.produkt, IF(%s='AGRO', 'MGW02', 'MGW01') AS lokalizacja, "
            "pw.plan_id, 'produkcja' AS source, %s AS linia, p.data_planu AS data_planu"
        ),
        'from_extra': (
            "JOIN {plan_table} p ON pw.plan_id = p.id"
        ),
        'where': "UPPER(pw.nr_palety) = UPPER(%s) AND pw.waga > 0",
        'alias': 'pw',
    },
    {
        'source': 'surowiec',
        'table_base': 'magazyn_surowce',
        'select': (
            "id, nr_palety, stan_magazynowy AS waga, nazwa AS produkt, lokalizacja, "
            "NULL AS plan_id, 'surowiec' AS source, %s AS linia, data_produkcji AS data_planu"
        ),
        'where': "UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0",
    },
    {
        'source': 'opakowanie',
        'table_base': 'magazyn_opakowania',
        'select': (
            "id, nr_palety, stan_magazynowy AS waga, nazwa AS produkt, lokalizacja, "
            "NULL AS plan_id, 'opakowanie' AS source, %s AS linia, data_produkcji AS data_planu"
        ),
        'where': "UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0",
    },
    {
        'source': 'dodatek',
        'table_base': 'magazyn_dodatki',
        'linie': ('PSD',),
        'select': (
            "id, nr_palety, stan_magazynowy AS waga, nazwa AS produkt, lokalizacja, "
            "NULL AS plan_id, 'dodatek' AS source, 'PSD' AS linia, data_produkcji AS data_planu"
        ),
        'where': "UPPER(nr_palety) = UPPER(%s) AND stan_magazynowy > 0",
    },
)


class PalletSplitService:
    """Podział palety na matkę (pomniejszoną) i nową paletę potomną."""

    @staticmethod
    def find_by_sscc(sscc: str) -> dict[str, Any] | None:
        sscc = str(sscc or '').strip()
        if not sscc:
            return None

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for spec in SSCC_SEARCH_SPECS:
                linie = spec.get('linie', LINIE)
                for linia in linie:
                    table = (
                        spec['table_base']
                        if spec['source'] == 'dodatek'
                        else get_table_name(spec['table_base'], linia)
                    )
                    alias = spec.get('alias', '')
                    from_clause = f"{table} {alias}".strip()
                    from_extra = spec.get('from_extra', '')
                    if from_extra:
                        plan_table = get_table_name('plan_produkcji', linia)
                        from_extra = from_extra.format(plan_table=plan_table)
                        from_clause = f"{from_clause} {from_extra}"

                    query = (
                        f"SELECT {spec['select']} FROM {from_clause} "
                        f"WHERE {spec['where']} LIMIT 1"
                    )
                    
                    if spec['source'] == 'magazyn':
                        params = (linia, linia, sscc)
                    elif spec['source'] == 'produkcja':
                        params = (linia, linia, sscc)
                    elif spec['source'] != 'dodatek':
                        params = (linia, sscc)
                    else:
                        params = (sscc,)
                        
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    if row:
                        return row
            return None
        finally:
            conn.close()

    @staticmethod
    def find_by_id(mother_id: int, source: str, requested_linia: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
        source = str(source or '').strip().lower()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if source in INVENTORY_SOURCES:
                if source == 'dodatek':
                    cursor.execute("SELECT * FROM magazyn_dodatki WHERE id = %s", (mother_id,))
                    row = cursor.fetchone()
                    return (row, 'PSD') if row else (None, None)

                table_base = 'magazyn_surowce' if source == 'surowiec' else 'magazyn_opakowania'
                linie_do_sprawdzenia = [requested_linia] if requested_linia else LINIE
                for linia in linie_do_sprawdzenia:
                    table = get_table_name(table_base, linia)
                    cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (mother_id,))
                    row = cursor.fetchone()
                    if row:
                        return row, linia
                return None, None

            table_base = 'magazyn_palety' if source == 'magazyn' else 'palety_workowanie'
            linie_do_sprawdzenia = [requested_linia] if requested_linia else LINIE
            for linia in linie_do_sprawdzenia:
                table = get_table_name(table_base, linia)
                cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (mother_id,))
                row = cursor.fetchone()
                if row:
                    return row, linia
            return None, None
        finally:
            conn.close()

    @staticmethod
    def split_pallet(
        mother_sscc: str = None,
        weight_to_take: float = 0.0,
        user_login: str = 'System',
        linia: str | None = None,
        mother_id: int = None,
        source: str = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        weight_to_take = round(float(weight_to_take or 0), 3)

        if weight_to_take <= 0:
            return False, 'Błędne dane wejściowe (waga musi być > 0).', None

        # Szukamy po SSCC jeśli podano (priorytet)
        pal = None
        if mother_sscc:
            pal = PalletSplitService.find_by_sscc(mother_sscc)
            if pal:
                linia = pal.get('linia', linia)
                source = pal['source']
                mother_id = pal['id']

        # Fallback na stary sposób wyszukiwania po ID
        if not pal and mother_id and source:
            source = str(source or '').strip().lower()
            pal, found_linia = PalletSplitService.find_by_id(mother_id, source, requested_linia=linia)
            if pal and found_linia:
                linia = found_linia

        if not pal:
            return False, 'Nie znaleziono palety bazowej w bazie danych.', None

        if pal.get('is_blocked'):
            return False, 'Paleta jest zablokowana (np. przypisana do dokumentu) i nie może zostać podzielona.', None

        # Kategoryczny zakaz dzielenia palet MIX
        nr_palety_check = str(pal.get('nr_palety', '')).upper()
        produkt_check = str(pal.get('produkt') or pal.get('nazwa') or '').upper()
        if nr_palety_check.startswith('MIX') or produkt_check.startswith('MIX'):
            return False, 'Kategoryczny zakaz dzielenia palet MIX.', None

        current_weight = PalletSplitService._get_weight(pal, source)
        if weight_to_take >= current_weight:
            return (
                False,
                f'Waga do zabrania ({weight_to_take} kg) jest równa lub większa niż stan palety ({current_weight} kg).',
                None,
            )

        new_weight = round(current_weight - weight_to_take, 3)
        mother_sscc = pal.get('nr_palety') or str(mother_id)
        new_sscc = generate_pallet_id(linia, PALLET_ID_TYPE[source])
        now_dt = datetime.now()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if source in INVENTORY_SOURCES:
                result = PalletSplitService._split_inventory(
                    cursor, pal, source, linia, mother_id, new_sscc,
                    current_weight, new_weight, weight_to_take,
                    user_login, now_dt, mother_sscc,
                )
            else:
                result = PalletSplitService._split_finished(
                    cursor, pal, source, linia, mother_id, new_sscc,
                    new_weight, weight_to_take, user_login, now_dt, mother_sscc,
                )

            conn.commit()
            return True, 'Podział zakończony pomyślnie.', result
        except Exception as exc:
            conn.rollback()
            raise exc
        finally:
            conn.close()

    @staticmethod
    def build_label_url(new_pallet: dict[str, Any]) -> str:
        source = new_pallet.get('source', '')
        if source in INVENTORY_SOURCES:
            p_type_to_use = source
            if str(new_pallet.get('nr_palety', '')).startswith('MIX'):
                p_type_to_use = 'wyrob_gotowy'
                
            query_params = urllib.parse.urlencode({
                'nr_palety': new_pallet.get('nr_palety', ''),
                'product_name': new_pallet.get('produkt') or new_pallet.get('nazwa') or '',
                'nr_partii': new_pallet.get('nr_partii') or '',
                'data_produkcji': str(new_pallet.get('data_produkcji') or ''),
                'data_przydatnosci': str(new_pallet.get('termin_przydatnosci') or new_pallet.get('data_przydatnosci') or ''),
                'qty': new_pallet.get('waga', 0),
                'p_type': p_type_to_use,
                'linia': new_pallet.get('linia', 'AGRO'),
            })
            return f"/magazyn-dostawy/podglad-etykiety?{query_params}"

        return (
            f"/magazyn-dostawy/podglad-etykiety-system/{new_pallet['id']}"
            f"?linia={new_pallet.get('linia', 'AGRO')}"
        )

    @staticmethod
    def _get_weight(pal: dict[str, Any], source: str) -> float:
        # find_by_sscc ujednolica wszystkie kolumny wagowe do aliasu 'waga'
        if 'waga' in pal and pal['waga'] is not None:
            return float(pal['waga'])
            
        # Fallback dla wyników z find_by_id (gdzie robimy SELECT *)
        if source in INVENTORY_SOURCES:
            return float(pal.get('stan_magazynowy') or 0)
        if source == 'magazyn':
            return float(pal.get('waga_netto') or 0)
        return float(pal.get('waga') or 0)

    @staticmethod
    def _log_historia(
        cursor,
        paleta_id: int,
        linia: str,
        typ_palety: str,
        akcja: str,
        user_login: str,
        komentarz: str,
        lokalizacja_zrodlowa: str | None = None,
        lokalizacja_docelowa: str | None = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO palety_historia
                (paleta_id, linia, typ_palety, akcja,
                 lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                paleta_id, linia, typ_palety, akcja,
                lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login,
            ),
        )

    @staticmethod
    def _log_magazyn_ruch(
        cursor,
        linia: str,
        surowiec_id: int,
        typ_ruchu: str,
        ilosc: float,
        ilosc_po: float,
        lokalizacja: str | None,
        user_login: str,
        now_dt: datetime,
        komentarz: str,
        nazwa: str | None = None,
    ) -> None:
        table_ruch = get_table_name('magazyn_ruch', linia)
        cursor.execute(
            f"""
            INSERT INTO {table_ruch}
                (surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po,
                 lokalizacja, status, autor_login, autor_data, komentarz)
            VALUES (%s, %s, %s, %s, %s, %s, 'POTWIERDZONE', %s, %s, %s)
            """,
            (
                surowiec_id, nazwa, typ_ruchu, ilosc, ilosc_po,
                lokalizacja, user_login, now_dt, komentarz,
            ),
        )

    @staticmethod
    def _split_inventory(
        cursor,
        pal: dict[str, Any],
        source: str,
        linia: str,
        mother_id: int,
        new_sscc: str,
        current_weight: float,
        new_weight: float,
        weight_to_take: float,
        user_login: str,
        now_dt: datetime,
        mother_sscc: str,
    ) -> dict[str, Any]:
        if source == 'surowiec':
            table = get_table_name('magazyn_surowce', linia)
        elif source == 'opakowanie':
            table = get_table_name('magazyn_opakowania', linia)
        else:
            table = 'magazyn_dodatki'

        mother_lokalizacja = pal.get('lokalizacja')
        child_lokalizacja = mother_lokalizacja if mother_lokalizacja else 'BF_MS01'
        typ_palety = HISTORIA_TYP[source]
        product_name = pal.get('nazwa')

        cursor.execute(
            f"UPDATE {table} SET stan_magazynowy = %s WHERE id = %s",
            (new_weight, mother_id),
        )
        cursor.execute(
            f"""
            INSERT INTO {table} (
                nr_palety, nazwa, stan_magazynowy, data_produkcji, data_przydatnosci,
                nr_partii, certyfikat, lokalizacja, uzytkownik_dodajacy, data_dodania
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_sscc, product_name, weight_to_take,
                pal.get('data_produkcji'), pal.get('termin_przydatnosci') or pal.get('data_przydatnosci'),
                pal.get('nr_partii'), pal.get('certyfikat'),
                child_lokalizacja, user_login, now_dt,
            ),
        )
        new_pallet_id = cursor.lastrowid

        mother_comment = (
            f"Podział palety {mother_sscc}: odjęto {weight_to_take} kg "
            f"(pozostało {new_weight} kg). Nowa paleta: {new_sscc}"
        )
        child_comment = (
            f"Utworzono z podziału palety {mother_sscc} "
            f"(pobrano {weight_to_take} kg z {current_weight} kg)"
        )

        PalletSplitService._log_historia(
            cursor, mother_id, linia, typ_palety, 'PODZIAL_ODJECIE',
            user_login, mother_comment, mother_lokalizacja, mother_lokalizacja,
        )
        PalletSplitService._log_historia(
            cursor, new_pallet_id, linia, typ_palety, 'PODZIAL_UTWORZENIE',
            user_login, child_comment, child_lokalizacja, child_lokalizacja,
        )
        PalletSplitService._log_magazyn_ruch(
            cursor, linia, mother_id, 'PODZIAL', -weight_to_take, new_weight,
            mother_lokalizacja, user_login, now_dt, mother_comment, product_name,
        )
        PalletSplitService._log_magazyn_ruch(
            cursor, linia, new_pallet_id, 'PODZIAL', weight_to_take, weight_to_take,
            child_lokalizacja, user_login, now_dt, child_comment, product_name,
        )

        return {
            'id': new_pallet_id,
            'nr_palety': new_sscc,
            'waga': weight_to_take,
            'linia': linia,
            'plan_id': None,
            'source': source,
            'produkt': product_name,
            'nazwa': product_name,
            'nr_partii': pal.get('nr_partii'),
            'data_produkcji': pal.get('data_produkcji'),
            'termin_przydatnosci': pal.get('termin_przydatnosci'),
            'mother_id': mother_id,
            'mother_nr_palety': mother_sscc,
            'mother_new_weight': new_weight,
        }

    @staticmethod
    def _split_finished(
        cursor,
        pal: dict[str, Any],
        source: str,
        linia: str,
        mother_id: int,
        new_sscc: str,
        new_weight: float,
        weight_to_take: float,
        user_login: str,
        now_dt: datetime,
        mother_sscc: str,
    ) -> dict[str, Any]:
        typ_palety = HISTORIA_TYP[source]
        mother_lokalizacja = pal.get('lokalizacja') or ''
        child_lokalizacja = mother_lokalizacja if mother_lokalizacja else 'BF_MS01'
        plan_id = pal.get('plan_id')
        produkt = pal.get('produkt')
        data_planu = pal.get('data_planu')
        nr_plomby = pal.get('nr_plomby')

        if source == 'magazyn':
            table_mother = get_table_name('magazyn_palety', linia)
            cursor.execute(
                f"UPDATE {table_mother} SET waga_netto = %s WHERE id = %s",
                (new_weight, mother_id),
            )
            prod_mother_id = pal.get('paleta_workowanie_id')
        else:
            table_mother = get_table_name('palety_workowanie', linia)
            cursor.execute(
                f"UPDATE {table_mother} SET waga = %s WHERE id = %s",
                (new_weight, mother_id),
            )
            prod_mother_id = mother_id

        new_prod_id = None
        new_pallet_id = None
        mag_pallet_id = None

        # Wstaw do palety_workowanie tylko wtedy, gdy znamy plan_id (tabela wymaga plan_id NOT NULL)
        if plan_id is not None:
            table_prod = get_table_name('palety_workowanie', linia)
            prod_cols = "plan_id, waga, data_dodania, nr_palety, nr_plomby, status, data_potwierdzenia, dodal_login, potwierdzil_login"
            prod_vals = "(%s, %s, %s, %s, %s, 'przyjeta', %s, %s, %s)"
            prod_params = (plan_id, weight_to_take, now_dt, new_sscc, nr_plomby, now_dt, user_login, user_login)

            cursor.execute(f"INSERT INTO {table_prod} ({prod_cols}) VALUES {prod_vals}", prod_params)
            new_prod_id = cursor.lastrowid
            new_pallet_id = new_prod_id

        # Update magazyn_palety jeśli źródło to magazyn
        if source == 'magazyn':
            table_mag = get_table_name('magazyn_palety', linia)
            if plan_id is not None:
                mag_cols = "paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, nr_palety, nr_plomby, lokalizacja, user_login, data_potwierdzenia, created_at, linia"
                mag_vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                mag_params = (new_prod_id, plan_id, data_planu, produkt, weight_to_take, new_sscc, nr_plomby, child_lokalizacja, user_login, now_dt, now_dt, linia)
            else:
                mag_cols = "paleta_workowanie_id, data_planu, produkt, waga_netto, nr_palety, nr_plomby, lokalizacja, user_login, data_potwierdzenia, created_at, linia"
                mag_vals = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                mag_params = (new_prod_id, data_planu, produkt, weight_to_take, new_sscc, nr_plomby, child_lokalizacja, user_login, now_dt, now_dt, linia)

            cursor.execute(f"INSERT INTO {table_mag} ({mag_cols}) VALUES {mag_vals}", mag_params)
            mag_pallet_id = cursor.lastrowid
            new_pallet_id = mag_pallet_id

        mother_hist_id = mother_id if source == 'magazyn' else prod_mother_id
        mother_comment = (
            f"Podział palety {mother_sscc}: odjęto {weight_to_take} kg "
            f"(pozostało {new_weight} kg). Nowa paleta: {new_sscc}"
        )
        child_comment = (
            f"Utworzono z podziału palety {mother_sscc} "
            f"(pobrano {weight_to_take} kg). Plan #{plan_id or 'brak'}"
        )

        PalletSplitService._log_historia(
            cursor, mother_hist_id, linia, typ_palety, 'PODZIAL_ODJECIE',
            user_login, mother_comment, mother_lokalizacja or None, mother_lokalizacja or None,
        )
        PalletSplitService._log_historia(
            cursor, new_pallet_id, linia, typ_palety, 'PODZIAL_UTWORZENIE',
            user_login, child_comment, child_lokalizacja, child_lokalizacja,
        )

        return {
            'id': new_pallet_id,
            'prod_id': new_prod_id,
            'mag_id': mag_pallet_id,
            'nr_palety': new_sscc,
            'waga': weight_to_take,
            'linia': linia,
            'plan_id': plan_id,
            'source': source,
            'produkt': produkt,
            'mother_id': mother_id,
            'mother_nr_palety': mother_sscc,
            'mother_new_weight': new_weight,
        }
