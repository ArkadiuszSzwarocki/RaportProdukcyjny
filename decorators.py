from flask import session, redirect, url_for
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('zalogowany'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('zalogowany') or session.get('rola') != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# NOWE UPRAWNIENIE: Wpuszcza Admina, Lidera i Planistę
def zarzad_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Lista ról, które mają dostęp do wyników
        dozwolone = ['admin', 'lider', 'planista']
        
        if not session.get('zalogowany') or session.get('rola') not in dozwolone:
            return redirect(url_for('index')) # Odsyła na główną, jeśli brak uprawnień
        return f(*args, **kwargs)
    return decorated_function