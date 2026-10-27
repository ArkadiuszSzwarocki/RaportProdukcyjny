"""Central navigation for mail settings, preserving existing endpoint guards."""
from flask import abort, current_app, g, redirect, request, url_for
from app.decorators import login_required

EMAIL_TABS = {
    'konta': ('Konta SMTP i odbiorcy', 'admin.admin_ustawienia_email'),
    'magazyn': ('Magazyn i OSIP', 'admin.admin_ustawienia_email_magazyn'),
    'historia': ('Historia wysyłek', 'admin.admin_email_history_page'),
    'raporty': ('Wysyłki raportów', 'admin.admin_report_delivery_history'),
}
LEGACY_EMAIL_PAGES = {endpoint: tab for tab, (_, endpoint) in EMAIL_TABS.items()}
LEGACY_EMAIL_PAGES['osip.email_settings_view'] = 'magazyn'


def register_email_center_routes(admin_bp):
    @admin_bp.before_app_request
    def redirect_legacy_email_pages():
        tab = LEGACY_EMAIL_PAGES.get(request.endpoint)
        if request.method == 'GET' and tab:
            params = request.args.to_dict(flat=False)
            params['tab'] = tab
            return redirect(url_for('admin.email_center', **params))

    @admin_bp.route('/admin/ustawienia/poczta')
    @login_required
    def email_center():
        tab = request.args.get('tab', 'konta')
        if tab not in EMAIL_TABS:
            abort(404)
        g.email_center_tab = tab
        # Resolve at request time to keep security-hardening replacements and
        # their personal/system SMTP scope checks. Never call __wrapped__.
        return current_app.view_functions[EMAIL_TABS[tab][1]]()
