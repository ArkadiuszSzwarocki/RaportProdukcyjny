"""
Folio routes — zarządzanie rolkami folii dla AGRO Workowanie.

Rejestruje routes:
  GET  /agro/folio                  → strona rozliczenia folii
  POST /agro/folio/close_roll       → zamknięcie rolki przez operatora
  GET  /agro/folio/api/live_status  → JSON live status (AJAX)
"""
from datetime import date

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required
from app.services.folio_service import FolioService
from app.services.agro_warehouse_service import AgroWarehouseService


def register_production_folio_routes(production_bp, bezpieczny_powrot):

    @production_bp.route('/agro/folio', methods=['GET'])
    @login_required
    @roles_required('lider', 'admin', 'pracownik', 'zarzad')
    def agro_folio_rozliczenie():
        """Strona rozliczenia rolek folii dla AGRO Workowanie."""
        data_planu = request.args.get('data', str(date.today()))
        selected_plan_id = request.args.get('plan_id', type=int)

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', 'AGRO')

            # Znajdź aktywne zlecenie Workowanie
            if selected_plan_id:
                cursor.execute(
                    f"""
                    SELECT id, produkt, data_planu, status, tonaz, tonaz_rzeczywisty,
                           start_machine_counter, stop_machine_counter, opakowanie_id
                    FROM {table_plan}
                    WHERE id = %s AND sekcja = 'Workowanie'
                    LIMIT 1
                    """,
                    (selected_plan_id,),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id, produkt, data_planu, status, tonaz, tonaz_rzeczywisty,
                           start_machine_counter, stop_machine_counter, opakowanie_id,
                           typ_produkcji
                    FROM {table_plan}
                    WHERE sekcja = 'Workowanie' AND status IN ('w toku', 'zawieszone')
                    ORDER BY FIELD(status, 'w toku', 'zawieszone') ASC, real_start DESC
                    LIMIT 1
                    """
                )
            active_plan = cursor.fetchone()

            # Jeśli brak aktywnego globally — szukaj pierwszego zaplanowanego lub ostatniego zakończonego z danego dnia
            if not active_plan:
                cursor.execute(
                    f"""
                    SELECT id, produkt, data_planu, status, tonaz, tonaz_rzeczywisty,
                           start_machine_counter, stop_machine_counter, opakowanie_id
                    FROM {table_plan}
                    WHERE data_planu = %s AND sekcja = 'Workowanie'
                    ORDER BY FIELD(status, 'zaplanowane', 'w toku', 'zawieszone', 'zakonczone') ASC, real_stop DESC, id ASC
                    LIMIT 1
                    """,
                    (data_planu,),
                )
                active_plan = cursor.fetchone()

            active_rolls = []
            history = []
            summary = {'suma_pobranych': 0, 'suma_zuzyto': 0, 'suma_strat': 0, 'suma_pozostalo': 0}
            palety_count = 0
            palety_kg = 0.0
            bag_kg = 0.0
            worki_z_palet = 0

            if active_plan:
                plan_id = active_plan['id']
                active_rolls = FolioService.get_active_rolls(plan_id)
                history = FolioService.get_plan_folio_history(plan_id)
                summary = FolioService.get_plan_folio_summary(plan_id)

                # Włącz zużycie na żywo dla aktywnych rolek do podsumowania (top card) i historii
                for roll in active_rolls:
                    live_zuzyte = roll.get('live_zuzyte', 0)
                    summary['suma_zuzyto'] += live_zuzyte
                    
                    # Filtrujemy zdarzenia WSADZENIE dla tego aktywnego linku
                    wsadzenia = [h for h in history if h.get('typ_zdarzenia') == 'WSADZENIE' and h.get('link_id') == roll.get('link_id')]
                    # Upewniamy się, że są posortowane rosnąco po czasie
                    wsadzenia.sort(key=lambda x: x.get('created_at', ''))
                    
                    for i in range(len(wsadzenia)):
                        h = wsadzenia[i]
                        start = int(h.get('licznik_start') or 0)
                        
                        # Jeśli to nie jest ostatnie wsadzenie, stopem jest start następnego wsadzenia
                        if i < len(wsadzenia) - 1:
                            stop = int(wsadzenia[i+1].get('licznik_start') or 0)
                        else:
                            # Ostatnie wsadzenie kończy się na bieżącym liczniku
                            stop = roll.get('current_counter', start)
                        
                        # Zabezpieczenie przed ujemnym zużyciem
                        if stop < start:
                            stop = start
                            
                        zuzyte_segment = stop - start
                        h['licznik_stop'] = stop
                        h['zuzyte_worki'] = zuzyte_segment
                        h['stan_po'] = max(float(h.get('stan_przed') or 0) - zuzyte_segment, 0)
                        h['pozostalo_na_rolce'] = h['stan_po']

                # Palety dla tego zlecenia
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt, COALESCE(SUM(waga), 0) AS total_kg
                    FROM palety_agro
                    WHERE plan_id = %s
                    """,
                    (plan_id,),
                )
                pallet_row = cursor.fetchone() or {}
                palety_count = int(pallet_row.get('cnt') or 0)
                palety_kg = float(pallet_row.get('total_kg') or 0)

                import re as _re
                typ_prod = str(active_plan.get('typ_produkcji') or '')
                m = _re.search(r'(\d+)\s*$', typ_prod)
                bag_kg = float(m.group(1)) if m else 0.0
                worki_z_palet = int(palety_kg / bag_kg) if bag_kg > 0 and palety_kg > 0 else 0

                # Obliczamy na żywo brakujące "zepsute worki"
                # (to co maszyna wybiła na liczniku MINUS to co faktycznie jest na paletach)
                defective_bags = max(summary['suma_zuzyto'] - worki_z_palet, 0)
                
                # Straty całkowite to: Straty folii (z bazy z zamkniętych rolek) + uszkodzone worki na żywo
                summary['suma_strat'] += defective_bags

            # Dostępne opakowania w magazynie (filtrowane po zapotrzebowaniu ze zlecenia)
            available_packaging = []
            has_required_packaging = False
            
            if active_plan and active_plan.get('opakowanie_id'):
                cursor.execute("SELECT nazwa FROM magazyn_opakowania WHERE id = %s", (active_plan['opakowanie_id'],))
                req_opak = cursor.fetchone()
                if req_opak:
                    has_required_packaging = True
                    cursor.execute("""
                        SELECT id, nazwa, stan_magazynowy, lokalizacja 
                        FROM magazyn_opakowania 
                        WHERE nazwa = %s 
                          AND stan_magazynowy > 0 
                          AND IFNULL(lokalizacja, '') NOT IN ('', 'None', 'Maszyna', 'ZUZYTE', 'ZUŻYTE', 'DO_ZWROTU')
                        ORDER BY nazwa ASC
                    """, (req_opak['nazwa'],))
                    available_packaging = cursor.fetchall()
            
            # Fallback POKAZUJE CAŁY MAGAZYN TYLKO jeśli plan nie ma przypisanego konkretnego opakowania
            if not has_required_packaging:
                cursor.execute("""
                    SELECT id, nazwa, stan_magazynowy, lokalizacja 
                    FROM magazyn_opakowania 
                    WHERE stan_magazynowy > 0 
                      AND IFNULL(lokalizacja, '') NOT IN ('', 'None', 'Maszyna', 'ZUZYTE', 'ZUŻYTE', 'DO_ZWROTU')
                    ORDER BY nazwa ASC
                """)
                available_packaging = cursor.fetchall()

            return render_template(
                'agro_folio_rozliczenie.html',
                active_plan=active_plan,
                data_planu=data_planu,
                active_rolls=active_rolls,
                history=history,
                summary=summary,
                palety_count=palety_count,
                palety_kg=palety_kg,
                bag_kg=bag_kg,
                worki_z_palet=worki_z_palet,
                lokalizacje_zwrotu=FolioService.LOKALIZACJE_ZWROTU,
                available_packaging=available_packaging,
            )
        except Exception as e:
            current_app.logger.error('Error in agro_folio_rozliczenie: %s', e)
            return 'Błąd ładowania strony rozliczenia folii', 500
        finally:
            conn.close()

    @production_bp.route('/agro/folio/close_roll', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'pracownik', 'zarzad')
    def agro_folio_close_roll():
        """Zamknięcie rolki przez operatora."""
        link_id = request.form.get('link_id', type=int)
        pozostalo_szt = request.form.get('pozostalo_szt', 0)
        data_planu = request.form.get('data_planu', str(date.today()))
        
        # New custom counters
        licznik_start_input = request.form.get('licznik_start')
        licznik_stop_input = request.form.get('licznik_stop')
        
        if not link_id:
            flash('❌ Błąd: brak identyfikatora rolki.', 'danger')
            return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

        try:
            pozostalo_szt = float(str(pozostalo_szt).replace(',', '.'))
        except (ValueError, TypeError):
            pozostalo_szt = 0.0
            
        custom_licznik_start = None
        custom_licznik_stop = None
        try:
            if licznik_start_input is not None:
                custom_licznik_start = int(licznik_start_input)
            if licznik_stop_input is not None:
                custom_licznik_stop = int(licznik_stop_input)
        except ValueError:
            pass

        ok, err = FolioService.close_roll(
            link_id=link_id,
            pozostalo_szt=pozostalo_szt,
            user_login=session.get('login', 'System'),
            custom_licznik_start=custom_licznik_start,
            custom_licznik_stop=custom_licznik_stop
        )

        source = request.form.get('source')

        if ok:
            flash(f'✅ Rolka zamknięta. Pozostało {pozostalo_szt:.0f} szt. (rolka pozostała na maszynie).', 'success')
        else:
            flash(f'❌ Błąd zamknięcia rolki: {err}', 'danger')

        if source == 'dashboard':
            return redirect(url_for('main.index', sekcja='Workowanie', linia='AGRO', data=data_planu))
        return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

    @production_bp.route('/agro/folio/add_roll', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'pracownik', 'zarzad')
    def agro_folio_add_roll():
        """Podpięcie nowej rolki z magazynu do zlecenia."""
        plan_id = request.form.get('plan_id', type=int)
        opakowanie_id = request.form.get('opakowanie_id', type=int)
        data_planu = request.form.get('data_planu', str(date.today()))
        ilosc_pobrana = request.form.get('ilosc_pobrana', type=float)

        if not plan_id or not opakowanie_id:
            flash('❌ Błąd: brak plan_id lub opakowanie_id.', 'danger')
            return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))
            
        if not ilosc_pobrana or ilosc_pobrana <= 0:
            flash('❌ Błąd: Podaj ilość do pobrania na maszynę.', 'danger')
            return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

        ok, err = AgroWarehouseService.link_packaging_to_plan(
            opakowanie_id=opakowanie_id,
            plan_id=plan_id,
            ilosc_pobrana=ilosc_pobrana,
            user_login=session.get('login', 'System')
        )

        if ok:
            flash(f'✅ Nowa rolka ({ilosc_pobrana} szt.) została dodana na maszynę.', 'success')
        else:
            flash(f'❌ Błąd dodawania rolki: {err}', 'danger')

        return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

    @production_bp.route('/agro/folio/undo_close_roll', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'pracownik', 'zarzad')
    def agro_folio_undo_close_roll():
        """Cofnięcie operacji zamknięcia rolki."""
        rozliczenie_id = request.form.get('rozliczenie_id', type=int)
        data_planu = request.form.get('data_planu', str(date.today()))

        if not rozliczenie_id:
            flash('❌ Błąd: Brak ID operacji do cofnięcia.', 'danger')
            return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

        ok, err = FolioService.undo_close_roll(rozliczenie_id, session.get('login', 'System'))
        
        if ok:
            flash('✅ Operacja zamknięcia rolki została cofnięta.', 'success')
        else:
            flash(f'❌ Błąd cofania operacji: {err}', 'danger')

        return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

    @production_bp.route('/agro/folio/edit_active_roll', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'pracownik', 'zarzad')
    def agro_folio_edit_active_roll():
        """Korekta wsadzenia dla aktywnej rolki na maszynie."""
        link_id = request.form.get('link_id', type=int)
        new_amount = request.form.get('new_amount', type=float)
        data_planu = request.form.get('data_planu', str(date.today()))

        if not link_id or not new_amount:
            flash('❌ Błąd: Brak ID rolki lub nowej ilości.', 'danger')
            return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

        ok, err = FolioService.edit_active_roll(link_id, new_amount, session.get('login', 'System'))
        if ok:
            flash(f'✅ Zaktualizowano wsadzenie aktywnej rolki na {new_amount} szt.', 'success')
        else:
            flash(f'❌ Błąd korekty rolki: {err}', 'danger')

        return redirect(url_for('production.agro_folio_rozliczenie', data=data_planu))

    @production_bp.route('/agro/folio/api/live_status', methods=['GET'])
    @login_required
    def agro_folio_live_status():
        """JSON endpoint: live status rolek (AJAX polling)."""
        plan_id = request.args.get('plan_id', type=int)
        if not plan_id:
            return jsonify({'error': 'Brak plan_id'}), 400
        try:
            data = FolioService.get_live_status(plan_id)
            return jsonify(data)
        except Exception as e:
            current_app.logger.error('Error in agro_folio_live_status: %s', e)
            return jsonify({'error': str(e)}), 500
