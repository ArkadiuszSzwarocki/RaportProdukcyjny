from flask import render_template, request, jsonify, redirect, url_for, send_file, Response, make_response
import os
import re
from datetime import datetime
from ..base import magazyn_dostawy_bp
from app.services.osip_report_email_service import OsipReportEmailService

@magazyn_dostawy_bp.route('/drukuj-raport-dzienny')
def print_daily_report_center():
    """
    Centrum i interaktywne okno wyboru/drukowania raportów dziennych oraz poszczególnych załączników PZ i MM.
    Wywoływane m.in. bezpośrednio z linku w wiadomości e-mail.
    """
    date_str = request.args.get('data') or request.args.get('date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    service = OsipReportEmailService()
    activity_data = service.get_daily_warehouse_activity(date_str, central_only=True)

    # Przygotowanie listy dokumentów do wyboru
    deliveries = activity_data.get('deliveries', [])
    transfers = activity_data.get('transfers', [])

    return render_template(
        'magazyn_dostawy/drukuj_raport_dzienny.html',
        date_str=date_str,
        activity_data=activity_data,
        deliveries=deliveries,
        transfers=transfers,
        total_pallets=activity_data.get('total_pallets', 0),
        deliveries_count=activity_data.get('deliveries_count', 0),
        transfers_count=activity_data.get('transfers_count', 0)
    )

@magazyn_dostawy_bp.route('/raport-dzienny/podglad-druku')
def print_daily_report_stream():
    """
    Czysty widok HTML sformatowany do bezpośredniego wydruku A4 wybranych dokumentów (lub wszystkich naraz).
    """
    date_str = request.args.get('data') or request.args.get('date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    selected_raw = request.args.get('docs', 'all')
    auto_print = request.args.get('autoprint', '0') == '1'

    service = OsipReportEmailService()
    activity_data = service.get_daily_warehouse_activity(date_str, central_only=True)

    deliveries = activity_data.get('deliveries', [])
    transfers = activity_data.get('transfers', [])

    selected_keys = set(s.strip() for s in selected_raw.split(',') if s.strip())
    include_all = 'all' in selected_keys or not selected_keys
    include_summary = include_all or 'summary' in selected_keys

    # Filtrujemy dokumenty wg zaznaczenia
    filtered_deliveries = []
    for d in deliveries:
        key = f"PZ_{d.get('order_ref')}"
        if include_all or key in selected_keys or str(d.get('order_ref')) in selected_keys:
            filtered_deliveries.append(d)

    filtered_transfers = []
    for t in transfers:
        key = f"MM_{t.get('order_ref')}"
        if include_all or key in selected_keys or str(t.get('order_ref')) in selected_keys:
            filtered_transfers.append(t)

    # Budujemy przefiltrowane dane aktywności dla podsumowania zbiorczego (jeśli wybrano)
    filtered_activity = dict(activity_data)
    if not include_all:
        filtered_activity['deliveries'] = filtered_deliveries
        filtered_activity['transfers'] = filtered_transfers

    summary_pdf_html = ""
    if include_summary:
        # Generujemy HTML sekcji zbiorczej
        summary_pdf_html = service.build_daily_summary_report_html(date_str, filtered_activity)

    return render_template(
        'magazyn_dostawy/podglad_druku_raportu.html',
        date_str=date_str,
        include_summary=include_summary,
        summary_html=summary_pdf_html,
        deliveries=filtered_deliveries,
        transfers=filtered_transfers,
        auto_print=auto_print,
        service=service
    )

@magazyn_dostawy_bp.route('/raport-dzienny/pobierz-pdf')
def download_daily_report_pdf():
    """Generuje i pobiera plik PDF raportu zbiorczego."""
    date_str = request.args.get('data') or request.args.get('date')
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    service = OsipReportEmailService()
    activity_data = service.get_daily_warehouse_activity(date_str, central_only=True)
    pdf_path = service.generate_daily_summary_pdf(date_str, activity_data)

    if not pdf_path or not os.path.exists(pdf_path):
        return "Nie udało się wygenerować pliku PDF.", 500

    filename = f"Raport_Zbiorczy_Magazyn_Centralny_{date_str}.pdf"
    
    # Odczytujemy plik i usuwamy tymczasowy plik
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()

    try:
        os.remove(pdf_path)
    except Exception:
        pass

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
