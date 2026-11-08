"""Central navigation for mail settings, preserving existing endpoint guards."""
from flask import abort, current_app, g, redirect, render_template, request, url_for
from app.decorators import login_required, roles_required

EMAIL_TABS = {
    'mapa': ('Konta i wysyłki', 'admin.mail_routing'),
    'dzienne': ('Raporty dzienne', 'admin.daily_mail_reports'),
    'stany': ('Stany minimalne opakowań', 'admin.packaging_alerts'),
    'konta': ('Konta SMTP i odbiorcy', 'admin.admin_ustawienia_email'),
    'magazyn': ('Magazyn i OSIP', 'admin.admin_ustawienia_email_magazyn'),
    'historia': ('Historia wysyłek', 'admin.admin_email_history_page'),
    'raporty': ('Wysyłki raportów', 'admin.admin_report_delivery_history'),
}
LEGACY_EMAIL_PAGES = {endpoint: tab for tab, (_, endpoint) in EMAIL_TABS.items()}
LEGACY_EMAIL_PAGES['osip.email_settings_view'] = 'magazyn'


def register_email_center_routes(admin_bp):
    @admin_bp.route('/admin/ustawienia/poczta/konta-wysylki')
    @login_required
    @roles_required('admin', 'masteradmin')
    def mail_routing():
        from app.services.mail_routing_overview import load_mail_routing
        return render_template('admin/mail_routing.html', routing=load_mail_routing())

    @admin_bp.route('/admin/ustawienia/poczta/konto/<int:target_user_id>')
    @login_required
    @roles_required('admin', 'masteradmin')
    def email_account_edit(target_user_id):
        from app.core.admin_security_hardening import secure_email_settings_page
        return secure_email_settings_page()

    @admin_bp.route('/admin/ustawienia/poczta/dzienne')
    @login_required
    @roles_required('admin','masteradmin','zarzad','lider','planista')
    def daily_mail_reports():
        from datetime import date, datetime
        from zoneinfo import ZoneInfo
        from app.services.auto_report_service import AutoReportService
        day = request.args.get('data') or datetime.now(ZoneInfo('Europe/Warsaw')).date().isoformat()
        try:
            date.fromisoformat(day)
        except ValueError:
            abort(400)
        line = request.args.get('linia','AGRO').upper()
        if line not in ('AGRO','PSD'):
            abort(400)
        return render_template('admin/daily_mail_reports.html', day=day, line=line,
                               schedule=AutoReportService.get_schedule('AGRO',day))

    @admin_bp.before_app_request
    def redirect_legacy_email_pages():
        tab = LEGACY_EMAIL_PAGES.get(request.endpoint)
        if request.path in ('/ustawienia-osobiste/email', '/moje_konto_email'):
            return None
        if request.method == 'GET' and tab:
            params = request.args.to_dict(flat=False)
            params['tab'] = tab
            return redirect(url_for('admin.email_center', **params))

    @admin_bp.route('/admin/ustawienia/poczta')
    @login_required
    def email_center():
        tab = request.args.get('tab', 'start')
        if tab == 'start':
            g.email_center_tab = 'start'
            return render_template('admin/email_center_overview.html')
        if tab not in EMAIL_TABS:
            abort(404)
        g.email_center_tab = tab
        # Resolve at request time to keep security-hardening replacements and
        # their personal/system SMTP scope checks. Never call __wrapped__.
        return current_app.view_functions[EMAIL_TABS[tab][1]]()
