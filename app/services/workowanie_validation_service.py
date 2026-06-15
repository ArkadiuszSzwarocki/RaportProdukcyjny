import logging
from flask import current_app
from app.db import get_db_connection, get_table_name

logger = logging.getLogger(__name__)

class WorkowanieValidationService:
    """Serwis weryfikujący możliwość startu zlecenia na sekcji Workowanie."""

    BYPASS_ROLES = {'admin', 'masteradmin', 'master admin', 'master_admin', 'lider', 'planista', 'zarzad'}

    @classmethod
    def validate_start(cls, plan_id: int, linia: str, sekcja: str, produkt: str, data_planu: str, role_lc: str) -> tuple[bool, str]:
        """
        Weryfikuje, czy zlecenie może zostać wystartowane. Zwraca (True, "") jeśli tak, 
        lub (False, "komunikat błędu") jeśli zablokowano.
        """
        # Sprawdzamy tylko sekcję Workowanie i Czyszczenie
        if sekcja not in ('Workowanie', 'Czyszczenie'):
            return True, ""

        # Jeżeli rola jest uprzywilejowana, omijamy walidację bufora i FIFO
        if role_lc in cls.BYPASS_ROLES:
            logger.debug(f'[KOLEJKA] bypass for role={role_lc} plan_id={plan_id} produkt={produkt}')
            return True, ""

        conn = None
        try:
            table_bufor = get_table_name('bufor', linia)
            table_plan = get_table_name('plan_produkcji', linia)
            
            conn = get_db_connection()
            cursor = conn.cursor()

            logger.debug(f'[KOLEJKA] start_zlecenie check id={plan_id} produkt="{produkt}" data_planu={data_planu}')

            # 1. Sprawdź czy produkt w ogóle jest w buforze
            cursor.execute(
                f"""
                SELECT kolejka FROM {table_bufor}
                WHERE produkt = %s AND DATE(data_planu) = %s AND status = 'aktywny'
                """,
                (produkt, data_planu),
            )
            my_q_row = cursor.fetchone()
            my_q = my_q_row[0] if my_q_row else None

            if my_q is None:
                return False, f"❌ Start zablokowany: Produkt '{produkt}' nie znajduje się obecnie w buforze (Zasyp musi najpierw wyprodukować wsad)."

            # 2. Produkt jest w buforze, sprawdzamy zasady FIFO (czy jest najwcześniejszy)
            cursor.execute(
                f"""
                SELECT MIN(b.kolejka)
                FROM {table_bufor} b
                WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
                  AND EXISTS (
                      SELECT 1 FROM {table_plan} w
                      WHERE w.sekcja IN ('Workowanie', 'Czyszczenie') AND w.status IN ('zaplanowane', 'w toku')
                        AND w.produkt = b.produkt AND w.data_planu = b.data_planu
                  )
                """,
                (data_planu,),
            )
            min_q_row = cursor.fetchone()
            global_min_queue = min_q_row[0] if min_q_row else None

            if global_min_queue is not None and my_q > global_min_queue:
                # Ktoś inny w kolejce jest wcześniej
                cursor.execute(
                    f"SELECT produkt FROM {table_bufor} WHERE kolejka = %s AND status = 'aktywny' AND DATE(data_planu) = %s LIMIT 1",
                    (global_min_queue, data_planu),
                )
                earliest_row = cursor.fetchone()
                earliest_produkt = earliest_row[0] if earliest_row else '?'

                return False, f"❌ Kolejkowanie Workowanie: W buforze znajduje się produkt przewidziany wcześniej do startu: {earliest_produkt}. Zalecana kolejność FIFO."

            # Wszystko ok, produkt w buforze i ma pierwszeństwo (lub jest sam)
            return True, ""
            
        except Exception as e:
            logger.exception('[KOLEJKA] FIFO check failed: %s', e)
            # W razie błędów zapytania awaryjnie przepuszczamy lub zwracamy błąd. 
            # Zachowuję logikę w "orders.py", która przechwytywała błąd logując go i kontynuowała start.
            return True, ""
        finally:
            if conn:
                cursor.close()
                conn.close()
