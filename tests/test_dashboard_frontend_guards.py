from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_TEMPLATE = ROOT / 'templates' / 'dashboard.html'
ORDER_CARD_TEMPLATE = ROOT / 'templates' / 'dashboard' / '_dashboard_order_card.html'
LAYOUT_TEMPLATE = ROOT / 'templates' / 'layout.html'
DOSYPKI_LIST_TEMPLATE = ROOT / 'templates' / 'dosypki_list.html'
CSS_DASHBOARD = ROOT / 'static' / 'css' / 'dashboard.css'
CONFIG_JS = ROOT / 'static' / 'js' / 'dashboard' / 'config.js'
CARD_ACTIONS_JS = ROOT / 'static' / 'js' / 'dashboard' / 'card-actions.js'
DASHBOARD_JS_DIR = ROOT / 'static' / 'js' / 'dashboard'
DOSYPKI_JS = ROOT / 'static' / 'js' / 'dosypki.js'
GLOBAL_SCRIPTS_JS = ROOT / 'static' / 'scripts.js'
CACHE_BUST_SUFFIX = '&dashboard_refactor=4'
EXPECTED_DASHBOARD_ASSETS = [
    'js/dashboard/scheduler.js',
    'js/dashboard/toasts.js',
    'js/dashboard/config.js',
    'js/dashboard/card-actions.js',
    'js/dashboard/agro-banners.js',
    'js/dashboard/polling.js',
    'js/dashboard/ui.js',
    'js/dashboard/kgph.js',
    'js/dashboard/etapy.js',
    'js/dashboard/page-helpers.js',
    'js/dashboard/bootstrap.js',
]


def test_dashboard_template_has_no_inline_event_handlers_or_inline_scripts():
    content = DASHBOARD_TEMPLATE.read_text(encoding='utf-8')

    assert not re.search(r'\son[a-z]+\s*=', content, flags=re.IGNORECASE)
    assert not re.search(r'<script(?![^>]*\bsrc=)', content, flags=re.IGNORECASE)


def test_dashboard_config_uses_single_module_object_state():
    content = CONFIG_JS.read_text(encoding='utf-8')

    assert 'global.dashboardConfig = {' in content
    assert 'state: state' in content
    assert 'getState: getState' in content
    assert 'urls:' not in content

    forbidden_globals = [
        'global._urls',
        'global._currentRole',
        'global._linia',
        'global._isAgroZasypOperator',
        'global._isAgroDosypkiObserver',
        'global._isAgroLaborant',
    ]
    for symbol in forbidden_globals:
        assert symbol not in content


def test_dashboard_modules_do_not_restore_legacy_window_exports():
    forbidden_globals = [
        'global.editPalet =',
        'global.deletePalet =',
        'global.deletePlan =',
        'global.dashboardTonazEdit =',
        'global.handleZasypStartForm =',
        'global.handleEtapStopForm =',
        'global.toggleManualEtapForm =',
        'global.applyNowMaxToTimeInputs =',
        'global.startEtapyTimers =',
        'global._szarzaModalConfirm =',
        'global._szarzaModalCancel =',
        'global.openStopDecisionModal =',
        'global._closeStopDecisionModal =',
        'global._stopDecisionChoose =',
        'global.openRaportPalet =',
        'global.getAutoSzarzaMode =',
        'global.applyAutoSzarzaMode =',
        'global.toggleAutoSzarzaMode =',
        'global.openModal =',
        'global.closeAllModals =',
        'global.formatElapsed =',
        'global.updatePaletaTimers =',
        'global.initUpdatePaletaTimers =',
        'global.toggleDetails =',
        'global._stopAgroBannerMedia =',
        'global._isAgroBannerLocked =',
        'global._syncDosypkiBadgesAndFallbackBanner =',
        'global.sendZwolnienieMieszalnika =',
        'global.closeZwolnienieBanner =',
        'global.showZwolnienieBanner =',
        'global.showZasypStartBanner =',
        'global.showZasypMieszanieStartBanner =',
        'global.showZasypDosypkaAddedBanner =',
    ]

    for path in DASHBOARD_JS_DIR.glob('*.js'):
        content = path.read_text(encoding='utf-8')
        for symbol in forbidden_globals:
            assert symbol not in content, f'{symbol} found in {path.name}'


def test_dashboard_template_keeps_cache_busting_suffix_for_dashboard_assets():
    content = DASHBOARD_TEMPLATE.read_text(encoding='utf-8')

    for asset in EXPECTED_DASHBOARD_ASSETS:
        assert asset in content, f'missing dashboard asset include: {asset}'

    matches = re.findall(r'js/dashboard/[^\"]+dashboard_refactor=\d+', content)
    assert len(matches) == len(EXPECTED_DASHBOARD_ASSETS)
    assert all(CACHE_BUST_SUFFIX in match for match in matches)


def test_sidebar_time_report_is_only_exposed_for_agro_and_laboratory_roles():
    content = LAYOUT_TEMPLATE.read_text(encoding='utf-8')

    assert "url_for('production.zasyp_etapy_podsumowanie', linia='PSD')" not in content
    assert "{% if role in ['lider', 'admin', 'zarzad', 'planista', 'laborant', 'laboratorium'] %}" in content


def test_laborant_has_dosypki_action_in_order_tile():
    content = ORDER_CARD_TEMPLATE.read_text(encoding='utf-8')

    assert "role_lc in ['masteradmin', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad', 'laborant', 'laboratorium']" in content


def test_dashboard_card_actions_skips_prevented_submit_events():
    content = CARD_ACTIONS_JS.read_text(encoding='utf-8')

    assert 'if (event.defaultPrevented) {' in content


def test_quick_popup_submit_handler_respects_prevented_event():
    content = GLOBAL_SCRIPTS_JS.read_text(encoding='utf-8')

    assert 'if (evt.defaultPrevented) {' in content


def test_dosypki_fragment_uses_fragment_role_context_instead_of_removed_legacy_globals():
    template_content = DOSYPKI_LIST_TEMPLATE.read_text(encoding='utf-8')
    script_content = DOSYPKI_JS.read_text(encoding='utf-8')

    assert 'data-current-role="{{ rola or \"\" }}"' in template_content or "data-current-role=\"{{ rola or '' }}\"" in template_content
    assert 'window._currentRole' not in script_content
    assert 'window._linia' not in script_content
    assert 'getCurrentRole' in script_content
    assert 'getCurrentLinia' in script_content


def test_agro_open_stage_hint_is_bound_to_control_point_header_not_global_banner():
    content = DASHBOARD_TEMPLATE.read_text(encoding='utf-8')

    assert 'agro-open-etap-alert-wrap' not in content
    assert 'agro-session-running-hint' in content


def test_batch_lists_wrap_dosypki_inside_tiles():
    content = CSS_DASHBOARD.read_text(encoding='utf-8')

    assert '.active-order-szarze-dosypki {' in content
    assert 'overflow-wrap: anywhere;' in content
    assert '.active-order-szarze-actions {' in content
    assert '.szarza-dosypki-item' in content


def test_dosypki_are_rendered_below_batch_not_in_side_column():
    content = CSS_DASHBOARD.read_text(encoding='utf-8')

    assert 'grid-template-columns: minmax(280px, 1.2fr) minmax(240px, 0.8fr);' not in content
    assert '.szarza-row-layout {' in content
    assert 'display: block;' in content