import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
from app.db import get_db_connection

logger = logging.getLogger(__name__)

class ZasypyRaportService:
    @staticmethod
    def get_zasypy_report(start_date: str, end_date: str, linia: str = 'WSZYSTKO') -> List[Dict[str, Any]]:
        """
        Pobiera zagregowany raport zasypów i dosypek dla podanego zakresu dat.
        :param start_date: Data początkowa (YYYY-MM-DD)
        :param end_date: Data końcowa (YYYY-MM-DD)
        :param linia: 'PSD', 'AGRO', 'WSZYSTKO'
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            results = []

            # -------------------------------------------------------------
            # Zapytanie dla PSD
            # -------------------------------------------------------------
            if linia in ('PSD', 'WSZYSTKO'):
                q_psd = """
                SELECT 
                    'PSD' as linia,
                    z.id as zasyp_id,
                    z.nr_zasypu,
                    z.nr_szarzy,
                    z.waga as waga_zasypu,
                    z.data_dodania as data_zasypu,
                    p.id as plan_id,
                    p.data_planu,
                    p.produkt,
                    p.nazwa_zlecenia,
                    p.status as plan_status,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = z.pracownik_id) as zasyp_pracownik,
                    d.id as dosypka_id,
                    d.nazwa as dosypka_nazwa,
                    d.kg as dosypka_waga,
                    d.data_zlecenia as dosypka_data,
                    d.potwierdzone as dosypka_potwierdzone,
                    d.data_potwierdzenia as dosypka_data_potwierdzenia,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = d.pracownik_id) as dosypka_zlecil,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = d.potwierdzil_pracownik_id) as dosypka_potwierdzil
                FROM zasypy z
                JOIN plan_produkcji p ON z.plan_id = p.id
                LEFT JOIN dosypki d ON d.szarza_id = z.id
                WHERE DATE(z.data_dodania) BETWEEN %s AND %s
                  AND p.is_deleted = 0
                ORDER BY z.data_dodania DESC
                """
                cursor.execute(q_psd, (start_date, end_date))
                psd_rows = cursor.fetchall()
                results.extend(psd_rows)

            # -------------------------------------------------------------
            # Zapytanie dla AGRO
            # -------------------------------------------------------------
            if linia in ('AGRO', 'WSZYSTKO'):
                q_agro = """
                SELECT 
                    'AGRO' as linia,
                    z.id as zasyp_id,
                    z.nr_zasypu,
                    z.nr_szarzy,
                    z.waga as waga_zasypu,
                    z.data_dodania as data_zasypu,
                    p.id as plan_id,
                    p.data_planu,
                    p.produkt,
                    p.nazwa_zlecenia,
                    p.status as plan_status,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = z.pracownik_id) as zasyp_pracownik,
                    d.id as dosypka_id,
                    d.nazwa as dosypka_nazwa,
                    d.kg as dosypka_waga,
                    d.data_zlecenia as dosypka_data,
                    d.potwierdzone as dosypka_potwierdzone,
                    d.data_potwierdzenia as dosypka_data_potwierdzenia,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = d.pracownik_id) as dosypka_zlecil,
                    (SELECT u.login FROM uzytkownicy u WHERE u.id = d.potwierdzil_pracownik_id) as dosypka_potwierdzil
                FROM zasypy_agro z
                JOIN plan_produkcji_agro p ON z.plan_id = p.id
                LEFT JOIN dosypki_agro d ON d.szarza_id = z.id
                WHERE DATE(z.data_dodania) BETWEEN %s AND %s
                  AND p.is_deleted = 0
                ORDER BY z.data_dodania DESC
                """
                cursor.execute(q_agro, (start_date, end_date))
                agro_rows = cursor.fetchall()
                results.extend(agro_rows)

            # Agregacja wtyczek w Pythonie ze względu na to że jedna szarża/zasyp może mieć wiele dosypek
            grouped_results = {}
            for row in results:
                key = f"{row['linia']}_{row['zasyp_id']}"
                if key not in grouped_results:
                    grouped_results[key] = {
                        'linia': row['linia'],
                        'zasyp_id': row['zasyp_id'],
                        'nr_zasypu': row['nr_zasypu'],
                        'nr_szarzy': row['nr_szarzy'],
                        'waga_zasypu': row['waga_zasypu'],
                        'data_zasypu': row['data_zasypu'],
                        'plan_id': row['plan_id'],
                        'data_planu': row['data_planu'],
                        'produkt': row['produkt'],
                        'nazwa_zlecenia': row['nazwa_zlecenia'],
                        'plan_status': row['plan_status'],
                        'zasyp_pracownik': row['zasyp_pracownik'],
                        'dosypki': []
                    }
                
                # Dodajemy dosypkę jeśli istnieje w tym wierszu
                if row['dosypka_id']:
                    grouped_results[key]['dosypki'].append({
                        'id': row['dosypka_id'],
                        'nazwa': row['dosypka_nazwa'],
                        'waga': row['dosypka_waga'],
                        'data': row['dosypka_data'],
                        'potwierdzone': row['dosypka_potwierdzone'],
                        'data_potwierdzenia': row['dosypka_data_potwierdzenia'],
                        'zlecil': row['dosypka_zlecil'],
                        'potwierdzil': row['dosypka_potwierdzil']
                    })

            # Sortujemy po dacie zasypu malejąco
            final_list = list(grouped_results.values())
            final_list.sort(key=lambda x: x['data_zasypu'] or datetime.min, reverse=True)
            
            return final_list

        except Exception as e:
            logger.error(f"Błąd podczas pobierania raportu zasypów i dosypek: {e}")
            return []
        finally:
            conn.close()
