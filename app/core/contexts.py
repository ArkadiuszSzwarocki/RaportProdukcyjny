"""
Context processors for Jinja templates.

These inject helper functions and variables into all templates.
"""

import os
import json
import time
from flask import session, request, current_app

# Global translation cache
_translations_cache = {}


def _normalize_role_name(raw_role):
    """Normalize known role variants to canonical names."""
    role = str(raw_role or '').lower().strip()
    role_aliases = {
        'master admin': 'masteradmin',
        'master_admin': 'masteradmin',
        'master-admin': 'masteradmin',
        'laboratorium': 'laborant',
    }
    return role_aliases.get(role, role)


def inject_static_version():
    """Inject cache-busting static file version based on CSS modification time."""
    try:
        # Use the latest modification time among key static assets (style + scripts)
        candidates = [
            os.path.join(current_app.root_path, 'static', 'css', 'style.css'),
            os.path.join(current_app.root_path, 'static', 'css', 'sidebar.css'),
            os.path.join(current_app.root_path, 'static', 'css', 'inline-styles.css'),
            os.path.join(current_app.root_path, 'static', 'css', 'dashboard.css'),
            os.path.join(current_app.root_path, 'static', 'scripts.js'),
            os.path.join(current_app.root_path, 'static', 'js', 'sidebar.js'),
            os.path.join(current_app.root_path, 'static', 'js', 'magazyny_nowe.js'),
            os.path.join(current_app.root_path, 'static', 'js', 'agro_warehouse.js'),
        ]
        mtimes = []
        for p in candidates:
            try:
                mtimes.append(int(os.path.getmtime(p)))
            except Exception:
                continue
        if mtimes:
            v = max(mtimes)
        else:
            v = int(time.time())
    except Exception:
        v = int(time.time())
    return dict(static_version=v)


