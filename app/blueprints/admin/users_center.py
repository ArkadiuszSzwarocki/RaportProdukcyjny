"""One entry point for user administration; existing view guards stay authoritative."""
from flask import abort, current_app, g, redirect, request, url_for
from app.decorators import login_required

USER_TABS = {
    'zespol': ('Pracownicy i konta', 'admin.admin_ustawienia_zespol'),
    'uprawnienia': ('Role i uprawnienia', 'admin.admin_ustawienia_roles'),
    'podglad-rol': ('Przegląd ról', 'admin.admin_ustawienia_roles_users'),
    'struktura': ('Struktura organizacyjna', 'struktura.widok_struktury'),
    'sesje': ('Zalogowani i sesje', 'admin.admin_ustawienia_zalogowani'),
}
LEGACY_USER_PAGES = {endpoint: tab for tab, (_, endpoint) in USER_TABS.items()}
LEGACY_USER_PAGES.update({
    'admin.admin_ustawienia_uzytkownicy': 'zespol',
    'admin.admin_ustawienia_pracownicy': 'zespol',
    'admin.admin_master_permissions': 'uprawnienia',
})


def register_users_center_routes(admin_bp):
    @admin_bp.before_app_request
    def redirect_legacy_user_pages():
        # Only navigation GETs move. All existing mutation/API endpoints keep
        # their original guards, payloads and behavior.
        tab = LEGACY_USER_PAGES.get(request.endpoint)
        if request.method == 'GET' and tab:
            params = request.args.to_dict(flat=False)
            params['tab'] = tab
            return redirect(url_for('admin.users_center', **params))

    @admin_bp.route('/admin/uzytkownicy')
    @login_required
    def users_center():
        tab = request.args.get('tab', 'zespol')
        if tab not in USER_TABS:
            abort(404)
        g.users_center_tab = tab
        # Dispatch the DECORATED view, never its __wrapped__ function. In
        # particular roles remain masteradmin-only, also for direct tab URLs.
        return current_app.view_functions[USER_TABS[tab][1]]()
