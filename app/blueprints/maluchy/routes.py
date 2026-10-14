from flask import render_template, request, session, make_response
from app.blueprints.maluchy.blueprint import maluchy_bp
from app.decorators import login_required
from app.blueprints.maluchy.permissions import can_emergency_dump_bucket
from app.db import get_db_connection, get_table_name
from app.services.bucket_maluch_service import BucketMaluchService
from app.repositories.bucket_maluch_repository import BucketMaluchRepository


@maluchy_bp.route('/', methods=['GET'])
@maluchy_bp.route('/nawazanie', methods=['GET'])
@login_required
def index():
    """Main touch / scanner interface for weighing micro-ingredients into buckets."""
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    table_plan = get_table_name('plan_produkcji', linia)
    
    conn = get_db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        # Fetch active plans on Zasyp: strictly 'w toku', 'zaplanowane', 'zawieszone' from the last 7 days
        cur.execute(
            f"""
            SELECT id, produkt, tonaz, tonaz_rzeczywisty, DATE_FORMAT(data_planu, '%Y-%m-%d') AS data_planu_fmt, status, typ_produkcji
            FROM {table_plan} 
            WHERE sekcja = 'Zasyp' AND (is_deleted = 0 OR is_deleted IS NULL)
              AND status IN ('w toku', 'zaplanowane', 'zawieszone')
              AND (status IN ('w toku', 'zawieszone') OR DATE(data_planu) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY))
            ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zawieszone' THEN 2 ELSE 3 END, data_planu DESC, id DESC
            """
        )
        active_plans = cur.fetchall()

        # Available KO stations KO01 - KO40
        station_materials = BucketMaluchService.get_assigned_station_materials(linia)
        ko_stations = [f"KO{i:02d}" for i in range(1, 41) if f"KO{i:02d}" in station_materials]

        # Fetch active buckets for current line
        cur.execute(
            """
            SELECT * FROM wiaderka_maluchy 
            WHERE linia = %s AND status IN ('w_trakcie_nawazania', 'skompletowane')
            ORDER BY id DESC
            """,
            (linia.upper(),)
        )
        active_buckets = cur.fetchall()
        for b in active_buckets:
            b['pozycje'] = BucketMaluchRepository.get_items_for_bucket(b['id'])

        # Bucket counts per line for line-switcher badges
        cur.execute("SELECT linia, count(*) as cnt FROM wiaderka_maluchy GROUP BY linia")
        line_counts = {r['linia'].upper(): r['cnt'] for r in cur.fetchall()}
        agro_bucket_count = line_counts.get('AGRO', 0)
        psd_bucket_count = line_counts.get('PSD', 0)

        selected_plan_id = request.args.get('plan_id')
        if selected_plan_id:
            try:
                selected_plan_id = int(selected_plan_id)
            except ValueError:
                selected_plan_id = None
        elif active_plans:
            # Auto-select plan with most recent bucket on this line if available
            cur.execute(
                "SELECT plan_id FROM wiaderka_maluchy WHERE linia = %s ORDER BY id DESC LIMIT 1",
                (linia.upper(),)
            )
            latest_b = cur.fetchone()
            if latest_b and any(p['id'] == latest_b['plan_id'] for p in active_plans):
                selected_plan_id = latest_b['plan_id']
            else:
                selected_plan_id = active_plans[0]['id']

        return render_template(
            'maluchy/index.html',
            linia=linia,
            active_plans=active_plans,
            ko_stations=ko_stations,
            station_materials=station_materials,
            active_buckets=active_buckets,
            selected_plan_id=selected_plan_id,
            agro_bucket_count=agro_bucket_count,
            psd_bucket_count=psd_bucket_count,
        )
    finally:
        conn.close()


@maluchy_bp.route('/zasyp_wiaderka/<int:plan_id>/<int:szarza_id>', methods=['GET'])
@login_required
def zasyp_wiaderka_page(plan_id: int, szarza_id: int):
    """Render sliding popup with list of buckets for this production plan with emergency dump action."""
    linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
    summary = BucketMaluchService.get_plan_maluchy_summary(plan_id, linia)

    # The API and view share the same supervisor authorization.

    can_emergency_dump = can_emergency_dump_bucket()

    table_plan = get_table_name('plan_produkcji', linia)
    table_szarze = get_table_name('szarze', linia)
    conn = get_db_connection()
    plan_info = None
    szarza_info = None
    szarze_list = []
    default_free_szarza_id = szarza_id
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT id, produkt, nr_receptury, tonaz FROM {table_plan} WHERE id = %s", (plan_id,))
        plan_info = cur.fetchone()
        if not plan_info:
            alt_linia = 'AGRO' if linia.upper() == 'PSD' else 'PSD'
            alt_table_plan = get_table_name('plan_produkcji', alt_linia)
            alt_table_szarze = get_table_name('szarze', alt_linia)
            cur.execute(f"SELECT id, produkt, nr_receptury, tonaz FROM {alt_table_plan} WHERE id = %s", (plan_id,))
            alt_plan = cur.fetchone()
            if alt_plan:
                plan_info = alt_plan
                linia = alt_linia
                table_szarze = alt_table_szarze

        cur.execute(f"SELECT id, nr_szarzy, waga FROM {table_szarze} WHERE id = %s", (szarza_id,))
        szarza_info = cur.fetchone()

        # Query all szarze for this plan with assigned dumped bucket if any
        cur.execute(
            f"""
            SELECT s.id, s.nr_szarzy, s.waga, s.godzina,
                   (SELECT w.id FROM wiaderka_maluchy w WHERE w.szarza_id = s.id AND w.plan_id = s.plan_id AND UPPER(w.linia) = '{'AGRO' if table_szarze.endswith('_agro') else 'PSD'}' AND w.status = 'wrzucone_do_mieszalnika' LIMIT 1) AS bucket_id,
                   (SELECT w.kod_wiadra FROM wiaderka_maluchy w WHERE w.szarza_id = s.id AND w.plan_id = s.plan_id AND UPPER(w.linia) = '{'AGRO' if table_szarze.endswith('_agro') else 'PSD'}' AND w.status = 'wrzucone_do_mieszalnika' LIMIT 1) AS bucket_code
            FROM {table_szarze} s
            WHERE s.plan_id = %s
            ORDER BY s.nr_szarzy ASC, s.id ASC
            """,
            (plan_id,)
        )
        szarze_list = cur.fetchall() or []

        # Find first free szarza if current active szarza already has an assigned bucket
        current_occupied = any(sz['id'] == szarza_id and sz.get('bucket_id') for sz in szarze_list)
        if current_occupied:
            first_free = next((sz['id'] for sz in szarze_list if not sz.get('bucket_id')), None)
            if first_free:
                default_free_szarza_id = first_free
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    response = make_response(render_template(
        'maluchy/popups/zasyp_wiaderka.html',
        plan_id=plan_id,
        szarza_id=szarza_id,
        linia=linia,
        summary=summary,
        can_emergency_dump=can_emergency_dump,
        plan_info=plan_info,
        szarza_info=szarza_info,
        szarze_list=szarze_list,
        default_free_szarza_id=default_free_szarza_id,
    ))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
