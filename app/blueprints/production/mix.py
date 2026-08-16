from datetime import date
import math
import re

from flask import current_app, flash, redirect, render_template, request, session

from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required



def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        text = str(value).strip().replace(',', '.')
        if text == '':
            return default
        return int(float(text))
    except Exception:
        return default


def _load_workowanie_rozliczenie_context(cursor, data_planu, preferred_plan_id=None):
    """Load context for AGRO Workowanie settlement.
    
    Args:
        cursor: Database cursor
        data_planu: Date string (YYYY-MM-DD)
        preferred_plan_id: Optional plan ID to prioritize
    
    Returns:
        dict with keys: active_plan, packaging_items, bag_kg, palety_kg_wykonane, palety_count, estimated_bags
    """
    table_plan = get_table_name('plan_produkcji', 'AGRO')
    table_opak = get_table_name('magazyn_opakowania', 'AGRO')
    
    # 1. Find active Workowanie plan (in progress)
    if preferred_plan_id:
        cursor.execute(
            f"""
            SELECT id, produkt, data_planu, status, tonaz, tonaz_rzeczywisty
            FROM {table_plan}
            WHERE id = %s AND sekcja='Workowanie' AND status='w toku'
            LIMIT 1
            """,
            (preferred_plan_id,),
        )
    else:
        cursor.execute(
            f"""
            SELECT id, produkt, data_planu, status, tonaz, tonaz_rzeczywisty, typ_produkcji
            FROM {table_plan}
            WHERE data_planu = %s AND sekcja='Workowanie' AND status='w toku'
            ORDER BY kolejnosc ASC
            LIMIT 1
            """,
            (data_planu,),
        )
    active_plan = cursor.fetchone()
    
    # 2. Get packaging items (opakowania)
    cursor.execute(
        f"""
        SELECT id, nazwa, COALESCE(stan_magazynowy, 0) AS stan_magazynowy
        FROM {table_opak}
        WHERE linia = 'AGRO'
        ORDER BY nazwa ASC
        """
    )
    packaging_items = cursor.fetchall() or []
    
    # 3. Calculate produced pallets weight
    palety_kg_wykonane = 0
    palety_count = 0
    bag_kg = 20  # default
    
    if active_plan:
        plan_id = active_plan['id']
        
        # Get pallets for this plan
        cursor.execute(
            """
            SELECT COALESCE(SUM(waga_netto), 0) AS total_kg, COUNT(*) AS cnt
            FROM palety_agro
            WHERE plan_id = %s AND (is_deleted = 0 OR is_deleted IS NULL)
            """,
            (plan_id,),
        )
        pallet_stats = cursor.fetchone()
        if pallet_stats:
            palety_kg_wykonane = float(pallet_stats.get('total_kg') or 0)
            palety_count = int(pallet_stats.get('cnt') or 0)
        
        # Get bag weight from plan's typ_produkcji
        import re as _re
        typ_prod = str(active_plan.get('typ_produkcji') or '')
        m = _re.search(r'(\d+)\s*$', typ_prod)
        if m:
            bag_kg = float(m.group(1))
    
    # 4. Calculate estimated bags used
    estimated_bags = 0
    if bag_kg > 0 and palety_kg_wykonane > 0:
        estimated_bags = math.ceil(palety_kg_wykonane / bag_kg)
    
    return {
        'active_plan': active_plan,
        'packaging_items': packaging_items,
        'bag_kg': bag_kg,
        'palety_kg_wykonane': palety_kg_wykonane,
        'palety_count': palety_count,
        'estimated_bags': estimated_bags,
    }