def inject_role_permissions():
    """Inject role-based access control functions into templates."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
    page_aliases = {
        'podsumowanie_zasypow': 'podsumowanie_szarz',
    }

    def _resolve_page_key(page, perms):
        if page in perms:
            return page
        legacy = page_aliases.get(page)
        if legacy and legacy in perms:
            return legacy
        for new_key, legacy_key in page_aliases.items():
            if page == legacy_key and new_key in perms:
                return new_key
        return page

    def role_has_access(page):
        try:
            r = _normalize_role_name(session.get('rola'))
            # 0. MasterAdmin Bypasses EVERYTHING - has access to every single page/API
            if r == 'masteradmin':
                return True

            # If the page being checked is 'bufor', resolve it dynamically based on hall context
            if page == 'bufor':
                from flask import request
                linia = (request.args.get('linia') or session.get('selected_hall_view') or session.get('grupa') or 'PSD').upper()
                if linia not in ['PSD', 'AGRO']:
                    linia = 'PSD'
                page = f"{linia.lower()}.bufor"

            # Read config every time (no caching)
            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception as e:
                current_app.logger.error(f"[DEBUG configs] Failed to load role_permissions.json from {cfg_path}: {e}")
                perms = {}
            
            # Normalize common role name variants/synonyms (support numeric roles from DB)
            if r.isdigit():
                try:
                    idx = int(r)
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    if 0 <= idx < len(roles_order):
                        r = roles_order[idx]
                except Exception:
                    pass
            if r in ['operator', 'stepnpio']:
                r = 'pracownik'
            # Do not log debug info here to avoid noisy logs during template rendering
            
            # IMPORTANT: if config exists and contains pages, use ONLY config
            # (no fallback to hardcoded rules)
            if perms and len(perms) > 0:
                # Config has data - check if page is in config
                page_key = _resolve_page_key(page, perms)
                # Page in config -> check role access
                page_perms = perms.get(page_key)
                if page_perms is None:
                    # Check for dynamic sub-keys (e.g. 'ustawienia.system' when page is 'ustawienia')
                    sub_keys = [k for k in perms if k.startswith(f"{page_key}.")]
                    if sub_keys:
                        has_sub_access = False
                        for sk in sub_keys:
                            sk_perms = perms.get(sk, {})
                            role_cfg = sk_perms.get(r, {})
                            if bool(role_cfg.get('access', False)):
                                has_sub_access = True
                                break
                        current_app.logger.info(f"role_has_access(parent_page={page}, role={r}) resolved via sub_keys to {has_sub_access}")
                        return has_sub_access
                    
                    current_app.logger.warning(f"role_has_access: page_key '{page_key}' not found in perms (original page: '{page}')")
                    return False
                
                role_cfg = page_perms.get(r, {})
                result = bool(role_cfg.get('access', False))
                current_app.logger.info(f"role_has_access(page={page}, key={page_key}, role={r}) -> {result} (cfg: {role_cfg})")
                return result
            
            # Config empty - use fallback
            if page == 'dashboard':
                return r in ['lider', 'admin']
            if page in ('zasyp', 'workowanie', 'magazyn'):
                return r in ['produkcja', 'lider', 'admin', 'zarzad', 'pracownik']
            if page == 'jakosc':
                return r in ['laborant', 'lider', 'admin', 'zarzad', 'produkcja', 'planista']
            if page == 'wyniki':
                return True
            if page == 'awarie':
                return r in ['dur', 'admin', 'zarzad']
            if page == 'plan':
                return r not in ['pracownik', 'magazynier']
            if page == 'moje_godziny':
                return True
            if page == 'ustawienia':
                return r == 'admin'
            # unknown page key -> allow by default
            return True
        except Exception as e:
            current_app.logger.exception(f'role_has_access({page}) error: {e}')
            return False

    def role_is_readonly(page):
        try:
            r = _normalize_role_name(session.get('rola'))
            if r == 'masteradmin':
                return False

            # Read config every time (no caching)
            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception:
                perms = {}
            
            # Normalize common role name variants/synonyms
            if r.isdigit():
                try:
                    idx = int(r)
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    if 0 <= idx < len(roles_order):
                        r = roles_order[idx]
                except Exception:
                    pass
            if r in ['operator', 'stepnpio']:
                r = 'pracownik'
            if not perms:
                # default: no readonly restrictions
                return False
            page_key = _resolve_page_key(page, perms)
            page_perms = perms.get(page_key)
            if page_perms is None:
                return False
            return bool(page_perms.get(r, {}).get('readonly', False))
        except Exception:
            return False

    # Pre-calculate master and admin access for templates
    curr_role = _normalize_role_name(session.get('rola'))
    has_master_access = (curr_role == 'masteradmin')
    has_admin_access = (curr_role in ['admin', 'masteradmin'])

    return dict(
        role_has_access=role_has_access, 
        role_is_readonly=role_is_readonly,
        has_master_access=has_master_access,
        has_admin_access=has_admin_access
    )


def inject_translations():
    """Inject translation function into templates.
    
    Supports language resolution in order:
    1. session['app_language']
    2. cookie 'app_language'
    3. query param ?lang=
    4. Accept-Language header
    5. default: 'pl'
    """
    
    def get_language():
        """Get preferred language from various sources."""
        # 1. Check session
        if 'app_language' in session:
            return session.get('app_language')
        
        # 2. Check cookie
        if 'app_language' in request.cookies:
            return request.cookies.get('app_language')
        
        # 3. Check query parameter ?lang=uk
        if 'lang' in request.args:
            return request.args.get('lang')
        
        # 4. Check Accept-Language header
        if request.headers.get('Accept-Language'):
            lang_header = request.headers.get('Accept-Language', '').lower()
            if 'uk' in lang_header:
                return 'uk'
            elif 'en' in lang_header:
                return 'en'
        
        # 5. Default to Polish
        return 'pl'
    
    def get_translation(key, default_text=''):
        """Get translation for a given key."""
        try:
            lang = get_language()
            
            # Load translations if not in global cache
            if 'translations' not in _translations_cache:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                trans_paths = [
                    os.path.join(project_root, 'config', 'translations.json'),
                    os.path.join(current_app.root_path, 'config', 'translations.json'),
                ]
                for trans_path in trans_paths:
                    if os.path.exists(trans_path):
                        with open(trans_path, 'r', encoding='utf-8') as f:
                            _translations_cache['translations'] = json.load(f)
                        break
                else:
                    _translations_cache['translations'] = {}
            
            translations = _translations_cache['translations']
            
            # Get text for selected language
            if lang in translations and key in translations[lang]:
                return translations[lang][key]
            elif 'pl' in translations and key in translations['pl']:
                return translations['pl'][key]
            else:
                return default_text or key
        except Exception as e:
            current_app.logger.warning(f'Translation error for key {key}: {e}')
            return default_text or key
    
    return dict(_=get_translation, get_translation=get_translation)


def inject_globals():
    """Inject global variables into all Jinja templates."""
    active_db = getattr(g, 'active_db', get_active_database_name())
    app_version = get_app_version()
    
    # Increase this number to force browser to reload static files (css/js)
    static_version = 46
    
    return dict(static_version=static_version, app_version=app_version, db_name=active_db)


def inject_app_into_templates():
    """Inject Flask app instance into templates for backward compatibility."""
    try:
        return dict(app=current_app)
    except Exception:
        return dict()


def inject_app_version():
    """Inject application version from VERSION file into templates."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        version_path = os.path.join(project_root, 'VERSION')
        with open(version_path, 'r', encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        version = 'N/A'
    return dict(app_version=version)


def inject_bug_report_counters():
    """Inject unread bug reports count for templates (shown where applicable)."""
    try:
        if not session.get('zalogowany'):
            return dict(unread_bug_reports_count=0)

        from app.db import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM zgloszenia_bledow WHERE status = 'nowy'")
        row = cursor.fetchone()
        conn.close()
        count = int(row[0]) if row else 0
        return dict(unread_bug_reports_count=count)
    except Exception:
        return dict(unread_bug_reports_count=0)


def inject_delivery_counters():
    """Wstrzykuje licznik oczekujących przyjęć dla PSD/AGRO/ALL."""
    conn = None
    try:
        if not session.get('zalogowany'):
            return dict(pending_deliveries={'PSD': 0, 'AGRO': 0, 'ALL': 0})

        from app.db import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        counts = {'PSD': 0, 'AGRO': 0, 'ALL': 0}
        total_pending = 0

        # 1) Oczekujące dostawy/przesunięcia z modułu magazyn_dostawy
        cursor.execute(
            """
            SELECT UPPER(TRIM(COALESCE(linia, ''))) AS linia, COUNT(*)
            FROM magazyn_dostawy
            WHERE UPPER(TRIM(COALESCE(status, ''))) IN ('OCZEKUJE', 'PENDING')
            GROUP BY UPPER(TRIM(COALESCE(linia, '')))
            """
        )
        for row in cursor.fetchall():
            l = (row[0] or '').upper()
            qty = int(row[1] or 0)
            total_pending += qty
            if l in counts:
                counts[l] += qty

        counts['ALL'] = total_pending

        return dict(pending_deliveries=counts)
    except Exception:
        return dict(pending_deliveries={'PSD': 0, 'AGRO': 0, 'ALL': 0})
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def inject_today_date():
    """Inject current date 'dzisiaj' into templates globally to prevent UndefinedError in sidebar."""
    from datetime import date
    return dict(dzisiaj=str(date.today()))


def inject_database_info():
    """Wstrzykuje informacje o podłączonej bazie danych (np. czy to baza testowa)."""
    try:
        from app.db import get_active_database_name
        db_name = get_active_database_name()
        is_test_db = 'test' in db_name.lower()
        print(f"[DEBUG context] inject_database_info: db_name={db_name}, is_test={is_test_db}")
        return dict(db_name=db_name, is_test_db=is_test_db)
    except Exception as e:
        print(f"[ERROR context] inject_database_info failed: {e}")
        return dict(db_name='Unknown', is_test_db=False)


def register_contexts(app):
    """Register all context processors with Flask app."""
    app.context_processor(inject_static_version)
    app.context_processor(inject_role_permissions)
    app.context_processor(inject_translations)
    app.context_processor(inject_app_into_templates)
    app.context_processor(inject_app_version)
    app.context_processor(inject_bug_report_counters)
    app.context_processor(inject_delivery_counters)
    app.context_processor(inject_database_info)
    app.context_processor(inject_today_date)
