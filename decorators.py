from functools import wraps
from flask import session, redirect, request, jsonify

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
            if session.get('rola') not in ['zarzad', 'admin', 'planista', 'lider', 'laboratorium']:
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
            print(f"[DECORATOR] roles_required check for {f.__name__}")
            print(f"[DECORATOR] Required roles: {roles}")
            print(f"[DECORATOR] Session: zalogowany={session.get('zalogowany')}, rola={session.get('rola')}, grupa={session.get('grupa')}")
            
            if 'zalogowany' not in session:
                print(f"[DECORATOR] ✗ NOT LOGGED IN - redirecting to /login")
                return redirect('/login')

            # Admin ma zawsze dostęp
            if session.get('rola') == 'admin':
                print(f"[DECORATOR] ✓ ADMIN - access granted")
                return f(*args, **kwargs)

            user_rola = session.get('rola')
            user_grupa = session.get('grupa')

            if roles and user_rola not in roles:
                print(f"[DECORATOR] ✗ ROLE CHECK FAILED: {user_rola} not in {roles}")
                return redirect('/')

            if groups and user_grupa not in groups:
                print(f"[DECORATOR] ✗ GROUP CHECK FAILED: {user_grupa} not in {groups}")
                return redirect('/')

            print(f"[DECORATOR] ✓ ALL CHECKS PASSED - calling {f.__name__}")
            return f(*args, **kwargs)
        return decorated
    return wrapper