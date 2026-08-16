from app.db import get_db_connection, get_table_name
from datetime import datetime


class MomService:
    """MOM — rozliczenie materiałowe per zlecenie AGRO.

    Przepływ:
    1. open_mom(plan_id)  — tworzy rozliczenie, wciąga przesunięcia z magazyn_agro_ruch
    2. refresh(mom_id)    — przelicza przesunięcia z ruchów magazynowych
    3. save_usage(mom_id, items)  — wpisuje ręczne zużycie na koniec zlecenia
    4. close_mom(mom_id, login)   — zamyka rozliczenie
    """

    LINIA = 'Agro'

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _get_plan(cursor, plan_id):
        table = get_table_name('plan_produkcji', MomService.LINIA)
        cursor.execute(
            f"SELECT id, data_planu, produkt, tonaz, tonaz_rzeczywisty, nazwa_zlecenia "
            f"FROM {table} WHERE id = %s", (plan_id,)
        )
        return cursor.fetchone()

    @staticmethod
    def _aggregate_moves(cursor, plan_id):
        """Return dict {surowiec_nazwa: total_kg} from warehouse moves for plan."""
        table_ruch = get_table_name('magazyn_ruch', MomService.LINIA)
        table_sur = get_table_name('magazyn_surowce', MomService.LINIA)
        cursor.execute(
            f"SELECT COALESCE(s.nazwa, r.surowiec_nazwa) AS nazwa, "
            f"       SUM(ABS(r.ilosc)) AS total "
            f"FROM {table_ruch} r "
            f"LEFT JOIN {table_sur} s ON r.surowiec_id = s.id "
            f"WHERE r.plan_id = %s AND r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
            f"GROUP BY nazwa",
            (plan_id,)
        )
        return {row[0]: row[1] for row in cursor.fetchall() if row[0]}

    # ── CRUD ─────────────────────────────────────────────────────

    @staticmethod
    def open_mom(plan_id):
        """Create MOM for a plan_agro order. Returns mom_id or None."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            plan = MomService._get_plan(cursor, plan_id)
            if not plan:
                return None

            pid, data_planu, produkt, tonaz, tonaz_rz, nazwa_zl = plan

            # Check if MOM already exists for this plan
            cursor.execute(
                "SELECT id FROM mom_rozliczenia WHERE plan_id = %s", (plan_id,)
            )
            existing = cursor.fetchone()
            if existing:
                return existing[0]

            cursor.execute(
                "INSERT INTO mom_rozliczenia "
                "(plan_id, nazwa_zlecenia, data_planu, produkt, tonaz_planowany, tonaz_rzeczywisty) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (plan_id, nazwa_zl or '', data_planu, produkt, tonaz or 0, tonaz_rz or 0)
            )
            mom_id = cursor.lastrowid

            # Insert positions from existing warehouse moves
            moves = MomService._aggregate_moves(cursor, plan_id)
            for nazwa, kg in moves.items():
                cursor.execute(
                    "INSERT INTO mom_pozycje (mom_id, surowiec_nazwa, przesunieto_kg) "
                    "VALUES (%s, %s, %s)",
                    (mom_id, nazwa, kg)
                )

            conn.commit()
            return mom_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def refresh(mom_id):
        """Refresh moved-qty from warehouse moves; add new materials if appeared."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plan_id FROM mom_rozliczenia WHERE id = %s", (mom_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            plan_id = row[0]

            # Also refresh tonaz_rzeczywisty from plan
            plan = MomService._get_plan(cursor, plan_id)
            if plan:
                cursor.execute(
                    "UPDATE mom_rozliczenia SET tonaz_rzeczywisty = %s WHERE id = %s",
                    (plan[4] or 0, mom_id)
                )

            moves = MomService._aggregate_moves(cursor, plan_id)

            # Get existing positions
            cursor.execute(
                "SELECT id, surowiec_nazwa FROM mom_pozycje WHERE mom_id = %s", (mom_id,)
            )
            existing = {r[1]: r[0] for r in cursor.fetchall()}

            for nazwa, kg in moves.items():
                if nazwa in existing:
                    cursor.execute(
                        "UPDATE mom_pozycje SET przesunieto_kg = %s WHERE id = %s",
                        (kg, existing[nazwa])
                    )
                else:
                    cursor.execute(
                        "INSERT INTO mom_pozycje (mom_id, surowiec_nazwa, przesunieto_kg) "
                        "VALUES (%s, %s, %s)",
                        (mom_id, nazwa, kg)
                    )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def save_usage(mom_id, items):
        """Save manually-entered usage for existing MOM positions only.

        items: list of {'surowiec_nazwa': str, 'zuzycie_kg': float, 'komentarz': str}
        Only updates positions that already exist (from warehouse moves).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Get existing positions
            cursor.execute(
                "SELECT id, surowiec_nazwa FROM mom_pozycje WHERE mom_id = %s", (mom_id,)
            )
            existing = {r[1]: r[0] for r in cursor.fetchall()}

            for item in items:
                nazwa = item.get('surowiec_nazwa', '').strip()
                zuzycie = float(item.get('zuzycie_kg', 0))
                komentarz = item.get('komentarz', '')
                if not nazwa or nazwa not in existing:
                    continue

                cursor.execute(
                    "UPDATE mom_pozycje SET zuzycie_kg = %s, "
                    "roznica_kg = %s - przesunieto_kg, "
                    "komentarz = %s WHERE id = %s",
                    (zuzycie, zuzycie, komentarz, existing[nazwa])
                )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def close_mom(mom_id, login):
        """Close MOM — recalculates differences and locks it."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # Final refresh of moves
            MomService.refresh(mom_id)

            # Recalculate all differences
            cursor.execute(
                "UPDATE mom_pozycje SET roznica_kg = zuzycie_kg - przesunieto_kg "
                "WHERE mom_id = %s",
                (mom_id,)
            )

            cursor.execute(
                "UPDATE mom_rozliczenia SET status = 'zamkniety', "
                "zamknal_login = %s, data_zamkniecia = %s WHERE id = %s",
                (login, datetime.now(), mom_id)
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def reopen_mom(mom_id):
        """Reopen a closed MOM (admin only)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mom_rozliczenia SET status = 'otwarty', "
                "zamknal_login = NULL, data_zamkniecia = NULL WHERE id = %s",
                (mom_id,)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # ── Queries ──────────────────────────────────────────────────

    @staticmethod
    def get_mom(mom_id):
        """Return MOM header + positions."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM mom_rozliczenia WHERE id = %s", (mom_id,))
            mom = cursor.fetchone()
            if not mom:
                return None

            cursor.execute(
                "SELECT * FROM mom_pozycje WHERE mom_id = %s ORDER BY surowiec_nazwa",
                (mom_id,)
            )
            mom['pozycje'] = cursor.fetchall()
            return mom
        finally:
            conn.close()

    @staticmethod
    def get_mom_by_plan(plan_id):
        """Return MOM for a given plan_id or None."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM mom_rozliczenia WHERE plan_id = %s", (plan_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return MomService.get_mom(row['id'])
        finally:
            conn.close()

    @staticmethod
    def list_moms(limit=50, status=None, data_od=None, data_do=None):
        """List MOM headers with optional filters."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            q = "SELECT * FROM mom_rozliczenia WHERE 1=1 "
            params = []
            if status:
                q += " AND status = %s "
                params.append(status)
            if data_od:
                q += " AND data_planu >= %s "
                params.append(data_od)
            if data_do:
                q += " AND data_planu <= %s "
                params.append(data_do)
            q += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def delete_mom(mom_id):
        """Delete MOM and its positions (cascade)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mom_rozliczenia WHERE id = %s", (mom_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def get_open_plans():
        """Return AGRO plans that do NOT yet have a MOM."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table = get_table_name('plan_produkcji', MomService.LINIA)
            cursor.execute(
                f"SELECT p.id, p.data_planu, p.produkt, p.tonaz, p.tonaz_rzeczywisty, "
                f"p.nazwa_zlecenia, p.status "
                f"FROM {table} p "
                f"LEFT JOIN mom_rozliczenia m ON m.plan_id = p.id "
                f"WHERE m.id IS NULL "
                f"ORDER BY p.data_planu DESC, p.id DESC LIMIT 100"
            )
            return cursor.fetchall()
        finally:
            conn.close()
