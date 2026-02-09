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
        # Use file modification time of static/css/style.css as cache-buster
        path = os.path.join(current_app.root_path, 'static', 'css', 'style.css')
        v = int(os.path.getmtime(path))
    except Exception:
        v = int(time.time())
    return dict(static_version=v)


def inject_role_permissions():
    """Inject role-based access control functions into templates."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')

    def role_has_access(page):
        try:
            # Read config every time (no caching)
            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception:
                perms = {}
            
            r = (session.get('rola') or '').lower()
            # Log dla debugowania
            current_app.logger.debug(f'role_has_access({page}): rola={r}, session_rola={session.get("rola")}')
            
            # IMPORTANT: if config exists and contains pages, use ONLY config
            # (no fallback to hardcoded rules)
            if perms and len(perms) > 0:
                # Config has data - check if page is in config
                page_perms = perms.get(page)
                if page_perms is None:
                    # Page not in config -> allow (permissive)
                    current_app.logger.debug(f'  page {page} not in perms, allowing')
                    return True
                # Page in config -> check role access
                result = bool(page_perms.get(r, {}).get('access', False))
                current_app.logger.debug(f'  page {page} access for {r}: {result}')
                return result
            
            # Config empty - use fallback
            if page == 'dashboard':
                return r in ['lider', 'admin']
            if page in ('zasyp', 'workowanie', 'magazyn'):
                return r in ['produkcja', 'lider', 'admin', 'zarzad', 'pracownik']
            if page == 'jakosc':
                return r in ['laboratorium', 'lider', 'admin', 'zarzad', 'produkcja', 'planista']
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
            # Read config every time (no caching)
            perms = {}
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    perms = json.load(f)
            except Exception:
                perms = {}
            
            r = (session.get('rola') or '').lower()
            if not perms:
                # default: no readonly restrictions
                return False
            page_perms = perms.get(page)
            if page_perms is None:
                return False
            return bool(page_perms.get(r, {}).get('readonly', False))
        except Exception:
            return False

    return dict(role_has_access=role_has_access, role_is_readonly=role_is_readonly)


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


def inject_app_into_templates():
    """Inject Flask app instance into templates for backward compatibility."""
    try:
        return dict(app=current_app)
    except Exception:
        return dict()


def register_contexts(app):
    """Register all context processors with Flask app."""
    app.context_processor(inject_static_version)
    app.context_processor(inject_role_permissions)
    app.context_processor(inject_translations)
    app.context_processor(inject_app_into_templates)

