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


def inject_static_version():
    """Inject cache-busting static file version based on CSS modification time."""
    try:
        candidates = [
            os.path.join(current_app.root_path, 'static', 'css', 'style.css'),
            os.path.join(current_app.root_path, 'static', 'css', 'sidebar.css'),
            os.path.join(current_app.root_path, 'static', 'css', 'inline-styles.css'),
            os.path.join(current_app.root_path, 'static', 'scripts.js'),
            os.path.join(current_app.root_path, 'static', 'js', 'sidebar.js'),
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
            r = str(session.get('rola') or '').lower().strip()
            if r == 'masteradmin':
                return True

            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception as e:
                current_app.logger.error(f"[DEBUG configs] Failed to load role_permissions.json from {cfg_path}: {e}")
                perms = {}
            
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
            
            if perms and len(perms) > 0:
                page_key = _resolve_page_key(page, perms)
                page_perms = perms.get(page_key)
                if page_perms is None:
                    current_app.logger.warning(f"role_has_access: page_key '{page_key}' not found in perms (original page: '{page}')")
                    return False
                
                role_cfg = page_perms.get(r, {})
                result = bool(role_cfg.get('access', False))
                current_app.logger.info(f"role_has_access(page={page}, key={page_key}, role={r}) -> {result} (cfg: {role_cfg})")
                return result
            
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
            return True
        except Exception as e:
            current_app.logger.exception(f'role_has_access({page}) error: {e}')
            return False

    def role_is_readonly(page):
        try:
            r = str(session.get('rola') or '').lower().strip()
            if r == 'masteradmin':
                return False

            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception:
                perms = {}
            
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
                return False
            page_key = _resolve_page_key(page, perms)
            page_perms = perms.get(page_key)
            if page_perms is None:
                return False
            return bool(page_perms.get(r, {}).get('readonly', False))
        except Exception:
            return False

    curr_role = str(session.get('rola') or '').lower().strip()
    has_master_access = (curr_role == 'masteradmin')
    has_admin_access = (curr_role in ['admin', 'masteradmin'])

    return dict(
        role_has_access=role_has_access, 
        role_is_readonly=role_is_readonly,
        has_master_access=has_master_access,
        has_admin_access=has_admin_access
    )


def inject_translations():
    """Inject translation function into templates."""
    def get_language():
        if 'app_language' in session:
            return session.get('app_language')
        if 'app_language' in request.cookies:
            return request.cookies.get('app_language')
        if 'lang' in request.args:
            return request.args.get('lang')
        if request.headers.get('Accept-Language'):
            lang_header = request.headers.get('Accept-Language', '').lower()
            if 'uk' in lang_header:
                return 'uk'
            elif 'en' in lang_header:
                return 'en'
        return 'pl'
    
    def get_translation(key, default_text=''):
        try:
            lang = get_language()
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
    """Inject unread bug reports count for templates."""
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


def inject_db_env():
    """Wstrzykuje informacje o aktywnym środowisku (baza testowa) do szablonów."""
    is_test_db = False
    try:
        # Metoda 1: Sprawdza fizycznie podpiętą bazę z konfiguracji aplikacji
        from app.db import get_active_database_name
        active_db = str(get_active_database_name()).lower()
        if 'test' in active_db:
            is_test_db = True
            
        # Metoda 2: Zapasowe sprawdzenie zawartości pliku active_db.txt
        if not is_test_db:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            active_db_path = os.path.join(project_root, 'active_db.txt')
            if os.path.exists(active_db_path):
                with open(active_db_path, 'r', encoding='utf-8') as f:
                    db_content = f.read().strip().lower()
                    if 'test' in db_content:  # <--- Sprawdzamy czy ZAWIERA słowo test
                        is_test_db = True
    except Exception:
        pass
        
    return dict(is_test_db=is_test_db)

def register_contexts(app):
    """Register all context processors with Flask app."""
    app.context_processor(inject_static_version)
    app.context_processor(inject_role_permissions)
    app.context_processor(inject_translations)
    app.context_processor(inject_app_into_templates)
    app.context_processor(inject_app_version)
    app.context_processor(inject_bug_report_counters)
    app.context_processor(inject_delivery_counters)
    app.context_processor(inject_db_env)