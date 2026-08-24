"""
Kontroler API dla profilu użytkownika.
Zapewnia endpointy GET i POST dla pobierania oraz edycji profilu osobistego.
"""
from flask import jsonify, request, session
from app.blueprints.auth.base import auth_bp
from app.decorators import login_required
from app.services.user_profile_service import UserProfileService
from app.dto.user_profile_dto import UserProfileUpdateDTO
from app.core.audit import audit_log


@auth_bp.route('/api/user/profile', methods=['GET'])
@login_required
def get_user_profile_api():
    """Zwraca dane profilowe zalogowanego użytkownika w formacie JSON."""
    login = session.get('login')
    if not login:
        return jsonify({'success': False, 'message': 'Brak aktywnej sesji.'}), 401

    service = UserProfileService()
    profile = service.get_user_profile(login=login)
    if not profile:
        return jsonify({'success': False, 'message': 'Nie odnaleziono konta użytkownika.'}), 404

    return jsonify({'success': True, 'profile': profile.to_dict()})


@auth_bp.route('/api/user/profile/update', methods=['POST'])
@login_required
def update_user_profile_api():
    """Aktualizuje dane profilowe zalogowanego użytkownika."""
    login = session.get('login')
    if not login:
        return jsonify({'success': False, 'message': 'Brak aktywnej sesji.'}), 401

    service = UserProfileService()
    profile = service.get_user_profile(login=login)
    if not profile:
        return jsonify({'success': False, 'message': 'Nie odnaleziono konta użytkownika.'}), 404

    data = request.get_json(silent=True) or request.form

    email = data.get('email')
    urlop_biezacy = data.get('urlop_biezacy')
    urlop_zalegly = data.get('urlop_zalegly')
    imie_nazwisko = data.get('imie_nazwisko')

    def parse_int_or_none(val):
        if val is None or val == '':
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    update_dto = UserProfileUpdateDTO(
        email=str(email) if email is not None else None,
        urlop_biezacy=parse_int_or_none(urlop_biezacy),
        urlop_zalegly=parse_int_or_none(urlop_zalegly),
        imie_nazwisko=str(imie_nazwisko) if imie_nazwisko is not None else None
    )

    success, message = service.update_user_profile(user_id=profile.user_id, update_dto=update_dto)
    if success:
        # Zaktualizuj ew. imie_nazwisko w sesji jeśli uległo zmianie
        if update_dto.imie_nazwisko and update_dto.imie_nazwisko.strip():
            session['imie_nazwisko'] = update_dto.imie_nazwisko.strip()
        audit_log('Edycja profilu', f'Użytkownik {login} zaktualizował własny profil')
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400
