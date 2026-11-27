"""Unified movement and pallet history writer for AGRO film roll operations."""
from __future__ import annotations

import json
from datetime import datetime

from app.core.database import get_table_name
from app.dto.folio_events import FoilClosureEvent, FoilWithdrawalEvent


class FolioLedgerWriter:
    """Persist consistent AGRO movement and pallet history records for film rolls."""

    @staticmethod
    def has_request_key(cursor, request_key: str) -> bool:
        """Check idempotency key across movement tables."""
        pattern = f'%{request_key}%'
        for table_name in ('magazyn_ruch', 'magazyn_agro_ruch'):
            cursor.execute(
                f"SELECT id FROM {table_name} "
                "WHERE typ_ruchu = 'POBRANIE_NA_MASZYNE' AND komentarz LIKE %s LIMIT 1",
                (pattern,),
            )
            if cursor.fetchone():
                return True
        return False

    @staticmethod
    def is_individual_roll(cursor, opakowanie_id: int) -> bool:
        """Return True if packaging row was created as a per-order LP01 withdrawal roll."""
        for table_name in ('magazyn_agro_ruch', 'magazyn_ruch'):
            cursor.execute(
                f"""
                SELECT id
                FROM {table_name}
                WHERE surowiec_id = %s
                  AND typ_ruchu = 'POBRANIE_NA_MASZYNE'
                  AND komentarz LIKE %s
                LIMIT 1
                """,
                (opakowanie_id, '%source_sscc%'),
            )
            if cursor.fetchone():
                return True
        return False

    @staticmethod
    def find_roll_source_metadata(cursor, opakowanie_id: int) -> dict:
        """Fetch latest JSON withdrawal metadata for a roll from AGRO or legacy ledger."""
        for table_name in ('magazyn_agro_ruch', 'magazyn_ruch'):
            cursor.execute(
                f"""
                SELECT komentarz
                FROM {table_name}
                WHERE surowiec_id = %s AND typ_ruchu = 'POBRANIE_NA_MASZYNE'
                ORDER BY id DESC
                LIMIT 1
                """,
                (opakowanie_id,),
            )
            row = cursor.fetchone()
            raw_comment = (
                row.get('komentarz')
                if isinstance(row, dict)
                else (row[0] if row else None)
            )
            if raw_comment:
                try:
                    parsed = json.loads(raw_comment)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, TypeError):
                    continue
        return {}

    @staticmethod
    def record_foil_withdrawal(cursor, event: FoilWithdrawalEvent) -> None:
        """Write withdrawal ledger entries to magazyn_ruch and palety_historia."""
        now_dt = datetime.now()
        src = event.source
        roll = event.roll
        meta_json = json.dumps(
            {
                'source_id': src.source_id,
                'source_sscc': src.source_sscc,
                'plan_id': event.plan_id,
                'link_id': event.link_id,
                'request_key': event.request_key,
            },
            ensure_ascii=False,
        )

        if not event.reused_lp01_roll:
            cursor.execute(
                "INSERT INTO magazyn_ruch "
                "(surowiec_id, surowiec_nazwa, lokalizacja, typ_ruchu, ilosc, ilosc_po, "
                "status, autor_login, autor_data, plan_id, komentarz) "
                "VALUES (%s, %s, %s, 'POBRANIE_DO_PRODUKCJI', %s, %s, "
                "'POTWIERDZONE', %s, %s, %s, %s)",
                (
                    src.source_id,
                    src.source_name,
                    src.source_location or None,
                    -float(roll.amount),
                    float(src.qty_after),
                    event.user_login,
                    now_dt,
                    event.plan_id,
                    meta_json,
                ),
            )

        cursor.execute(
            "INSERT INTO magazyn_ruch "
            "(surowiec_id, surowiec_nazwa, lokalizacja, typ_ruchu, ilosc, ilosc_po, "
            "status, autor_login, autor_data, plan_id, komentarz) "
            "VALUES (%s, %s, 'LP01', 'POBRANIE_NA_MASZYNE', %s, %s, "
            "'POTWIERDZONE', %s, %s, %s, %s)",
            (
                roll.roll_id,
                src.source_name,
                float(roll.amount),
                float(roll.amount),
                event.user_login,
                now_dt,
                event.plan_id,
                meta_json,
            ),
        )

        if event.reused_lp01_roll:
            reused_comment = (
                f"Podpięcie pozostałości rolki na LP01 ({int(roll.amount)} szt.) "
                f"do zlecenia #{event.plan_id}"
            )
            cursor.execute(
                """
                INSERT INTO palety_historia
                (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
                 lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
                 quantity_before, quantity_after)
                VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'PODPIECIE_DO_ZLECENIA',
                        %s, 'LP01', %s, %s, %s, %s, %s)
                """,
                (
                    roll.roll_id,
                    roll.roll_sscc,
                    src.source_location or 'LP01',
                    reused_comment,
                    event.user_login,
                    now_dt,
                    float(roll.amount),
                    float(roll.amount),
                ),
            )
            return

        split_comment = (
            f"Pobrano {int(roll.amount)} szt. folii na LP01 do zlecenia "
            f"#{event.plan_id} (rolka {roll.roll_sscc})"
        )
        cursor.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'PODZIAL_ODJECIE',
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                src.source_id,
                src.source_sscc,
                src.source_location,
                'ZUŻYTE' if src.qty_after <= 0 else src.source_location,
                split_comment,
                event.user_login,
                now_dt,
                float(src.qty_before),
                float(src.qty_after),
            ),
        )

        dispatch_comment = (
            f"Wydano {int(roll.amount)} szt. z palety {src.source_sscc} "
            f"({src.source_location or 'Magazyn'}) na LP01 (plan #{event.plan_id})"
        )
        cursor.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'WYDANIE_NA_MASZYNE',
                    %s, 'LP01', %s, %s, %s, %s, %s)
            """,
            (
                roll.roll_id,
                roll.roll_sscc,
                src.source_location,
                dispatch_comment,
                event.user_login,
                now_dt,
                0.0,
                float(roll.amount),
            ),
        )

    @staticmethod
    def record_foil_activation(
        cursor,
        *,
        opakowanie_id: int,
        plan_id: int,
        user_login: str,
    ) -> None:
        """Record activation of a prepared LP01 roll in AGRO movement log."""
        table_ruch = get_table_name('magazyn_ruch', 'AGRO')
        cursor.execute(
            f"""
            INSERT INTO {table_ruch}
            (surowiec_id, lokalizacja, typ_ruchu, ilosc, status,
             autor_login, autor_data, plan_id, komentarz)
            VALUES (%s, 'LP01', 'ZALOZENIE_ROLKI', 0, 'POTWIERDZONE',
                    %s, NOW(), %s, %s)
            """,
            (
                opakowanie_id,
                user_login,
                plan_id,
                f"Założenie przygotowanej rolki do zlecenia #{plan_id}",
            ),
        )

    @staticmethod
    def record_foil_closure(cursor, event: FoilClosureEvent) -> None:
        """Record roll settlement in magazyn_agro_ruch, palety_historia, and magazyn_archiwum."""
        now_dt = datetime.now()
        table_ruch = get_table_name('magazyn_ruch', 'AGRO')
        has_remainder = event.pozostalo_szt > 0
        target_loc = 'LP01' if has_remainder else 'ZUŻYTE'
        if has_remainder:
            rem_int = int(round(event.pozostalo_szt))
            comment = (
                f"Zamknięcie rolki (plan #{event.plan_id}), "
                f"pozostało na LP01: {rem_int} szt."
            )
        else:
            used_int = int(round(event.fizycznie_zuzyto))
            comment = (
                f"Zamknięcie rolki (plan #{event.plan_id}), "
                f"zużyto w całości ({used_int} szt.)"
            )

        cursor.execute(
            f"""
            INSERT INTO {table_ruch}
            (surowiec_id, surowiec_nazwa, lokalizacja, typ_ruchu, ilosc, ilosc_po,
             status, autor_login, autor_data, plan_id, komentarz)
            VALUES (%s, %s, %s, 'ODPIECIE_OD_ZLECENIA', %s, %s,
                    'POTWIERDZONE', %s, %s, %s, %s)
            """,
            (
                event.opakowanie_id,
                event.opak_nazwa,
                target_loc,
                -float(event.fizycznie_zuzyto),
                float(event.pozostalo_szt),
                event.user_login,
                now_dt,
                event.plan_id,
                comment,
            ),
        )

        cursor.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', %s,
                    'LP01', %s, %s, %s, %s, %s, %s)
            """,
            (
                event.opakowanie_id,
                event.nr_palety or None,
                'ROZLICZENIE_ROLKI' if has_remainder else 'ARCHIWIZACJA_LP01',
                target_loc,
                comment,
                event.user_login,
                now_dt,
                float(event.stan_poczatkowy),
                float(event.pozostalo_szt),
            ),
        )

        if not has_remainder and event.fizycznie_zuzyto > 0:
            cursor.execute(
                """
                INSERT INTO magazyn_archiwum
                (original_id, nr_palety, nazwa, typ_palety, linia,
                 waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji, user_login, komentarz)
                VALUES (%s, %s, %s, 'Opakowanie', 'AGRO',
                        %s, 'LP01', %s, %s, %s)
                """,
                (
                    event.opakowanie_id,
                    event.nr_palety or None,
                    event.opak_nazwa,
                    float(event.fizycznie_zuzyto),
                    now_dt,
                    event.user_login,
                    comment,
                ),
            )
