from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_TEMPLATE = ROOT / 'templates' / 'dashboard.html'
CONFIG_JS = ROOT / 'static' / 'js' / 'dashboard' / 'config.js'
DASHBOARD_JS_DIR = ROOT / 'static' / 'js' / 'dashboard'
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