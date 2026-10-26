"""Individual film withdrawals; NULL start counter means prepared, not consuming.

Each withdrawal owns a separate packaging row. Source pallet identity is preserved
in the existing warehouse movement metadata, so no remote schema migration is needed.
"""
import json
import math
import unicodedata
from app.db import get_db_connection


def _film_name(value):
    return ' '.join(unicodedata.normalize('NFC', str(value or '')).casefold().split())


class FolioAssignmentService:
    @staticmethod
    def plans(source_id=None):
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            source_name = None
            if source_id is not None:
                cur.execute("SELECT nazwa FROM magazyn_opakowania WHERE id=%s", (int(source_id),))
                source = cur.fetchone()
                if not source:
                    return []
                source_name = _film_name(source['nazwa'])
            cur.execute("""SELECT p.id, p.produkt, p.data_planu, p.status, o.nazwa AS wymagana_folia,
                (SELECT COUNT(*) FROM agro_plan_opakowania ap WHERE ap.plan_id=p.id AND ap.is_active=TRUE AND ap.licznik_start IS NOT NULL) AS used_rolls,
                (SELECT COUNT(*) FROM agro_plan_opakowania ap WHERE ap.plan_id=p.id AND ap.is_active=TRUE) AS total_rolls
                FROM plan_produkcji_agro p LEFT JOIN magazyn_opakowania o ON o.id=p.opakowanie_id
                WHERE p.sekcja='Workowanie' AND p.status IN ('zaplanowane','w toku','zawieszone')
                AND COALESCE(p.is_deleted,0)=0
                AND (p.status <> 'zaplanowane' OR p.data_planu BETWEEN CURRENT_DATE - INTERVAL 6 DAY AND CURRENT_DATE)
                ORDER BY FIELD(p.status,'w toku','zawieszone','zaplanowane'),p.data_planu,p.id""")
            plans = cur.fetchall()
            if source_name is not None:
                plans = [plan for plan in plans if plan.get('wymagana_folia') and _film_name(plan['wymagana_folia']) == source_name]
            for plan in plans:
                plan['data_planu'] = str(plan.get('data_planu') or '')
            return plans
        finally:
            conn.close()

    @staticmethod
    def assign(source_id, plan_id, amount, user, role='prepared', request_key=None, previous_remaining=None):
        if role not in ('auto', 'active', 'prepared', 'replace'):
            return False, 'Nieprawidłowe przeznaczenie rolki.'
        try:
            amount = float(amount)
            source_id, plan_id = int(source_id), int(plan_id)
            if not math.isfinite(amount) or amount <= 0 or not amount.is_integer():
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            return False, 'Podaj dodatnią, całkowitą liczbę sztuk na rolce.'
        if request_key:
            import uuid
            try:
                request_key = str(uuid.UUID(str(request_key)))
            except ValueError:
                return False, 'Nieprawidłowy identyfikator pobrania.'
        conn = get_db_connection()
        labels = []
        replacing = role == 'replace'
        try:
            cur = conn.cursor(dictionary=True)
            # Lock the order before slots/source: concurrent requests cannot overfill it.
            cur.execute("SELECT id,produkt,data_planu,status,opakowanie_id FROM plan_produkcji_agro WHERE id=%s AND sekcja='Workowanie' AND COALESCE(is_deleted,0)=0 FOR UPDATE", (plan_id,))
            plan = cur.fetchone()
            if not plan or plan['status'] not in ('zaplanowane','w toku','zawieszone','wstrzymane'):
                raise ValueError('Wybierz niezakończone zlecenie Workowania AGRO.')
            if request_key:
                cur.execute("SELECT id FROM magazyn_ruch WHERE typ_ruchu='POBRANIE_NA_MASZYNE' AND komentarz LIKE %s LIMIT 1", ('%'+request_key+'%',))
                if cur.fetchone():
                    conn.rollback()
                    return True, 'To pobranie zostało już zapisane.'
            cur.execute("SELECT id,licznik_start FROM agro_plan_opakowania WHERE plan_id=%s AND is_active=TRUE FOR UPDATE", (plan_id,))
            slots = cur.fetchall()
            used = [row for row in slots if row['licznik_start'] is not None]
            if replacing and (plan['status'] != 'w toku' or len(used) != 1):
                raise ValueError('Zmiana rolki wymaga zlecenia w toku z jedną używaną rolką.')
            if replacing:
                try:
                    previous_remaining = float(previous_remaining)
                    if not math.isfinite(previous_remaining) or previous_remaining < 0 or not previous_remaining.is_integer():
                        raise ValueError()
                except (ValueError, TypeError, OverflowError):
                    raise ValueError('Wpisz pozostałość na poprzedniej rolce (szt.), również gdy wynosi 0.')
            if len(slots) - int(replacing) >= 2:
                raise ValueError('Zlecenie ma już dwie rolki. Najpierw rozlicz lub zwróć jedną z nich.')
            has_active = bool(used)
            if role == 'auto':
                role = 'active' if plan['status']=='w toku' and not has_active else 'prepared'
            if role == 'active' and (has_active or plan['status']!='w toku'):
                raise ValueError('Używana rolka wymaga zlecenia w toku bez innej używanej rolki. Wybierz przygotowanie do wymiany.')
            cur.execute("SELECT * FROM magazyn_opakowania WHERE id=%s FOR UPDATE", (source_id,))
            source = cur.fetchone()
            if not source or source.get('is_blocked') or amount > float(source['stan_magazynowy'] or 0):
                raise ValueError('Brak wystarczającego, niezablokowanego zapasu na wskazanej palecie.')
            cur.execute("SELECT id FROM agro_plan_opakowania WHERE opakowanie_id=%s AND is_active=TRUE LIMIT 1", (source_id,))
            if cur.fetchone():
                raise ValueError('Ta rolka jest już przypisana do zlecenia. Zeskanuj paletę źródłową.')
            if not plan.get('opakowanie_id'):
                raise ValueError('To zlecenie nie ma przypisanej folii w planowaniu.')
            if plan.get('opakowanie_id'):
                cur.execute("SELECT nazwa FROM magazyn_opakowania WHERE id=%s", (plan['opakowanie_id'],))
                required = cur.fetchone()
                if not required or _film_name(required['nazwa']) != _film_name(source['nazwa']):
                    raise ValueError('Ta folia nie odpowiada folii wymaganej przez wybrane zlecenie.')
            from app.utils.pallet_id import generate_pallet_id
            from app.services.folio_service import _get_mqtt_counter
            if replacing:
                from app.services.folio_service import FolioService
                ok, error = FolioService.close_roll(used[0]['id'], previous_remaining, user,
                    external_conn=conn, label_jobs=labels)
                if not ok:
                    raise ValueError(error)
                role = 'active'
            remaining = float(source['stan_magazynowy']) - amount
            cur.execute("UPDATE magazyn_opakowania SET stan_magazynowy=%s,updated_at=NOW() WHERE id=%s", (remaining,source_id))
            cur.execute("""INSERT INTO magazyn_opakowania
                (nazwa,stan_magazynowy,lokalizacja,nr_palety,nr_partii,data_produkcji,data_przydatnosci,typ_opakowania,linia)
                VALUES (%s,%s,'LP01',%s,%s,%s,%s,%s,%s)""",
                (source['nazwa'],amount,generate_pallet_id('AGRO','opakowanie'),source.get('nr_partii'),source.get('data_produkcji'),source.get('data_przydatnosci'),source.get('typ_opakowania'),'AGRO'))
            roll_id = cur.lastrowid
            counter = _get_mqtt_counter() if role=='active' else None
            cur.execute("INSERT INTO agro_plan_opakowania (plan_id,opakowanie_id,stan_poczatkowy,is_active,licznik_start) VALUES (%s,%s,%s,TRUE,%s)", (plan_id,roll_id,amount,counter))
            link_id = cur.lastrowid
            meta = json.dumps({'source_id':source_id,'source_sscc':source.get('nr_palety') or '', 'plan_id':plan_id,'link_id':link_id,'request_key':request_key},ensure_ascii=False)
            for material_id, kind, qty, stock in [(source_id,'POBRANIE_DO_PRODUKCJI',-amount,remaining),(roll_id,'POBRANIE_NA_MASZYNE',amount,amount)]:
                cur.execute("INSERT INTO magazyn_ruch (surowiec_id,typ_ruchu,ilosc,ilosc_po,status,autor_login,autor_data,komentarz) VALUES (%s,%s,%s,%s,'POTWIERDZONE',%s,NOW(),%s)", (material_id,kind,qty,stock,user,meta))
            cur.execute("""INSERT INTO agro_workowanie_rozliczenie
                (plan_id,data_planu,produkt,opakowanie_id,opakowanie_nazwa,stan_przed,zuzyte_worki,stan_po,autor_login,typ_zdarzenia,licznik_start,link_id)
                VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,'WSADZENIE',%s,%s)""",
                (plan_id,plan['data_planu'],plan['produkt'],roll_id,source['nazwa'],amount,amount,user,counter,link_id))
            conn.commit()
            if labels:
                from app.services.folio_service import FolioService
                FolioService.print_closed_roll_labels(labels)
            if replacing:
                return True, 'Poprzednia rolka została rozliczona i zamknięta. Nowa rolka jest używana.'
            return True, 'Rolka przypisana: '+('używana.' if role=='active' else 'przygotowana do wymiany.')
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            conn.close()

    @staticmethod
    def activate(link_id, user, close_link_id=None, remaining=None):
        from app.services.folio_service import FolioService, _get_mqtt_counter
        conn = get_db_connection()
        labels = []
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT plan_id FROM agro_plan_opakowania WHERE id=%s", (link_id,))
            target = cur.fetchone()
            if not target:
                raise ValueError('Nie znaleziono przygotowanej rolki.')
            cur.execute("SELECT status FROM plan_produkcji_agro WHERE id=%s FOR UPDATE", (target['plan_id'],))
            plan = cur.fetchone()
            if not plan or plan['status']!='w toku':
                raise ValueError('Rolkę można założyć dopiero, gdy zlecenie jest w toku.')
            cur.execute("SELECT id,licznik_start FROM agro_plan_opakowania WHERE plan_id=%s AND is_active=TRUE FOR UPDATE", (target['plan_id'],))
            slots = cur.fetchall()
            prepared = next((row for row in slots if row['id']==int(link_id) and row['licznik_start'] is None),None)
            if not prepared:
                raise ValueError('Rolka nie jest przygotowana do wymiany.')
            active = [row for row in slots if row['licznik_start'] is not None]
            if active:
                if len(active)!=1 or not close_link_id or active[0]['id']!=int(close_link_id):
                    raise ValueError('Najpierw zamknij używaną rolkę, wpisując jej pozostałość.')
                ok,error = FolioService.close_roll(int(close_link_id),remaining,user,external_conn=conn,label_jobs=labels)
                if not ok:
                    raise ValueError(error)
            counter = _get_mqtt_counter()
            cur.execute("UPDATE agro_plan_opakowania SET licznik_start=%s WHERE id=%s",(counter,link_id))
            cur.execute("UPDATE agro_workowanie_rozliczenie SET licznik_start=%s WHERE link_id=%s AND typ_zdarzenia='WSADZENIE'",(counter,link_id))
            cur.execute("INSERT INTO magazyn_ruch (surowiec_id,typ_ruchu,ilosc,status,autor_login,autor_data,komentarz) SELECT opakowanie_id,'ZALOZENIE_ROLKI',0,'POTWIERDZONE',%s,NOW(),%s FROM agro_plan_opakowania WHERE id=%s",(user,'Założenie przygotowanej rolki do zlecenia #'+str(target['plan_id']),link_id))
            conn.commit()
            FolioService.print_closed_roll_labels(labels)
            return True, 'Przygotowana rolka jest teraz używana.'
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            conn.close()
