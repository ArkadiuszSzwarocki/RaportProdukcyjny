from flask import current_app
from datetime import date
from app.db import get_table_name
from app.core.audit import audit_log
from app.services.notification_service import notify_workers_about_plan_batch

class DodajPlanyBatchCommand:
    """Command to handle batch plan creation."""
    
    @staticmethod
    def execute(conn, cursor, data_planu, plans, session):
        table_psd = get_table_name('plan_produkcji', 'PSD')
        cursor.execute(
            f"""
            SELECT sekcja, MAX(kolejnosc) as max_seq
            FROM {table_psd}
            WHERE data_planu=%s
            GROUP BY sekcja
            """,
            (data_planu,),
        )
        max_seq_map = {row[0]: (row[1] if row[1] else 0) for row in cursor.fetchall()}

        table_agro = get_table_name('plan_produkcji', 'Agro')
        cursor.execute(
            f"""
            SELECT sekcja, MAX(kolejnosc) as max_seq
            FROM {table_agro}
            WHERE data_planu=%s
            GROUP BY sekcja
            """,
            (data_planu,),
        )
        max_seq_map_agro = {row[0]: (row[1] if row[1] else 0) for row in cursor.fetchall()}

        for idx, plan in enumerate(plans, start=1):
            produkt = (plan.get('produkt') or '').strip()
            try:
                tonaz = int(float(plan.get('tonaz') or 0))
            except Exception as parse_err:
                current_app.logger.debug(f'Row {idx} tonaz parse error: {parse_err}')
                tonaz = 0
                
            typ = (plan.get('typ_produkcji') or '').strip() or 'worki_zgrzewane_25'
            typ_opakowania = (plan.get('typ_opakowania') or '').strip() or 'worki'
            rodzaj_palety = (plan.get('rodzaj_palety') or '').strip() or 'krajowa'
            termin_przydatnosci = plan.get('termin_przydatnosci') or None
            sekcja = (plan.get('sekcja') or 'Zasyp').strip()
            sekcja = sekcja[0].upper() + sekcja[1:].lower() if sekcja else 'Zasyp'
            nr = plan.get('nr_receptury') or ''
            
            if not produkt:
                return False, f'Wiersz {idx}: brak nazwy produktu'
            if not (isinstance(tonaz, int) and tonaz > 0):
                return False, f'Wiersz {idx}: nieprawidłowy tonaż'
            if not typ:
                return False, f'Wiersz {idx}: brak typu produkcji'

            target_linia = 'Agro' if sekcja == 'Agro' else 'PSD'
            table_target = get_table_name('plan_produkcji', target_linia)

            cursor.execute(
                f'SELECT id FROM {table_target} WHERE data_planu=%s AND produkt=%s AND (is_deleted=0 OR is_deleted IS NULL) LIMIT 1',
                (data_planu, produkt),
            )
            if cursor.fetchone():
                return False, f'Wiersz {idx}: zlecenie dla {produkt} już istnieje na {data_planu} — edytuj istniejący plan.'

            if sekcja == 'Agro':
                opakowanie_id_val = plan.get('opakowanie_id')
                etykieta_id_val = plan.get('etykieta_id')
                
                try:
                    opakowanie_id = int(opakowanie_id_val) if opakowanie_id_val not in (None, '', 'None') else None
                except Exception:
                    opakowanie_id = None
                    
                try:
                    etykieta_id = int(etykieta_id_val) if etykieta_id_val not in (None, '', 'None') else None
                except Exception:
                    etykieta_id = None

                if typ_opakowania == 'worki' and (not opakowanie_id or not etykieta_id):
                    return False, f'Wiersz {idx}: Dla linii AGRO z workami wyznaczony worek (opakowanie) oraz etykieta są obowiązkowe!'

                nk_agro = max_seq_map_agro.get('Agro', 0) + 1
                max_seq_map_agro['Agro'] = nk_agro
                cursor.execute(
                    f'INSERT INTO {table_agro} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety, termin_przydatnosci) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (data_planu, produkt, tonaz, 'zaplanowane', 'Zasyp', nk_agro, typ, nr, 0, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety, termin_przydatnosci),
                )

                nk_work_agro = max_seq_map_agro.get('Workowanie', 0) + 1
                max_seq_map_agro['Workowanie'] = nk_work_agro
                zasyp_id_agro = cursor.lastrowid
                cursor.execute(
                    f'INSERT INTO {table_agro} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety, termin_przydatnosci) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (data_planu, produkt, 0, 'zaplanowane', 'Workowanie', nk_work_agro, typ, 0, zasyp_id_agro, opakowanie_id, etykieta_id, typ_opakowania, rodzaj_palety, termin_przydatnosci),
                )
                continue

            nk_zasyp = max_seq_map.get('Zasyp', 0) + 1
            max_seq_map['Zasyp'] = nk_zasyp
            cursor.execute(
                f'INSERT INTO {table_psd} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, nr_receptury, tonaz_rzeczywisty, typ_opakowania, rodzaj_palety, termin_przydatnosci) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (data_planu, produkt, tonaz, 'zaplanowane', sekcja, nk_zasyp, typ, nr, 0, typ_opakowania, rodzaj_palety, termin_przydatnosci),
            )

            if sekcja == 'Zasyp':
                nk_work = max_seq_map.get('Workowanie', 0) + 1
                max_seq_map['Workowanie'] = nk_work
                zasyp_id_created = cursor.lastrowid
                cursor.execute(
                    f'INSERT INTO {table_psd} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, typ_opakowania, rodzaj_palety, termin_przydatnosci) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (data_planu, produkt, 0, 'zaplanowane', 'Workowanie', nk_work, typ, 0, zasyp_id_created, typ_opakowania, rodzaj_palety, termin_przydatnosci),
                )

        notify_workers_about_plan_batch(
            data_planu=data_planu,
            plans_count=len(plans),
            author_name=session.get('imie_nazwisko') or session.get('login'),
            conn=conn,
            cursor=cursor,
            created_by_user_id=session.get('user_id'),
            linia='PSD',
        )
        
        current_app.logger.info('Dodano %s zleceń na dzień %s przez %s', len(plans), data_planu, session.get('login'))
        audit_log('Dodał zlecenia (bulk)', f'{len(plans)} zleceń na {data_planu}')
        
        return True, ''
