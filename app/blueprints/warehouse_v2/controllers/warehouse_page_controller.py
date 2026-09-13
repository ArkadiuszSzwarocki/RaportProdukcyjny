# File: app/blueprints/warehouse_v2/controllers/warehouse_page_controller.py
"""Warehouse Page Controller.

Handles generic views and auxiliary pages for warehouse v2:
- Production status
- Orders list and new order cart
- Pallet archive
- 3D rack visualization
"""

from typing import Any, Dict, List
from flask import render_template, request

from app.db import get_db_connection


class WarehousePageController:
    """Controller for generic warehouse pages and 3D visualizers."""

    @staticmethod
    def render_production_status():
        """Summary page for production stations status."""
        linia = request.args.get('linia', 'PSD').upper()
        return render_template('warehouse_v2/production_status.html', linia=linia)

    @staticmethod
    def render_orders():
        """Warehouse raw material orders list view."""
        linia = request.args.get('linia', 'PSD').upper()
        return render_template('warehouse_v2/zamowienia.html', linia=linia)

    @staticmethod
    def render_new_order():
        """Create new raw material order view."""
        linia = request.args.get('linia', 'PSD').upper()
        return render_template('warehouse_v2/zamowienie_nowe.html', linia=linia)

    @staticmethod
    def render_archive():
        """Pallet archive view showing the latest 1000 records."""
        linia = request.args.get('linia', 'PSD').upper()
        conn = get_db_connection()
        archive_items: List[Dict[str, Any]] = []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, original_id, nr_palety, nazwa, typ_palety, linia, nr_partii, 
                       waga_ostatnia, lokalizacja_ostatnia, data_archiwizacji, user_login, komentarz
                FROM magazyn_archiwum
                ORDER BY data_archiwizacji DESC
                LIMIT 1000
            """)
            archive_items = cursor.fetchall() or []
            for row in archive_items:
                arch_date = row.get('data_archiwizacji')
                row['data_archiwizacji_str'] = (
                    arch_date.strftime('%Y-%m-%d %H:%M:%S') if arch_date else '-'
                )
        except Exception as e:
            print(f"Error fetching archive in WarehousePageController: {e}")
        finally:
            if conn:
                conn.close()

        return render_template('warehouse_v2/archiwum.html', linia=linia, items=archive_items)

    @staticmethod
    def render_racks_3d():
        """Interactive 3D Warehouse Rack visualization view."""
        linia = request.args.get('linia', 'ALL').upper()
        active_rack = request.args.get('rack_id', 'R01')

        from app.services.warehouse_3d_service import Warehouse3dService
        racks_config = Warehouse3dService.get_rack_configurations()

        magazyny_zakladki = [
            {'id': 'all', 'name': 'Wszystkie Magazyny'},
            {'id': 'MS01', 'name': 'Magazyn Surowcowy (MS01)'},
            {'id': 'MP01', 'name': 'Magazyn Produkcyjny (MP01)'},
            {'id': 'OSIP', 'name': 'Magazyn Centralny', 'code': 'CENTRALNY'},
            {'id': 'PSD01', 'name': 'Magazyn Produkcyjny (PSD01)'},
            {'id': 'MDO01', 'name': 'Magazyn Dodatków (MDO01)'},
            {'id': 'MOP01', 'name': 'Magazyn Opakowań (MOP01)'},
            {'id': 'MGW01', 'name': 'Wyroby Gotowe (MGW01)'},
            {'id': 'MGW02', 'name': 'Wyroby Gotowe (MGW02)'},
            {'id': 'BF_MS01', 'name': 'BUFOR MS01'},
            {'id': 'BF_MP01', 'name': 'BUFOR MP01'}
        ]

        return render_template(
            'warehouse_v2/racks_3d.html',
            linia=linia,
            active_rack=active_rack,
            racks_config=racks_config,
            zakladki=magazyny_zakladki,
            aktywna_zakladka='all',
            aktywna_podzakladka='all',
            stats={}
        )
