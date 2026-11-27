"""Read-only CQRS queries for Nested HU packaging sub-rolls."""
from __future__ import annotations

from datetime import datetime

from app import db as app_db
from app.repositories.packaging_subroll_repository import PackagingSubrollRepository
from app.services.scanner.scanner_resolution_service import ScannerResolutionService


class PackagingSubrollQueries:
    """Query service resolving sub-roll lists, direct ROL... scans, and label payloads."""

    @staticmethod
    def is_subroll_barcode(code: str | None) -> bool:
        """Return True if scanned code carries the ROL prefix."""
        clean = str(code or '').strip().upper()
        return clean.startswith('ROL') and len(clean) >= 6

    @staticmethod
    def serialize_subrolls(rows: list[dict]) -> list[dict]:
        """Format DB sub-roll rows into JSON-ready dictionaries."""
        items: list[dict] = []
        for row in rows:
            created = row.get('created_at')
            created_str = (
                created.strftime('%Y-%m-%d %H:%M')
                if hasattr(created, 'strftime')
                else str(created or '')[:16]
            )
            waga_val = row.get('waga_kg')
            items.append({
                'id': int(row['id']),
                'parent_id': int(row['parent_opakowanie_id']),
                'kod_rolki': str(row['kod_rolki']),
                'nr_rolki': int(row.get('nr_rolki') or 1),
                'ilosc_szt': int(row.get('ilosc_szt') or 0),
                'waga_kg': float(waga_val) if waga_val is not None else None,
                'zrodlo': str(row.get('zrodlo') or 'PODZIAL'),
                'created_by': row.get('created_by') or '',
                'created_at': created_str,
            })
        return items

    @staticmethod
    def get_subrolls_summary_with_cursor(
        cursor,
        parent_id: int,
        pallet_total_qty: float,
    ) -> dict:
        """Return sub-rolls list and unassigned piece pool for a master pallet."""
        try:
            rows = PackagingSubrollRepository.list_active_by_parent(cursor, parent_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            if getattr(err, 'errno', None) == 1146:
                return {
                    'subrolls': [],
                    'subrolls_count': 0,
                    'subrolls_total_szt': 0,
                    'unassigned_szt': max(int(round(float(pallet_total_qty or 0))), 0),
                }
            raise

        serialized = PackagingSubrollQueries.serialize_subrolls(rows)
        subrolls_total = sum(item['ilosc_szt'] for item in serialized)
        total_int = max(int(round(float(pallet_total_qty or 0))), 0)
        return {
            'subrolls': serialized,
            'subrolls_count': len(serialized),
            'subrolls_total_szt': subrolls_total,
            'unassigned_szt': max(total_int - subrolls_total, 0),
        }

    @staticmethod
    def enrich_scanner_pallet(pallet: dict | None) -> dict | None:
        """Attach sub-rolls metadata when scanner lookup resolved a packaging pallet."""
        if not pallet or pallet.get('is_station') or pallet.get('is_bucket'):
            return pallet
        inv_type = str(pallet.get('inventory_type') or pallet.get('typ') or '').lower()
        inv_key = str(pallet.get('inventory_key') or '').upper()
        if 'opakow' not in inv_type and inv_key != 'OPK' and not pallet.get('is_pkg'):
            return pallet

        pallet_id = pallet.get('id')
        if not pallet_id or not str(pallet_id).isdigit():
            return pallet

        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            summary = PackagingSubrollQueries.get_subrolls_summary_with_cursor(
                cur,
                int(pallet_id),
                float(pallet.get('stan_magazynowy') or 0),
            )
            pallet.update(summary)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        finally:
            conn.close()
        return pallet

    @staticmethod
    def lookup_by_subroll_code(
        kod_rolki: str,
        linia: str = 'AGRO',
    ) -> dict | None:
        """Resolve a scanned ROL... barcode to its master pallet with selected_subroll."""
        if not PackagingSubrollQueries.is_subroll_barcode(kod_rolki):
            return None
        conn = app_db.get_db_connection()
        parent_sscc = None
        selected = None
        try:
            cur = conn.cursor(dictionary=True)
            try:
                row = PackagingSubrollRepository.find_by_roll_code(cur, kod_rolki)
            except Exception as err:  # pylint: disable=broad-exception-caught
                if getattr(err, 'errno', None) == 1146:
                    return None
                raise
            if not row:
                return None

            if str(row.get('status') or '').upper() != 'NA_PALECIE':
                lp01_id = row.get('lp01_opakowanie_id')
                if lp01_id:
                    cur.execute(
                        "SELECT nr_palety FROM magazyn_opakowania WHERE id = %s LIMIT 1",
                        (lp01_id,),
                    )
                    lp_row = cur.fetchone()
                    if lp_row and lp_row.get('nr_palety'):
                        parent_sscc = lp_row['nr_palety']
                if not parent_sscc:
                    return None
            else:
                cur.execute(
                    "SELECT nr_palety FROM magazyn_opakowania WHERE id = %s LIMIT 1",
                    (row['parent_opakowanie_id'],),
                )
                p_row = cur.fetchone()
                if not p_row:
                    return None
                parent_sscc = p_row.get('nr_palety') or f"OPK-{row['parent_opakowanie_id']}"
                selected = PackagingSubrollQueries.serialize_subrolls([row])[0]
        finally:
            conn.close()

        pallet = ScannerResolutionService.lookup_by_location(parent_sscc, linia=linia)
        if pallet and selected:
            pallet = PackagingSubrollQueries.enrich_scanner_pallet(pallet)
            pallet['selected_subroll'] = selected
        return pallet

    @staticmethod
    def get_subroll_label_data(kod_rolki: str, linia: str = 'AGRO') -> dict | None:
        """Build ZPL label dictionary for a ROL... sub-roll barcode."""
        if not PackagingSubrollQueries.is_subroll_barcode(kod_rolki):
            return None
        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            try:
                sub = PackagingSubrollRepository.find_by_roll_code(cur, kod_rolki)
            except Exception as err:  # pylint: disable=broad-exception-caught
                if getattr(err, 'errno', None) == 1146:
                    return None
                raise
            if not sub:
                return None
            cur.execute(
                "SELECT * FROM magazyn_opakowania WHERE id = %s LIMIT 1",
                (sub['parent_opakowanie_id'],),
            )
            parent = cur.fetchone()
            if not parent:
                return None

            parent_sscc = parent.get('nr_palety') or f"OPK-{parent['id']}"
            dp = parent.get('data_produkcji')
            dp_str = (
                dp.strftime('%d.%m.%Y')
                if hasattr(dp, 'strftime')
                else (str(dp)[:10] if dp else datetime.now().strftime('%d.%m.%Y'))
            )
            dz = parent.get('data_przydatnosci')
            dz_str = (
                dz.strftime('%d.%m.%Y')
                if hasattr(dz, 'strftime')
                else (str(dz)[:10] if dz else '---')
            )
            batch_txt = parent.get('nr_partii') or f"MATKA:{parent_sscc[-8:]}"
            roll_code = str(sub['kod_rolki'])
            return {
                'id': sub['id'],
                'linia': parent.get('linia') or linia,
                'nr_palety': roll_code,
                'sscc': roll_code,
                'qr_data': roll_code,
                'nazwa': f"{parent['nazwa']} [ROLKA #{sub['nr_rolki']}]",
                'ilosc': float(sub['ilosc_szt']),
                'jednostka': 'szt.',
                'lokalizacja': parent.get('lokalizacja') or 'MOP01',
                'partia': f"{batch_txt} ({parent_sscc})",
                'data_produkcji': dp_str,
                'data_przydatnosci': dz_str,
                'data': dp_str,
                'termin': dz_str,
                'typ': 'OPAKOWANIE',
                'inventory_type': 'Opakowanie',
            }
        finally:
            conn.close()
