from datetime import date

from flask import current_app, flash, redirect, render_template, request, session

from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required


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
