"""
API endpoints dla receptur AGRO (składniki receptury).

Endpointy:
    GET  /api/receptury                          → lista receptur (produkty z nr_receptury)
    GET  /api/receptury/<nr_receptury>/skladniki → składniki receptury
    POST /api/receptury/<nr_receptury>/skladniki → zapisz listę składników (bulk)
    DELETE /api/receptury/skladniki/<int:id>     → soft-delete składnika
"""
from flask import current_app, jsonify, request

from app.db import get_db_connection
from app.decorators import login_required
from app.repositories.receptury_agro_repository import RecepturyAgroRepository


def register_api_receptury_agro_routes(api_bp):

    @api_bp.route('/receptury', methods=['GET'])
    def get_receptury():
        """Zwraca listę produktów z przypisanym nr_receptury (public)."""
        try:
            conn = get_db_connection()
            repo = RecepturyAgroRepository(conn)
            data = repo.get_receptury()
            conn.close()
            return jsonify({'success': True, 'receptury': data}), 200
        except Exception as error:
            current_app.logger.exception('Error fetching receptury: %s', error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/receptury/<string:nr_receptury>/skladniki', methods=['GET'])
    def get_skladniki(nr_receptury):
        """Zwraca aktywne składniki receptury (public)."""
        try:
            conn = get_db_connection()
            repo = RecepturyAgroRepository(conn)
            data = repo.get_skladniki(nr_receptury)
            conn.close()
            return jsonify({'success': True, 'skladniki': data, 'nr_receptury': nr_receptury}), 200
        except Exception as error:
            current_app.logger.exception('Error fetching skladniki for %s: %s', nr_receptury, error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/receptury/<string:nr_receptury>/skladniki', methods=['POST'])
    @login_required
    def save_skladniki(nr_receptury):
        """
        Zapisuje (nadpisuje) listę składników receptury.

        Body JSON:
            {
                "nazwa_produktu": "MLECZNA PYCHA CZERWONA",
                "skladniki": [
                    {"skladnik_nazwa": "BM2", "ilosc_kg_szarza": 750, "typ": "surowiec", "kolejnosc": 0},
                    {"skladnik_nazwa": "Słodki permeat", "typ": "surowiec", "kolejnosc": 1}
                ]
            }
        """
        try:
            data = request.get_json() or {}
            nazwa_produktu = str(data.get('nazwa_produktu') or '').strip()
            skladniki_raw = data.get('skladniki') or []

            if not isinstance(skladniki_raw, list):
                return jsonify({'success': False, 'message': 'Pole "skladniki" musi być listą'}), 400

            conn = get_db_connection()
            repo = RecepturyAgroRepository(conn)
            repo.save_skladniki(
                nr_receptury=nr_receptury,
                nazwa_produktu=nazwa_produktu,
                skladniki=skladniki_raw,
            )
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Receptura {nr_receptury} zapisana ({len(skladniki_raw)} składników)',
                'nr_receptury': nr_receptury,
            }), 200
        except Exception as error:
            current_app.logger.exception('Error saving skladniki for %s: %s', nr_receptury, error)
            return jsonify({'success': False, 'message': str(error)}), 500

    @api_bp.route('/receptury/skladniki/<int:skladnik_id>', methods=['DELETE'])
    @login_required
    def delete_skladnik(skladnik_id):
        """Soft-delete pojedynczego składnika."""
        try:
            conn = get_db_connection()
            repo = RecepturyAgroRepository(conn)
            found = repo.delete_skladnik(skladnik_id)
            conn.close()
            if not found:
                return jsonify({'success': False, 'message': f'Składnik {skladnik_id} nie znaleziony'}), 404
            return jsonify({'success': True, 'message': f'Składnik {skladnik_id} usunięty'}), 200
        except Exception as error:
            current_app.logger.exception('Error deleting skladnik %s: %s', skladnik_id, error)
            return jsonify({'success': False, 'message': str(error)}), 500
