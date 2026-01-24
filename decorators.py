from functools import wraps
from flask import session, redirect, flash

# 1. WYMAGANE LOGOWANIE (Dla wszystkich podstron)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# 2. DOSTĘP DO WYNIKÓW (Zarząd, Admin, Planista, Lider)
def zarzad_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            return redirect('/login')
        
        # Uprawnienia do widoku /zarzad
        if session.get('rola') not in ['zarzad', 'admin', 'planista', 'lider', 'laboratorium']:
            return redirect('/')
            
        return f(*args, **kwargs)
    return decorated_function

# 3. DOSTĘP DO PANELU ADMINA (Tylko Admin - tego brakowało!)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'zalogowany' not in session:
            return redirect('/login')
        
        if session.get('rola') != 'admin':
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
            if 'zalogowany' not in session:
                return redirect('/login')

            # Admin ma zawsze dostęp
            if session.get('rola') == 'admin':
                return f(*args, **kwargs)

            user_rola = session.get('rola')
            user_grupa = session.get('grupa')

            if roles and user_rola not in roles:
                return redirect('/')

            if groups and user_grupa not in groups:
                return redirect('/')

            return f(*args, **kwargs)
        return decorated
    return wrapper