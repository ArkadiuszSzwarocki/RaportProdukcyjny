from flask import session, redirect, url_for
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Sprawdzamy, czy użytkownik jest zalogowany
        if not session.get('zalogowany'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Sprawdzamy logowanie ORAZ rolę admina
        if not session.get('zalogowany') or session.get('rola') != 'admin':
            return redirect(url_for('index')) # Odsyłamy na główną, nie do logowania
        return f(*args, **kwargs)
    return decorated_function