def register_production_mix_routes(production_bp, bezpieczny_powrot):

    @production_bp.route('/agro/mix_rozliczenie', methods=['GET'])
    @login_required
    @roles_required('lider', 'admin')
    def agro_mix_rozliczenie_page():
        """Render modal content for MIX settlement (AGRO only)."""
        data_planu = request.args.get('data', str(date.today()))
        linia = 'AGRO'

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            table_plan = get_table_name('plan_produkcji', linia)

            # 1. Find the LAST finished Zasyp order
            cursor.execute(
                f"""
                SELECT id, produkt, data_planu
                FROM {table_plan}
                WHERE sekcja='Zasyp' AND status='zakonczone' AND data_planu <= %s
                ORDER BY real_stop DESC LIMIT 1
                """,
                (data_planu,),
            )
            last_plan = cursor.fetchone()

            # 2. Find the NEXT planned or running Zasyp order (current session)
            cursor.execute(
                f"""
                SELECT id, produkt, data_planu, status
                FROM {table_plan}
                WHERE sekcja='Zasyp' AND status IN ('zaplanowane','w toku') AND data_planu >= %s
                ORDER BY case when status='w toku' then 1 else 2 end, data_planu ASC, kolejnosc ASC LIMIT 1
                """,
                (data_planu,),
            )
            next_plan = cursor.fetchone()

            # If no next plan is found, we cannot create a MIX settlement.
            if not next_plan:
                return render_template(
                    'agro_mix_rozliczenie_error.html',
                    message="Nie można stworzyć MIX - brak zaplanowanego lub uruchomionego zlecenia Zasyp.",
                )

            # 3. Get history of MIX for today
            cursor.execute(
                """
                SELECT * FROM agro_mix_rozliczenie
                WHERE data_planu = %s
                ORDER BY created_at DESC
                """,
                (data_planu,),
            )
            history = cursor.fetchall()

            return render_template(
                'agro_mix_rozliczenie.html',
                last_plan=last_plan,
                next_plan=next_plan,
                history=history,
                data_planu=data_planu,
            )
        except Exception as e:
            current_app.logger.error('Error in agro_mix_rozliczenie_page: %s', e)
            return 'Błąd ładowania danych MIX', 500
        finally:
            conn.close()

    @production_bp.route('/agro/mix_rozliczenie/add', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin')
    def agro_mix_rozliczenie_add():
        """Add a MIX settlement record."""
        data_planu = request.form.get('data_planu', str(date.today()))
        poprz_id = request.form.get('poprz_id')
        nast_id = request.form.get('nast_id')
        kategoria = request.form.get('kategoria', 'DO_LNU')
        ilosc_workow = request.form.get('ilosc_workow')
        waga_kg = request.form.get('waga_kg')

        if not nast_id or not ilosc_workow or not waga_kg:
            flash('Błąd: Wszystkie wymagane pola muszą być wypełnione.', 'danger')
            return redirect(bezpieczny_powrot())

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO agro_mix_rozliczenie (data_planu, poprzednie_zlecenie_id, nastepne_zlecenie_id, kategoria, nazwa_mix, ilosc_workow, waga_kg, autor_login)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data_planu,
                    poprz_id,
                    nast_id,
                    kategoria,
                    kategoria.replace('_', ' '),
                    ilosc_workow,
                    waga_kg,
                    session.get('login'),
                ),
            )
            conn.commit()
            conn.close()
            flash('Rozliczenie MIX dodane pomyślnie.', 'success')
        except Exception as e:
            current_app.logger.error('Error adding MIX settlement: %s', e)
            flash(f'Błąd zapisu: {str(e)}', 'danger')

        return redirect(bezpieczny_powrot())

    @production_bp.route('/agro/mix_rozliczenie/print/<int:mix_id>')
    @login_required
    def agro_mix_rozliczenie_print(mix_id):
        """Printable view for a single MIX record."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT * FROM agro_mix_rozliczenie WHERE id=%s', (mix_id,))
            mix = cursor.fetchone()
            if not mix:
                return 'Nie znaleziono rekordu MIX', 404

            # Get plan info
            table_plan = get_table_name('plan_produkcji', 'AGRO')
            poprz_prod = '---'
            if mix['poprzednie_zlecenie_id']:
                cursor.execute(f'SELECT produkt FROM {table_plan} WHERE id=%s', (mix['poprzednie_zlecenie_id'],))
                row = cursor.fetchone()
                if row:
                    poprz_prod = row['produkt']

            nast_prod = '---'
            if mix['nastepne_zlecenie_id']:
                cursor.execute(f'SELECT produkt FROM {table_plan} WHERE id=%s', (mix['nastepne_zlecenie_id'],))
                row = cursor.fetchone()
                if row:
                    nast_prod = row['produkt']

            return render_template('agro_mix_print.html', mix=mix, poprz_prod=poprz_prod, nast_prod=nast_prod)
        finally:
            conn.close()

    @production_bp.route('/agro/workowanie_rozliczenie', methods=['GET'])
    @login_required
    @roles_required('lider', 'admin', 'zarzad')
    def agro_workowanie_rozliczenie_page():
        """Render settlement panel for AGRO Workowanie (packaging consumption)."""
        data_planu = request.args.get('data', str(date.today()))
        selected_plan_id = request.args.get('plan_id', type=int)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            ctx = _load_workowanie_rozliczenie_context(cursor, data_planu, preferred_plan_id=selected_plan_id)
            active_plan = ctx['active_plan']
            if not active_plan or str(active_plan.get('status') or '').lower() != 'w toku':
                return render_template(
                    'agro_mix_rozliczenie_error.html',
                    message='Brak uruchomionego zlecenia Workowanie AGRO do rozliczenia.',
                )

            table_opak = get_table_name('magazyn_opakowania', 'AGRO')
            cursor.execute(
                f"""
                SELECT r.*, COALESCE(o.nazwa, r.opakowanie_nazwa) AS opakowanie_biezace
                FROM agro_workowanie_rozliczenie r
                LEFT JOIN {table_opak} o ON o.id = r.opakowanie_id
                WHERE r.data_planu = %s
                ORDER BY r.created_at DESC
                """,
                (data_planu,),
            )
            history = cursor.fetchall()

            return render_template(
                'agro_workowanie_rozliczenie.html',
                data_planu=data_planu,
                active_plan=active_plan,
                packaging_items=ctx['packaging_items'],
                bag_kg=ctx['bag_kg'],
                palety_kg_wykonane=ctx['palety_kg_wykonane'],
                palety_count=ctx['palety_count'],
                estimated_bags=ctx['estimated_bags'],
                history=history,
            )
        except Exception as e:
            current_app.logger.error('Error in agro_workowanie_rozliczenie_page: %s', e)
            return 'Błąd ładowania rozliczenia Workowania AGRO', 500
        finally:
            conn.close()

    @production_bp.route('/agro/workowanie_rozliczenie/add', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin', 'zarzad')
    def agro_workowanie_rozliczenie_add():
        """Save AGRO Workowanie settlement and deduct packaging stock."""
        data_planu = request.form.get('data_planu', str(date.today()))
        plan_id = _safe_int(request.form.get('plan_id'))
        opakowanie_id = _safe_int(request.form.get('opakowanie_id'))
        wyprodukowano_szt = max(_safe_int(request.form.get('wyprodukowano_szt')), 0)
        szt_na_palecie = max(_safe_int(request.form.get('szt_na_palecie')), 0)

        if not plan_id or not opakowanie_id:
            flash('Błąd: Wybierz aktywne zlecenie i opakowanie.', 'danger')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            ctx = _load_workowanie_rozliczenie_context(cursor, data_planu, preferred_plan_id=plan_id)
            active_plan = ctx['active_plan']
            if not active_plan or int(active_plan['id']) != int(plan_id):
                flash('Błąd: Nie znaleziono uruchomionego zlecenia Workowanie AGRO.', 'danger')
                return redirect(bezpieczny_powrot())

            bag_kg = float(ctx['bag_kg'] or 20)
            palety_kg_wykonane = float(ctx['palety_kg_wykonane'] or 0)
            zuzyte_worki = float(ctx['estimated_bags'] or 0)

            table_opak = get_table_name('magazyn_opakowania', 'AGRO')
            cursor.execute(
                f"""
                SELECT id, nazwa, COALESCE(stan_magazynowy, 0) AS stan_magazynowy
                FROM {table_opak}
                WHERE id = %s
                LIMIT 1
                """,
                (opakowanie_id,),
            )
            opakowanie = cursor.fetchone()
            if not opakowanie:
                flash('Błąd: Wybrane opakowanie nie istnieje.', 'danger')
                return redirect(bezpieczny_powrot())

            stan_przed = float(opakowanie.get('stan_magazynowy') or 0)
            stan_po = stan_przed - zuzyte_worki

            cursor.execute(
                f"UPDATE {table_opak} SET stan_magazynowy = %s WHERE id = %s",
                (stan_po, opakowanie_id),
            )

            cursor.execute(
                """
                INSERT INTO agro_workowanie_rozliczenie (
                    plan_id,
                    data_planu,
                    produkt,
                    opakowanie_id,
                    opakowanie_nazwa,
                    stan_przed,
                    wyprodukowano_szt,
                    szt_na_palecie,
                    kg_na_worek,
                    palety_kg_wykonane,
                    zuzyte_worki,
                    stan_po,
                    autor_login
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    active_plan['id'],
                    active_plan.get('data_planu') or data_planu,
                    active_plan.get('produkt') or '',
                    opakowanie_id,
                    opakowanie.get('nazwa') or '',
                    stan_przed,
                    wyprodukowano_szt,
                    szt_na_palecie,
                    bag_kg,
                    palety_kg_wykonane,
                    zuzyte_worki,
                    stan_po,
                    session.get('login'),
                ),
            )

            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {table_ruch}
                    (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                    """,
                    (
                        opakowanie_id,
                        'ROZLICZENIE_WORKOWANIE',
                        -zuzyte_worki,
                        stan_po,
                        'POTWIERDZONE',
                        session.get('login'),
                        f"Rozliczenie Workowania AGRO plan #{active_plan['id']} ({active_plan.get('produkt') or 'bez nazwy'})",
                    ),
                )
            except Exception:
                pass

            conn.commit()
            flash(
                f"Rozliczenie zapisane. Zużyto {zuzyte_worki:.0f} worków, stan opakowań: {stan_przed:.0f} -> {stan_po:.0f} szt.",
                'success',
            )
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.error('Error in agro_workowanie_rozliczenie_add: %s', e)
            flash(f'Błąd zapisu rozliczenia: {str(e)}', 'danger')
        finally:
            conn.close()

        return redirect(bezpieczny_powrot())

    @production_bp.route('/agro/mix/inventory', methods=['GET'])
    @login_required
    @roles_required('lider', 'admin')
    def agro_mix_inventory():
        """List available MIXes for consumption (Ajax popup)."""
        selected_plan_id = request.args.get('selected_plan_id', type=int)
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Fetch available MIXes along with their origin product
            table_plan = get_table_name('plan_produkcji', 'AGRO')
            cursor.execute(
                f"""
                SELECT m.*, p.produkt as origin_product
                FROM agro_mix_rozliczenie m
                LEFT JOIN {table_plan} p ON m.poprzednie_zlecenie_id = p.id
                WHERE m.status='DOSTEPNY'
                ORDER BY m.created_at DESC
                """
            )
            available_mixes = cursor.fetchall()

            # Only fetch ACTIVE (running) orders for ZASYP stage
            cursor.execute(
                f"SELECT id, produkt, nazwa_zlecenia FROM {table_plan} WHERE status = 'w toku' AND sekcja = 'Zasyp' ORDER BY kolejnosc ASC"
            )
            active_plans = cursor.fetchall()

            conn.close()
            return render_template(
                'agro_mix_inventory.html',
                mixes=available_mixes,
                plans=active_plans,
                selected_id=selected_plan_id,
            )
        except Exception as e:
            current_app.logger.error('Error loading MIX inventory: %s', e)
            return 'Błąd ładowania zasobnika', 500

    @production_bp.route('/agro/mix_consume', methods=['POST'])
    @login_required
    @roles_required('lider', 'admin')
    def agro_mix_consume():
        """Consume an available MIX into a Zasyp plan."""
        mix_id = request.form.get('mix_id')
        plan_id = request.form.get('plan_id')

        if not mix_id or not plan_id:
            flash('Błąd: Nieprawidłowe dane konsumpcji MIX', 'danger')
            return redirect(bezpieczny_powrot())

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # 1. Fetch MIX weight
            cursor.execute(
                "SELECT waga_kg, kategoria FROM agro_mix_rozliczenie WHERE id=%s AND status='DOSTEPNY'",
                (mix_id,),
            )
            mix = cursor.fetchone()
            if not mix:
                conn.close()
                flash('Błąd: Ten MIX nie jest już dostępny', 'danger')
                return redirect(bezpieczny_powrot())

            # 2. Update MIX status and consumption timestamp
            cursor.execute(
                """
                UPDATE agro_mix_rozliczenie
                SET status='ZUZYTY', zuzyte_w_id=%s, zuzyte_kiedy=NOW()
                WHERE id=%s
                """,
                (plan_id, mix_id),
            )

            # 3. INCREASE Zasyp actual tonnage
            table_plan = get_table_name('plan_produkcji', 'AGRO')
            cursor.execute(
                f"""
                UPDATE {table_plan}
                SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s
                WHERE id=%s
                """,
                (mix['waga_kg'], plan_id),
            )

            conn.commit()
            conn.close()
            flash(f"Dodano {mix['waga_kg']} kg MIXu ({mix['kategoria'].replace('_',' ')}) do zlecenia.", 'success')
        except Exception as e:
            current_app.logger.error('Error consuming MIX: %s', e)
            flash(f'Błąd: {str(e)}', 'danger')

        return redirect(bezpieczny_powrot())
