from datetime import datetime

from flask import current_app, flash, redirect, request, session

from app.decorators import login_required


def register_production_zasyp_flow_routes(
    production_bp,
    bezpieczny_powrot,
    _coerce_date,
    _parse_float,
    _flash_zasyp_result,
    _insert_szarza_compatible,
    _notify_laboratory_stage_start,
    get_db_connection,
    get_table_name,
    ZasypEtapyService,
    audit_log,
):
    def _read_zasyp_nr():
        raw = (
            request.form.get('zasyp_nr')
            or request.form.get('szarza_nr')
            or request.args.get('zasyp_nr')
            or request.args.get('szarza_nr')
        )
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    @production_bp.route('/zasyp_etap_start', methods=['POST'])
    @login_required
    def zasyp_etap_start():
        """START etapu 1-6 dla zlecenia Zasyp (na aktywnym zleceniu)."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        plan_id_raw = request.form.get('plan_id')
        etap_raw = request.form.get('etap')
        kg_raw = request.form.get('wielkosc_szarzy_kg')
        szarza_nr_raw = _read_zasyp_nr()
        role = str(session.get('rola') or '').lower().strip()
        default_auto_mode = 'auto' if role in ['operator', 'pracownik', 'produkcja', 'lider', 'admin', 'masteradmin', 'master admin', 'master_admin'] else 'manual'
        auto_szarza_mode = str(request.form.get('auto_szarza_mode') or default_auto_mode).strip().lower()

        try:
            plan_id = int(plan_id_raw)
            etap = int(etap_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane START etapu', 'danger')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, data_planu, produkt, typ_produkcji FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
            typ_produkcji = row[4] if len(row) > 4 else None
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
            data_planu_date = _coerce_date(data_planu)
        except Exception as e:
            current_app.logger.error('zasyp_etap_start failed: %s', e, exc_info=True)
            flash('❌ Błąd START etapu', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        kg_for_auto = None
        if etap == 1:
            kg = _parse_float(kg_raw)
            if kg is None:
                param = ZasypEtapyService.get_parametry(plan_id, linia)
                if param.get('wielkosc_szarzy_kg') is None:
                    flash('❌ Podaj wielkość zasypu przed startem Naważania', 'danger')
                    return redirect(bezpieczny_powrot())
                try:
                    kg_for_auto = float(param.get('wielkosc_szarzy_kg'))
                except Exception:
                    kg_for_auto = None
            else:
                ok_kg, msg_kg = ZasypEtapyService.set_wielkosc_szarzy(
                    plan_id=plan_id,
                    linia=linia,
                    data_planu=data_planu_date,
                    kg=kg,
                    user_login=session.get('login') or '',
                )
                if not ok_kg:
                    flash(f'❌ {msg_kg}', 'danger')
                    return redirect(bezpieczny_powrot())
                kg_for_auto = kg

        restart_intent = str(request.form.get('restart_intent') or '0').strip().lower() in ['1', 'true', 'yes', 'on']
        
        current_app.logger.info(f'[START-ETAP-RESTART] plan_id={plan_id}, etap={etap}, szarza={szarza_nr_raw}, linia={linia}, allow_restart={restart_intent}')

        ok, msg = ZasypEtapyService.start_etap(
            plan_id=plan_id,
            linia=linia,
            data_planu=data_planu_date,
            etap=etap,
            user_login=session.get('login') or '',
            szarza_nr=szarza_nr_raw,
            allow_restart=restart_intent,
        )
        
        if restart_intent:
            current_app.logger.info(f'[START-ETAP-RESTART-RESULT] ok={ok}, msg={msg}')

        # AUTO SZARZA mode: when Naważanie starts, add one szarża automatically
        if ok and etap == 1 and auto_szarza_mode == 'auto' and 'zapisany' in str(msg).lower():
            try:
                auto_kg = float(kg_for_auto) if kg_for_auto is not None else None
            except Exception:
                auto_kg = None

            if auto_kg and auto_kg > 0:
                auto_conn = None
                try:
                    auto_conn = get_db_connection()
                    auto_cursor = auto_conn.cursor()
                    table_szarze = get_table_name('szarze', linia)
                    table_plan = get_table_name('plan_produkcji', linia)
                    table_dosypki = get_table_name('dosypki', linia)

                    target_szarza_nr = None
                    try:
                        parsed = int(str(szarza_nr_raw or '').strip())
                        if parsed > 0:
                            target_szarza_nr = parsed
                    except Exception:
                        target_szarza_nr = None

                    if target_szarza_nr is None:
                        auto_cursor.execute(
                            "SELECT COALESCE(MAX(szarza_nr), 1) FROM zasyp_etapy WHERE linia=%s AND plan_id=%s",
                            (str(linia or '').upper(), plan_id),
                        )
                        row = auto_cursor.fetchone()
                        try:
                            target_szarza_nr = int(row[0] if row and row[0] else 1)
                        except Exception:
                            target_szarza_nr = 1

                    if not target_szarza_nr or target_szarza_nr <= 0:
                        target_szarza_nr = 1

                    now = datetime.now()
                    godzina = now.strftime('%H:%M:%S')
                    pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                    auto_cursor.execute(
                        f"SELECT id FROM {table_szarze} WHERE plan_id=%s AND nr_szarzy=%s LIMIT 1",
                        (plan_id, target_szarza_nr),
                    )
                    exists_row = auto_cursor.fetchone()

                    if exists_row:
                        msg = f"{msg}; AUTO ZASYP: zasyp #{target_szarza_nr} już istnieje"
                    else:
                        _insert_szarza_compatible(
                            auto_cursor,
                            table_szarze,
                            plan_id=plan_id,
                            nr_szarzy=target_szarza_nr,
                            waga=auto_kg,
                            godzina=godzina,
                            data_dodania=now,
                            pracownik_id=pracownik_id,
                            produkt=produkt,
                            typ_produkcji=typ_produkcji,
                            data_planu=data_planu_date,
                        )

                        auto_cursor.execute(
                            f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                            f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                            f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                            f"WHERE id = %s",
                            (plan_id, plan_id, plan_id),
                        )

                        auto_conn.commit()
                        msg = f"{msg}; AUTO ZASYP: dodano nr {target_szarza_nr} ({auto_kg:g} kg)"
                        audit_log(
                            'AUTO dodał zasyp',
                            f'zlecenie_id={plan_id}, produkt={produkt}, tonaz={auto_kg:g} kg, nr={target_szarza_nr}, linia={linia}, trigger=system:auto_start_etap_1',
                        )
                        try:
                            from app.blueprints.routes_production import _mark_dosypki_updated
                            _mark_dosypki_updated(linia)
                        except Exception:
                            pass
                except Exception as auto_err:
                    try:
                        if auto_conn:
                            auto_conn.rollback()
                    except Exception:
                        pass
                    msg = f"{msg}; AUTO ZASYP: błąd dodania ({auto_err})"
                finally:
                    try:
                        if auto_conn:
                            auto_conn.close()
                    except Exception:
                        pass

        _flash_zasyp_result(ok, msg)
        if ok:
            audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
            # If stage start requires laboratorium notification, register event + optional TTS file.
            try:
                _notify_laboratory_stage_start(
                    linia,
                    plan_id,
                    etap,
                    produkt,
                    szarza_nr=szarza_nr_raw,
                )
            except Exception:
                current_app.logger.exception('Failed post-start zasyp notification')
        return redirect(bezpieczny_powrot())

    @production_bp.route('/zasyp_etap_stop', methods=['POST'])
    @login_required
    def zasyp_etap_stop():
        """STOP etapu 1-6 dla zlecenia Zasyp."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        plan_id_raw = request.form.get('plan_id')
        etap_raw = request.form.get('etap')
        szarza_nr_raw = _read_zasyp_nr()
        next_action = str(request.form.get('next_action') or '').strip().lower()
        role = str(session.get('rola') or '').lower()
        default_auto_mode = 'auto' if role in ['operator', 'pracownik', 'produkcja', 'lider', 'admin', 'masteradmin'] else 'manual'
        auto_szarza_mode = str(request.form.get('auto_szarza_mode') or default_auto_mode).strip().lower()
        auto_szarza_enabled = auto_szarza_mode == 'auto'

        try:
            plan_id = int(plan_id_raw)
            etap = int(etap_raw)
        except Exception:
            flash('❌ Nieprawidłowe dane STOP etapu', 'danger')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT sekcja, status, data_planu, produkt, typ_produkcji FROM {table_plan} WHERE id=%s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                flash('❌ Zlecenie nie znalezione', 'danger')
                return redirect(bezpieczny_powrot())
            sekcja, status, data_planu, produkt = row[0], row[1], row[2], row[3]
            typ_produkcji = row[4] if len(row) > 4 else None
            if sekcja != 'Zasyp':
                flash('❌ To nie jest zlecenie Zasyp', 'danger')
                return redirect(bezpieczny_powrot())
            if status != 'w toku':
                flash('❌ Zlecenie musi być W TOKU', 'danger')
                return redirect(bezpieczny_powrot())
            data_planu_date = _coerce_date(data_planu)
        except Exception as e:
            current_app.logger.error('zasyp_etap_stop failed: %s', e, exc_info=True)
            flash('❌ Błąd STOP etapu', 'danger')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

        ok, msg = ZasypEtapyService.stop_etap(
            plan_id=plan_id,
            linia=linia,
            etap=etap,
            user_login=session.get('login') or '',
            szarza_nr=szarza_nr_raw,
        )

        if ok:
            next_etap = None
            wants_new_point_after_empty = False
            if linia == 'AGRO':
                # AGRO flow: 1 -> 2, then PAUZA (no auto-start for 2). Dosypka starts after etap 3 stop.
                if etap == 1:
                    next_etap = 2
                elif etap == 2 or etap == 4 or str(etap).startswith('4'):
                    if next_action not in ('add_pair', 'oprozniamy', 'oprozniamy_end_today', 'oprozniamy_new_point'):
                        msg = f"{msg}; brak wyboru w oknie decyzji - nie uruchomiono kolejnego etapu"
                    elif next_action in ('oprozniamy', 'oprozniamy_end_today', 'oprozniamy_new_point'):
                        next_etap = 5
                        wants_new_point_after_empty = next_action == 'oprozniamy_new_point'
                    elif next_action == 'add_pair':
                        pair_ok, pair_msg = ZasypEtapyService.add_agro_dosypka_pair(
                            plan_id=plan_id,
                            linia=linia,
                            data_planu=data_planu_date,
                            user_login=session.get('login') or '',
                            szarza_nr=szarza_nr_raw,
                        )
                        if pair_ok:
                            pair_start = None
                            cleaned = str(pair_msg).replace('/', ' ').replace(',', ' ')
                            for token in cleaned.split():
                                try:
                                    pair_start = int(token)
                                    break
                                except Exception:
                                    continue
                            if pair_start is not None:
                                next_etap = pair_start
                                msg = f"{msg}; {pair_msg}"
                            else:
                                msg = f"{msg}; {pair_msg}; brak automatycznego START (nierozpoznana para)"
                        else:
                            msg = f"{msg}; {pair_msg}"
                elif etap == 3:
                    next_etap = 4
                elif str(etap).startswith('3') and etap != 3:
                    # 31 -> 41, 32 -> 42, 310 -> 410, etc.
                    next_etap = int('4' + str(etap)[1:])
                elif etap == 5:
                    if next_action in ('new_point', 'oprozniamy_new_point'):
                        wants_new_point_after_empty = True
                    elif next_action in ('', 'end_today', 'oprozniamy_end_today'):
                        pass
                    else:
                        msg = f"{msg}; nieprawidłowy wybór po opróżnianiu"
            elif etap < 6:
                next_etap = etap + 1
            elif etap == 6:
                if next_action in ('new_point', 'oprozniamy_new_point'):
                    wants_new_point_after_empty = True
                elif next_action in ('', 'end_today', 'oprozniamy_end_today'):
                    pass
                else:
                    msg = f"{msg}; nieprawidłowy wybór po opróżnianiu"

            if next_etap is not None:
                next_ok, next_msg = ZasypEtapyService.start_etap(
                    plan_id=plan_id,
                    linia=linia,
                    data_planu=data_planu_date,
                    etap=next_etap,
                    user_login=session.get('login') or '',
                    szarza_nr=szarza_nr_raw,
                )
                if next_ok:
                    msg = f'{msg}; automatycznie uruchomiono etap {next_etap}'
                    audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap={next_etap}, linia={linia}, produkt={produkt}')
                    try:
                        _notify_laboratory_stage_start(
                            linia,
                            plan_id,
                            next_etap,
                            produkt,
                            szarza_nr=szarza_nr_raw,
                        )
                    except Exception:
                        current_app.logger.exception('Failed post-auto-start zasyp notification')

                    if wants_new_point_after_empty:
                        km_ok, km_msg = ZasypEtapyService.kolejny_pomiar(plan_id, linia, session.get('login') or '')
                        if km_ok:
                            new_szarza_nr = None
                            for token in str(km_msg).replace('#', ' ').split():
                                try:
                                    new_szarza_nr = int(token)
                                    break
                                except Exception:
                                    continue

                            if new_szarza_nr is not None:
                                st_ok, st_msg = ZasypEtapyService.start_etap(
                                    plan_id=plan_id,
                                    linia=linia,
                                    data_planu=data_planu_date,
                                    etap=1,
                                    user_login=session.get('login') or '',
                                    szarza_nr=new_szarza_nr,
                                )
                                if st_ok:
                                    msg = f"{msg}; {km_msg}; automatycznie uruchomiono Naważanie dla nowego punktu"
                                    audit_log('START etapu Zasyp', f'plan_id={plan_id}, etap=1, linia={linia}, produkt={produkt}, szarza_nr={new_szarza_nr}')
                                    try:
                                        _notify_laboratory_stage_start(
                                            linia,
                                            plan_id,
                                            1,
                                            produkt,
                                            szarza_nr=new_szarza_nr,
                                        )
                                    except Exception:
                                        current_app.logger.exception('Failed post-auto-start (new point) zasyp notification')

                                    if auto_szarza_enabled or wants_new_point_after_empty:
                                        # New-point flow must keep etap 1 start and szarza row in sync.
                                        param = ZasypEtapyService.get_parametry(plan_id, linia)
                                        kg_auto_new = param.get('wielkosc_szarzy_kg')
                                        try:
                                            kg_auto_new = float(kg_auto_new) if kg_auto_new is not None else None
                                        except Exception:
                                            kg_auto_new = None

                                        auto_conn = None
                                        try:
                                            auto_conn = get_db_connection()
                                            auto_cursor = auto_conn.cursor()
                                            table_szarze = get_table_name('szarze', linia)
                                            table_plan = get_table_name('plan_produkcji', linia)
                                            table_dosypki = get_table_name('dosypki', linia)

                                            # Fallback: when configured batch size is missing, reuse the latest batch weight for this plan.
                                            if not (kg_auto_new and kg_auto_new > 0):
                                                auto_cursor.execute(
                                                    f"SELECT waga FROM {table_szarze} WHERE plan_id=%s ORDER BY COALESCE(nr_szarzy, 0) DESC, data_dodania DESC, id DESC LIMIT 1",
                                                    (plan_id,),
                                                )
                                                row_last = auto_cursor.fetchone()
                                                try:
                                                    last_waga = row_last[0] if row_last else None
                                                except Exception:
                                                    last_waga = None
                                                try:
                                                    kg_auto_new = float(last_waga) if last_waga is not None else None
                                                except Exception:
                                                    kg_auto_new = None

                                            if kg_auto_new and kg_auto_new > 0:
                                                now = datetime.now()
                                                godzina = now.strftime('%H:%M:%S')
                                                pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

                                                auto_cursor.execute(
                                                    f"SELECT id FROM {table_szarze} WHERE plan_id=%s AND nr_szarzy=%s AND status='zarejestowana' LIMIT 1",
                                                    (plan_id, new_szarza_nr),
                                                )
                                                exists_row = auto_cursor.fetchone()

                                                if not exists_row:
                                                    _insert_szarza_compatible(
                                                        auto_cursor,
                                                        table_szarze,
                                                        plan_id=plan_id,
                                                        nr_szarzy=new_szarza_nr,
                                                        waga=kg_auto_new,
                                                        godzina=godzina,
                                                        data_dodania=now,
                                                        pracownik_id=pracownik_id,
                                                        produkt=produkt,
                                                        typ_produkcji=typ_produkcji,
                                                        data_planu=data_planu_date,
                                                    )

                                                    auto_cursor.execute(
                                                        f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                                                        f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                                                        f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                                                        f"WHERE id = %s",
                                                        (plan_id, plan_id, plan_id),
                                                    )

                                                    auto_conn.commit()
                                                    msg = f"{msg}; dodano zasyp #{new_szarza_nr} ({kg_auto_new:g} kg)"
                                                    audit_log(
                                                        'AUTO dodał zasyp',
                                                        f'zlecenie_id={plan_id}, produkt={produkt}, tonaz={kg_auto_new:g} kg, nr={new_szarza_nr}, linia={linia}, trigger=system:auto_po_stopie_etapu_5',
                                                    )
                                                    try:
                                                        from app.blueprints.routes_production import _mark_dosypki_updated
                                                        _mark_dosypki_updated(linia)
                                                    except Exception:
                                                        pass
                                                else:
                                                    msg = f"{msg}; zasyp #{new_szarza_nr} już istniał"
                                            else:
                                                msg = f"{msg}; tryb AUTO ZASYP aktywny, ale brak wielkości zasypu - nie dodano rekordu"
                                        except Exception as auto_new_err:
                                            try:
                                                if auto_conn:
                                                    auto_conn.rollback()
                                            except Exception:
                                                pass
                                            msg = f"{msg}; nie udało się dodać zasypu dla nowego punktu: {auto_new_err}"
                                        finally:
                                            try:
                                                if auto_conn:
                                                    auto_conn.close()
                                            except Exception:
                                                pass
                                else:
                                    msg = f"{msg}; {km_msg}; nie udało się uruchomić Naważania: {st_msg}"
                            else:
                                msg = f"{msg}; {km_msg}; nie rozpoznano numeru nowego zasypu"
                        else:
                            msg = f"{msg}; nie udało się utworzyć nowego punktu: {km_msg}"
                else:
                    next_msg_s = str(next_msg or '')
                    if linia == 'AGRO' and next_etap == 5 and 'nie może się rozpocząć przed zakończeniem' in next_msg_s.lower():
                        msg = f"{msg}; etap 5 nie został uruchomiony automatycznie (najpierw zakończ Mieszanie po dosypce)"
                    else:
                        msg = f'{msg}; etap {next_etap}: {next_msg}'

            if wants_new_point_after_empty and next_etap is None:
                km_ok, km_msg = ZasypEtapyService.kolejny_pomiar(plan_id, linia, session.get('login') or '')
                if km_ok:
                    msg = f"{msg}; {km_msg}"
                else:
                    msg = f"{msg}; nie udało się utworzyć nowego punktu: {km_msg}"

        _flash_zasyp_result(ok, msg)
        if ok:
            audit_log('STOP etapu Zasyp', f'plan_id={plan_id}, etap={etap}, linia={linia}, produkt={produkt}')
        return redirect(bezpieczny_powrot())
