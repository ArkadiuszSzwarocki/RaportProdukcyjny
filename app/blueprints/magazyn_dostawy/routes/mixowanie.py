"""Trasy i endpointy dla modulu mixowania palet."""

from flask import render_template, request, jsonify, session
from app.decorators import roles_required
from app.blueprints.magazyn_dostawy.base import magazyn_dostawy_bp
from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService
from app.services.magazyn_dostawy.pallet_mix_service import PalletMixService

@magazyn_dostawy_bp.route('/mixowanie')
@roles_required('lider', 'masteradmin', 'admin', 'magazynier', 'zarzad')
def mixowanie():
    """Renderuje główny widok mixowania palet."""
    # Podobnie jak podział, użytkownik wybiera linię (AGRO/PSD) - używamy sesji.
    linia = session.get('wybrana_linia_magazyn', 'AGRO')
    return render_template('magazyn_dostawy/mixowanie.html', linia=linia)


@magazyn_dostawy_bp.route('/api/mixowanie/scan', methods=['POST'])
@roles_required('lider', 'masteradmin', 'admin', 'magazynier', 'zarzad')
def api_mix_scan():
    """Skanuje paletę, by pobrać dane komponentu do mixu."""
    data = request.get_json() or {}
    sscc = str(data.get('sscc') or '').strip()

    if not sscc:
        return jsonify({'success': False, 'error': 'Nie podano kodu SSCC.'})

    pal = PalletSplitService.find_by_sscc(sscc)
    if not pal:
        return jsonify({'success': False, 'error': f'Nie odnaleziono palety: {sscc}'})

    # Ograniczenie by można było uzywać tylko surowców/opakowań (chociaż usługa wspiera wszystkie)
    if pal.get('is_blocked'):
        return jsonify({'success': False, 'error': 'Paleta jest zablokowana.'})

    return jsonify({
        'success': True,
        'mother_id': pal['id'],
        'source': pal['source'],
        'nr_palety': pal['nr_palety'],
        'produkt': pal['produkt'],
        'waga': pal['waga'],
        'linia': pal.get('linia', 'AGRO')
    })


@magazyn_dostawy_bp.route('/api/mixowanie/finalize', methods=['POST'])
@roles_required('lider', 'masteradmin', 'admin', 'magazynier', 'zarzad')
def api_mix_finalize():
    """Finalizuje proces mixowania i tworzy nową paletę MIX."""
    data = request.get_json() or {}
    components = data.get('components', [])
    mix_name = str(data.get('mix_name', 'MIX')).strip()
    linia = session.get('wybrana_linia_magazyn', 'AGRO')
    user_login = session.get('user', 'System')

    if not components:
        return jsonify({'success': False, 'error': 'Brak komponentów do mixowania.'})

    try:
        success, message, result = PalletMixService.mix_pallets(
            components=components,
            mix_name=mix_name,
            user_login=user_login,
            linia=linia
        )

        if not success:
            return jsonify({'success': False, 'error': message})

        # Zbieramy URL-e do wydruku (zaktualizowane etykiety palet matczynych oraz główny MIX)
        print_urls = []
        for source in result['sources']:
            # Tworzymy słownik odpowiadający nowej wadze, aby build_label_url zadziałał poprawnie
            pal_dict = {
                'id': source['mother_id'],
                'nr_palety': source['mother_nr_palety'],
                'waga': source['mother_new_weight'],
                'produkt': source['produkt'],
                'nazwa': source['produkt'],
                'nr_partii': source['nr_partii'],
                'data_produkcji': source['data_produkcji'],
                'termin_przydatnosci': source['termin_przydatnosci'],
                'source': source['source'],
                'linia': source['linia']
            }
            url = PalletSplitService.build_label_url(pal_dict)
            print_urls.append(url)

        # URL dla nowej palety MIX
        mix_url = PalletSplitService.build_label_url(result['mix_pallet'])
        print_urls.append(mix_url)

        return jsonify({
            'success': True,
            'message': message,
            'new_mix_sscc': result['mix_pallet']['nr_palety'],
            'print_urls': print_urls
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
