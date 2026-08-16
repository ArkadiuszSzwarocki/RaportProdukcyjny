from flask import current_app
from datetime import datetime as _dt
import logging

from app.db import get_table_name, refresh_bufor_queue, get_plan_notification_context
from app.core.audit import audit_log
from app.services.notification_service import notify_laboratory_about_zasyp

class DodajSzarzeCommand:
    """Command to handle adding a szarza (zasyp) to a plan."""
    
    @staticmethod
    def execute(conn, cursor, linia, data_planu, produkt, tonaz, typ, plan_id_provided, nr_szarzy, auto_szarza_mode, is_admin, session, request_path, ui_trigger, rodzaj_palety='krajowa'):
        table_plan = get_table_name('plan_produkcji', linia)
        table_szarze = get_table_name('szarze', linia)
        table_dosypki = get_table_name('dosypki', linia)
        
        zasyp_plan_id = None
        if plan_id_provided > 0:
            zasyp_plan_id = plan_id_provided
        else:
            cursor.execute(
                f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Zasyp' AND COALESCE(typ_produkcji,'')=%s ORDER BY id DESC LIMIT 1",
                (data_planu, produkt, typ),
            )
            szarza_plan = cursor.fetchone()
            if szarza_plan:
                zasyp_plan_id = szarza_plan[0]
                
        if not zasyp_plan_id:
            return False, 'Nie znaleziono planu do dodania zasypu'
            
        if not nr_szarzy:
            return False, 'Musisz podać numer zasypu!'
            
        cursor.execute(f'SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s', (zasyp_plan_id,))
        max_nr_row = cursor.fetchone()
        max_nr = max_nr_row[0] if max_nr_row else 0
        expected_nr = (max_nr or 0) + 1
        
        if str(linia).upper() == 'AGRO' and auto_szarza_mode == 'auto' and not is_admin:
            return False, 'BŁĄD: Tryb AUTO SZARŻA jest włączony. Ręczne + ZASYP jest zablokowane - użyj START Naważania.'
            
        if nr_szarzy != expected_nr and not is_admin:
            return False, f'BŁĄD: Podałeś błędny numer zasypu ({nr_szarzy}). Wykryto naruszenie kolejności! (Oczekiwano: {expected_nr}). Zweryfikuj prawidłowy numer zasypu z recepturą.'
            
        if str(linia).upper() == 'AGRO' and not is_admin:
            try:
                cursor.execute(
                    "SELECT COUNT(DISTINCT szarza_nr) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
                    (str(linia).upper(), int(zasyp_plan_id)),
                )
                kontrolne_row = cursor.fetchone()
                kontrolne_count = int(kontrolne_row[0] if kontrolne_row else 0)
            except Exception:
                kontrolne_count = 0

            target_szarza_nr = int(nr_szarzy)
            if target_szarza_nr > kontrolne_count:
                try:
                    linia_u = str(linia).upper()
                    start_login = (session.get('login') or '')[:100]
                    for missing_szarza_nr in range(kontrolne_count + 1, target_szarza_nr + 1):
                        cursor.execute(
                            """
                            INSERT INTO zasyp_etapy (linia, plan_id, data_planu, szarza_nr, etap, czas_start, czas_stop, start_login, stop_login)
                            VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s, NULL)
                            ON DUPLICATE KEY UPDATE plan_id = plan_id
                            """,
                            (linia_u, int(zasyp_plan_id), data_planu, int(missing_szarza_nr), 0, start_login),
                        )
                except Exception:
                    return False, f'BŁĄD: Nie udało się zsynchronizować punktów kontrolnych dla zasypu #{nr_szarzy}.'

        now = _dt.now()
        godzina = now.strftime('%H:%M:%S')
        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

        cursor.execute(
            f'INSERT INTO {table_szarze} (plan_id, waga, data_dodania, godzina, pracownik_id, status, nr_szarzy) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (zasyp_plan_id, tonaz, now, godzina, pracownik_id, 'zarejestowana', nr_szarzy),
        )

        cursor.execute(
            f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
            f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
            f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
            f"WHERE id = %s",
            (zasyp_plan_id, zasyp_plan_id, zasyp_plan_id),
        )
        
        try:
            current_app.logger.info(
                'Dodano zasyp do zlecenia ID=%s, produkt=%s, tonaz=%s kg, użytkownik=%s',
                zasyp_plan_id, produkt, tonaz, session.get('login'),
            )
            audit_log('Dodał zasyp', f'zlecenie_id={zasyp_plan_id}, produkt={produkt}, tonaz={tonaz} kg, nr={nr_szarzy}, linia={linia}, trigger={ui_trigger}')
        except Exception:
            pass

        plan_context = get_plan_notification_context(zasyp_plan_id, conn=conn, linia=linia)
        notify_laboratory_about_zasyp(
            plan_context=plan_context,
            weight_kg=tonaz,
            author_name=session.get('imie_nazwisko') or session.get('login'),
            conn=conn,
            cursor=cursor,
            created_by_user_id=session.get('user_id'),
            linia=linia,
        )
        
        # Link to workowanie
        cursor.execute(
            f"SELECT id, tonaz, zasyp_id FROM {table_plan} WHERE zasyp_id=%s AND sekcja IN ('Workowanie', 'Czyszczenie') ORDER BY id ASC LIMIT 1",
            (zasyp_plan_id,),
        )
        workowanie_plan = cursor.fetchone()
        if not workowanie_plan:
            cursor.execute(
                f"SELECT id, tonaz, zasyp_id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja IN ('Workowanie', 'Czyszczenie') ORDER BY id ASC LIMIT 1",
                (data_planu, produkt),
            )
            workowanie_plan = cursor.fetchone()

        if not workowanie_plan:
            cursor.execute(f'SELECT typ_produkcji FROM {table_plan} WHERE id=%s', (zasyp_plan_id,))
            source_row = cursor.fetchone()
            source_typ = source_row[0] if source_row else 'worki_zgrzewane_25'

            cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja IN ('Workowanie', 'Czyszczenie')", (data_planu,))
            res = cursor.fetchone()
            nk_work = (res[0] if res and res[0] else 0) + 1

            cursor.execute(
                f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, tonaz_rzeczywisty, zasyp_id, rodzaj_palety) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (data_planu, produkt, tonaz, 'zaplanowane', 'Workowanie', nk_work, source_typ, 0, zasyp_plan_id, rodzaj_palety),
            )
        else:
            workowanie_id = workowanie_plan[0]
            w_existing_tonaz = workowanie_plan[1] or 0
            w_zasyp_id = workowanie_plan[2]

            cursor.execute(f"SELECT id, tonaz FROM {table_plan} WHERE zasyp_id=%s AND sekcja IN ('Workowanie', 'Czyszczenie') ORDER BY id ASC LIMIT 1", (zasyp_plan_id,))
            linked = cursor.fetchone()
            if linked:
                target_id, target_existing_tonaz = linked[0], linked[1] or 0
                new_workowanie_tonaz = target_existing_tonaz + tonaz
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zaplanowane', real_start=NULL, real_stop=NULL, tonaz=%s WHERE id=%s AND status!='w toku'",
                    (new_workowanie_tonaz, target_id),
                )
                try:
                    status_logger = logging.getLogger('status_changes')
                    status_logger.info('action=update_workowanie plan_id=%s old_tonaz=%s new_tonaz=%s user=%s', target_id, target_existing_tonaz, new_workowanie_tonaz, session.get('login'))
                except Exception:
                    pass
            else:
                if not w_zasyp_id:
                    try:
                        cursor.execute(f'UPDATE {table_plan} SET zasyp_id=%s WHERE id=%s', (zasyp_plan_id, workowanie_id))
                    except Exception:
                        pass
                new_workowanie_tonaz = w_existing_tonaz + tonaz
                cursor.execute(
                    f"UPDATE {table_plan} SET status='zaplanowane', real_start=NULL, real_stop=NULL, tonaz=%s WHERE id=%s AND status!='w toku'",
                    (new_workowanie_tonaz, workowanie_id),
                )
        return True, ''
