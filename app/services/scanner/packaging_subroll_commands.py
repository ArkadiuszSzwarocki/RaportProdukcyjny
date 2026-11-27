"""CQRS command service for detaching sub-rolls to LP01 and returning leftovers."""
from __future__ import annotations

from datetime import datetime
import random
import time

from app import db as app_db
from app.core.database import get_table_name
from app.dto.packaging_subroll_dto import (
    SubrollDispatchCommand,
    SubrollInsertSpec,
    SubrollReturnCommand,
)
from app.repositories.packaging_subroll_repository import PackagingSubrollRepository
from app.services.folio.folio_queries import normalize_film_name
from app.services.folio_assignment_service import FolioAssignmentService
from app.utils.pallet_id import generate_pallet_id


def generate_subroll_code(seq_idx: int = 1) -> str:
    """Generate a unique 21-character ROL000... barcode for a sub-roll."""
    base_ts = int(time.time() * 1000)
    suffix = f"{(base_ts + seq_idx) % 10000000000000:013d}{random.randint(10, 99)}"
    return f"ROL000{suffix}"


class PackagingSubrollCommands:
    """Transactional commands for Nested HU packaging sub-rolls."""

    @staticmethod
    def _detach_without_plan(
        cur,
        parent: dict,
        subroll: dict,
        user_login: str,
    ) -> tuple[int, str]:
        """Move a single sub-roll from its master pallet onto LP01 without order link."""
        amount = int(subroll['ilosc_szt'])
        old_qty = float(parent.get('stan_magazynowy') or 0)
        remaining = max(old_qty - amount, 0.0)
        parent_id = int(parent['id'])
        parent_sscc = str(parent.get('nr_palety') or f"OPK-{parent_id}")
        parent_loc = str(parent.get('lokalizacja') or 'Magazyn')

        if remaining <= 0:
            cur.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy=0, lokalizacja='ZUŻYTE', "
                "updated_at=NOW() WHERE id=%s",
                (parent_id,),
            )
        else:
            cur.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy=%s, updated_at=NOW() WHERE id=%s",
                (remaining, parent_id),
            )

        lp01_sscc = generate_pallet_id('AGRO', 'opakowanie')
        cur.execute(
            """
            INSERT INTO magazyn_opakowania
                (nazwa, stan_magazynowy, lokalizacja, nr_palety, nr_partii,
                 data_produkcji, data_przydatnosci, typ_opakowania, linia)
            VALUES (%s, %s, 'LP01', %s, %s, %s, %s, %s, 'AGRO')
            """,
            (
                parent['nazwa'],
                amount,
                lp01_sscc,
                parent.get('nr_partii'),
                parent.get('data_produkcji'),
                parent.get('data_przydatnosci'),
                parent.get('typ_opakowania') or 'Taśma',
            ),
        )
        lp01_id = int(cur.lastrowid)
        PackagingSubrollRepository.mark_dispatched_to_lp01(cur, int(subroll['id']), lp01_id)

        now_dt = datetime.now()
        table_ruch = get_table_name('magazyn_ruch', 'AGRO')
        comment = (
            f"Wydano podrolkę #{subroll['nr_rolki']} ({subroll['kod_rolki']}, {amount} szt) "
            f"z palety {parent_sscc} na LP01"
        )
        cur.execute(
            f"""
            INSERT INTO {table_ruch}
            (surowiec_id, surowiec_nazwa, lokalizacja, typ_ruchu, ilosc, ilosc_po,
             status, autor_login, autor_data, komentarz)
            VALUES (%s, %s, 'LP01', 'WYDANIE_NA_MASZYNE', %s, %s,
                    'POTWIERDZONE', %s, %s, %s)
            """,
            (lp01_id, parent['nazwa'], amount, amount, user_login, now_dt, comment),
        )
        cur.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'PODZIAL_ODJECIE',
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                parent_id,
                parent_sscc,
                parent_loc,
                'ZUŻYTE' if remaining <= 0 else parent_loc,
                comment,
                user_login,
                now_dt,
                old_qty,
                remaining,
            ),
        )
        cur.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'WYDANIE_NA_MASZYNE',
                    %s, 'LP01', %s, %s, %s, 0, %s)
            """,
            (lp01_id, lp01_sscc, parent_loc, comment, user_login, now_dt, float(amount)),
        )
        return lp01_id, lp01_sscc

    @staticmethod
    def _validate_dispatch_target(
        cur,
        subroll_id: int,
    ) -> tuple[dict | None, dict | None, str | None]:
        """Lock and validate sub-roll and its master pallet prior to LP01 dispatch."""
        sub = PackagingSubrollRepository.find_by_id(cur, subroll_id, for_update=True)
        if not sub or str(sub.get('status') or '').upper() != 'NA_PALECIE':
            return None, None, 'Wybrana podrolka nie znajduje się już na palecie.'

        parent_id = int(sub['parent_opakowanie_id'])
        cur.execute("SELECT * FROM magazyn_opakowania WHERE id = %s FOR UPDATE", (parent_id,))
        parent = cur.fetchone()
        if not parent or parent.get('is_blocked'):
            return None, None, 'Paleta główna jest niedostępna lub zablokowana.'

        if float(parent.get('stan_magazynowy') or 0) < int(sub['ilosc_szt']):
            return None, None, 'Stan palety głównej jest mniejszy niż ilość na podrolce.'
        return sub, parent, None

    @staticmethod
    def _mark_plan_subroll_dispatched(subroll_id: int, plan_id: int) -> int | None:
        """Link newly created LP01 roll record back to the dispatched sub-roll."""
        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT opakowanie_id
                FROM agro_plan_opakowania
                WHERE plan_id = %s AND is_active = TRUE
                ORDER BY id DESC LIMIT 1
                """,
                (plan_id,),
            )
            latest_link = cur.fetchone()
            lp01_id = int(latest_link['opakowanie_id']) if latest_link else None
            PackagingSubrollRepository.mark_dispatched_to_lp01(cur, subroll_id, lp01_id)
            conn.commit()
            return lp01_id
        finally:
            conn.close()

    @staticmethod
    def dispatch_subroll_to_lp01(cmd: SubrollDispatchCommand) -> tuple[bool, str, dict | None]:
        """Detach a specific sub-roll from its master pallet and issue it to LP01."""
        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            PackagingSubrollRepository.ensure_table(cur)
            sub, parent, err_msg = PackagingSubrollCommands._validate_dispatch_target(
                cur,
                cmd.subroll_id,
            )
            if err_msg or not sub or not parent:
                conn.rollback()
                return False, err_msg or 'Nieprawidłowa podrolka.', None

            parent_id = int(parent['id'])
            amount = int(sub['ilosc_szt'])
            if not cmd.plan_id:
                lp01_id, lp01_sscc = PackagingSubrollCommands._detach_without_plan(
                    cur,
                    parent,
                    sub,
                    cmd.user_login,
                )
                conn.commit()
                msg = (
                    f"✅ Wydano podrolkę #{sub['nr_rolki']} ({amount} szt) "
                    f"na stanowisko LP01 ({lp01_sscc})."
                )
                return True, msg, {'lp01_id': lp01_id, 'lp01_sscc': lp01_sscc}
        except Exception as err:  # pylint: disable=broad-exception-caught
            conn.rollback()
            return False, f'Błąd wydania podrolki: {err}', None
        finally:
            conn.close()

        ok, message = FolioAssignmentService.assign(
            parent_id,
            cmd.plan_id,
            amount,
            cmd.user_login,
            role=cmd.roll_role,
            request_key=cmd.request_key,
            previous_remaining=cmd.previous_remaining,
        )
        if not ok:
            return False, message, None

        lp01_id = PackagingSubrollCommands._mark_plan_subroll_dispatched(
            cmd.subroll_id,
            cmd.plan_id,
        )
        return True, message, {'lp01_id': lp01_id}

    @staticmethod
    def _find_locked_mother_pallet(cur, identifier: str | int) -> dict | None:
        """Lock and fetch a warehouse master pallet by ID or SSCC."""
        raw = str(identifier or '').strip()
        if raw.isdigit():
            cur.execute("SELECT * FROM magazyn_opakowania WHERE id = %s FOR UPDATE", (int(raw),))
        else:
            cur.execute(
                "SELECT * FROM magazyn_opakowania WHERE UPPER(nr_palety) = UPPER(%s) FOR UPDATE",
                (raw,),
            )
        return cur.fetchone()

    @staticmethod
    def _validate_lp01_return_pair(
        cur,
        cmd: SubrollReturnCommand,
    ) -> tuple[dict | None, dict | None, int, str | None]:
        """Validate unassigned LP01 roll, target warehouse mother pallet, and film match."""
        cur.execute(
            "SELECT id FROM agro_plan_opakowania "
            "WHERE opakowanie_id=%s AND is_active=TRUE LIMIT 1",
            (cmd.lp01_item_id,),
        )
        if cur.fetchone():
            return None, None, 0, 'Najpierw rozlicz lub zwolnij rolkę w sekcji Folia zlecenia.'

        cur.execute(
            "SELECT * FROM magazyn_opakowania WHERE id=%s FOR UPDATE",
            (cmd.lp01_item_id,),
        )
        lp_roll = cur.fetchone()
        lp_loc = str((lp_roll or {}).get('lokalizacja') or '').strip().upper()
        if not lp_roll or lp_loc not in ('LP01', 'MASZYNA'):
            return None, None, 0, 'Nie znaleziono rolki na stanowisku LP01.'

        avail_qty = int(round(float(lp_roll.get('stan_magazynowy') or 0)))
        return_qty = int(round(float(cmd.amount))) if cmd.amount is not None else avail_qty
        if return_qty <= 0 or return_qty > avail_qty:
            return None, None, 0, f'Nieprawidłowa ilość do zwrotu (dostępne: {avail_qty} szt).'

        mother = PackagingSubrollCommands._find_locked_mother_pallet(cur, cmd.mother_identifier)
        mother_loc = str((mother or {}).get('lokalizacja') or '').strip().upper()
        invalid_locs = ('LP01', 'MASZYNA', 'ZUZYTE', 'ZUŻYTE', 'ARCHIWUM')
        if not mother or int(mother['id']) == int(lp_roll['id']) or mother_loc in invalid_locs:
            return None, None, 0, 'Wskazana paleta-matka w magazynie jest niedostępna.'

        if normalize_film_name(mother.get('nazwa')) != normalize_film_name(lp_roll.get('nazwa')):
            err = (
                f"Niezgodność folii: rolka '{lp_roll.get('nazwa')}' nie pasuje "
                f"do palety '{mother.get('nazwa')}'."
            )
            return None, None, 0, err
        return lp_roll, mother, return_qty, None

    @staticmethod
    def _apply_lp01_return_updates(
        cur,
        lp_roll: dict,
        mother: dict,
        return_qty: int,
    ) -> dict:
        """Update stock on both mother warehouse pallet and source LP01 roll."""
        avail_qty = int(round(float(lp_roll.get('stan_magazynowy') or 0)))
        mother_before = float(mother.get('stan_magazynowy') or 0)
        mother_after = mother_before + return_qty
        cur.execute(
            "UPDATE magazyn_opakowania SET stan_magazynowy=%s, updated_at=NOW() WHERE id=%s",
            (mother_after, mother['id']),
        )
        lp_after = avail_qty - return_qty
        if lp_after <= 0:
            cur.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy=0, lokalizacja='ZUŻYTE', "
                "updated_at=NOW() WHERE id=%s",
                (lp_roll['id'],),
            )
        else:
            cur.execute(
                "UPDATE magazyn_opakowania SET stan_magazynowy=%s, "
                "updated_at=NOW() WHERE id=%s",
                (lp_after, lp_roll['id']),
            )
        return {
            'mother_before': mother_before,
            'mother_after': mother_after,
            'lp_after': lp_after,
        }

    @staticmethod
    def return_lp01_roll_to_mother(cmd: SubrollReturnCommand) -> tuple[bool, str, dict | None]:
        """Attach an unassigned LP01 roll back onto a master pallet as a sub-roll."""
        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            PackagingSubrollRepository.ensure_table(cur)
            lp_roll, mother, return_qty, err_msg = (
                PackagingSubrollCommands._validate_lp01_return_pair(cur, cmd)
            )
            if err_msg or not lp_roll or not mother:
                conn.rollback()
                return False, err_msg or 'Błąd walidacji zwrotu.', None

            balances = PackagingSubrollCommands._apply_lp01_return_updates(
                cur,
                lp_roll,
                mother,
                return_qty,
            )

            next_nr = PackagingSubrollRepository.next_roll_number(cur, int(mother['id']))
            roll_code = generate_subroll_code(next_nr)
            sub_id = PackagingSubrollRepository.insert_subroll(
                cur,
                SubrollInsertSpec(
                    parent_id=int(mother['id']),
                    kod_rolki=roll_code,
                    nr_rolki=next_nr,
                    ilosc_szt=return_qty,
                    zrodlo='ZWROT_LP01',
                    created_by=cmd.user_login,
                ),
            )

            PackagingSubrollCommands._log_return_history(
                cur,
                lp_roll=lp_roll,
                mother=mother,
                return_qty=return_qty,
                roll_code=roll_code,
                user_login=cmd.user_login,
                **balances,
            )
            conn.commit()
            m_sscc = mother.get('nr_palety') or f"OPK-{mother['id']}"
            msg = (
                f"✅ Zwrócono końcówkę ({return_qty} szt) z LP01 jako Podrolkę #{next_nr} "
                f"({roll_code}) na paletę {m_sscc} ({mother.get('lokalizacja')})."
            )
            return True, msg, {'subroll_id': sub_id, 'kod_rolki': roll_code, 'mother_sscc': m_sscc}
        except Exception as err:  # pylint: disable=broad-exception-caught
            conn.rollback()
            return False, f'Błąd zwrotu na paletę-matkę: {err}', None
        finally:
            conn.close()

    @staticmethod
    def _log_return_history(cur, **ctx) -> None:
        """Write movement and palety_historia entries for LP01-to-mother-pallet return."""
        now_dt = datetime.now()
        lp_roll = ctx['lp_roll']
        mother = ctx['mother']
        qty = ctx['return_qty']
        m_sscc = mother.get('nr_palety') or f"OPK-{mother['id']}"
        m_loc = mother.get('lokalizacja') or 'Magazyn'
        comment = (
            f"Zwrot końcówki {qty} szt z LP01 ({lp_roll.get('nr_palety')}) "
            f"na paletę-matkę {m_sscc} jako podrolka {ctx['roll_code']}"
        )

        table_ruch = get_table_name('magazyn_ruch', 'AGRO')
        cur.execute(
            f"""
            INSERT INTO {table_ruch}
            (surowiec_id, surowiec_nazwa, lokalizacja, typ_ruchu, ilosc, ilosc_po,
             status, autor_login, autor_data, komentarz)
            VALUES (%s, %s, %s, 'ZWROT_NA_PALETE', %s, %s, 'POTWIERDZONE', %s, %s, %s)
            """,
            (
                mother['id'],
                mother.get('nazwa'),
                m_loc,
                float(qty),
                float(ctx['mother_after']),
                ctx['user_login'],
                now_dt,
                comment,
            ),
        )
        cur.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'DOPISANIE_PODROLKI_ZWROT',
                    'LP01', %s, %s, %s, %s, %s, %s)
            """,
            (
                mother['id'],
                m_sscc,
                m_loc,
                comment,
                ctx['user_login'],
                now_dt,
                float(ctx['mother_before']),
                float(ctx['mother_after']),
            ),
        )
        cur.execute(
            """
            INSERT INTO palety_historia
            (paleta_id, nr_palety, linia, typ_palety, entity_type, akcja,
             lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu,
             quantity_before, quantity_after)
            VALUES (%s, %s, 'AGRO', 'opakowanie', 'opakowanie', 'ZWROT_NA_PALETE_MATKE',
                    'LP01', %s, %s, %s, %s, %s, %s)
            """,
            (
                lp_roll['id'],
                lp_roll.get('nr_palety'),
                m_loc,
                comment,
                ctx['user_login'],
                now_dt,
                float(ctx['lp_after'] + qty),
                float(ctx['lp_after']),
            ),
        )
