from functools import wraps
from flask import session, redirect, request, jsonify, current_app

# 1. WYMAGANE LOGOWANIE (Dla wszystkich podstron)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            # If request looks like AJAX/JSON (X-Requested-With or Accepts JSON), return 401 JSON
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False; accepts_json = False
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'unauthenticated'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# 2. DOSTĘP DO WYNIKÓW (Zarząd, Admin, Planista, Lider)
def zarzad_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False; accepts_json = False
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'unauthenticated'}), 401
            return redirect('/login')
        
        # Uprawnienia do widoku /zarzad
        if session.get('rola') not in ['zarzad', 'admin', 'planista', 'lider', 'laborant']:
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False; accepts_json = False
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'forbidden'}), 403
            return redirect('/')
            
        return f(*args, **kwargs)
    return decorated_function

# 3. DOSTĘP DO PANELU ADMINA (Tylko Admin - tego brakowało!)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False; accepts_json = False
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'unauthenticated'}), 401
            return redirect('/login')
        
        if session.get('rola') != 'admin':
            try:
                current_app.logger.warning("[ADMIN_CHECK] Access denied for admin_required - session: %s", {k: session.get(k) for k in ('login','rola','imie_nazwisko')})
            except Exception:
                pass
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False; accepts_json = False
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'forbidden'}), 403
            return redirect('/')
            
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*roles, groups=None):
    """Decorator factory: pozwala określić listę dopuszczalnych ról i opcjonalnie grup.

    Użycie:
      @roles_required('planista', 'lider')
      def view(): ...

      @roles_required('produkcja', groups=['linia1','linia2'])
      def view(): ...
    """
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False
                accepts_json = False

            # Authentication check
            if 'zalogowany' not in session:
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'unauthenticated'}), 401
                return redirect('/login')

            # Normalize role name - only lowercase
            raw_role = session.get('rola')
            r = str(raw_role or '').lower()

            # numeric role ids -> map to canonical names
            if r.isdigit():
                try:
                    idx = int(r)
                    roles_order = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laborant']
                    if 0 <= idx < len(roles_order):
                        r = roles_order[idx]
                except Exception:
                    pass

            # Admin always allowed
            if r == 'admin':
                return f(*args, **kwargs)

            user_rola = r
            user_grupa = session.get('grupa')

            # compare in lowercase
            roles_lower = [x.lower() for x in roles] if roles else []
            if roles and user_rola not in roles_lower:
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'forbidden'}), 403
                return redirect('/')

            if groups and user_grupa not in groups:
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'forbidden'}), 403
                return redirect('/')

            return f(*args, **kwargs)

        return decorated

    return wrapper

def dynamic_role_required(page_name):
    """
    Sprawdza, czy rola użytkownika ma w 'role_permissions.json' ustawioną 
    flagę `access=True` dla podanej podstrony (page_name).
    """
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
            except Exception:
                is_xhr = False
                accepts_json = False

            if 'zalogowany' not in session:
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'unauthenticated'}), 401
                return redirect('/login')

            from app.core.contexts import inject_role_permissions
            # Pobierz metodę wyliczającą dostęp uwzględniającą cache/fallback
            role_checker = inject_role_permissions().get('role_has_access')
            
            if role_checker and role_checker(page_name):
                return f(*args, **kwargs)
            
            if is_xhr or accepts_json:
                return jsonify({'success': False, 'error': 'forbidden'}), 403
            return redirect('/')

        return decorated
    return wrapper