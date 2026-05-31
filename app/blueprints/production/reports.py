from flask import render_template, request
from app.decorators import login_required
from app.services.zasypy_raport_service import ZasypyRaportService
from datetime import date, timedelta

def register_production_reports_routes(bp):
    @bp.route('/raporty/zasypy-dosypki')
    @login_required
    def raport_zasypy_dosypki():
        linia = request.args.get('linia', 'WSZYSTKO')
        
        # Default date range: last 7 days
        today = date.today()
        default_start = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        default_end = today.strftime('%Y-%m-%d')
        
        start_date = request.args.get('start_date', default_start)
        end_date = request.args.get('end_date', default_end)
        
        raport_data = ZasypyRaportService.get_zasypy_report(start_date, end_date, linia)
        
        return render_template(
            'reports/raport_zasypow.html',
            raport_data=raport_data,
            start_date=start_date,
            end_date=end_date,
            linia=linia
        )
