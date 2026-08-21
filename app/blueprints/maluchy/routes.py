from flask import render_template, request, session
from app.blueprints.maluchy.blueprint import maluchy_bp
from app.decorators import login_required
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
        # Fetch active plans on Zasyp from the last 7 days (or currently 'w toku')
        cur.execute(
            f"""
            SELECT id, produkt, tonaz, tonaz_rzeczywisty, DATE_FORMAT(data_planu, '%Y-%m-%d') AS data_planu_fmt, status, typ_produkcji
            FROM {table_plan} 
            WHERE sekcja = 'Zasyp' AND (is_deleted = 0 OR is_deleted IS NULL)
              AND status IN ('w toku', 'zaplanowane')
              AND (status = 'w toku' OR DATE(data_planu) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY))
            ORDER BY CASE status WHEN 'w toku' THEN 1 ELSE 2 END, data_planu DESC, id DESC
            """
        )
        active_plans = cur.fetchall()

        # Available KO stations KO01 - KO40
        ko_stations = [f"KO{i:02d}" for i in range(1, 41)]

        # Fetch active buckets
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

        selected_plan_id = request.args.get('plan_id')
        if selected_plan_id:
            try:
                selected_plan_id = int(selected_plan_id)
            except ValueError:
                selected_plan_id = None
        elif active_plans:
            selected_plan_id = active_plans[0]['id']

        return render_template(
            'maluchy/index.html',
            linia=linia,
            active_plans=active_plans,
            ko_stations=ko_stations,
            active_buckets=active_buckets,
            selected_plan_id=selected_plan_id,
        )
    finally:
        conn.close()
