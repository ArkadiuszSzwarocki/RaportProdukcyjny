"""
Warehouse 3D Service.
Processes warehouse rack layouts, maps pallets to 3D shelf slots, detects packaging types (Big Bag vs Bags),
and prepares complete state for 3D visualization.
"""
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from app.repositories.warehouse_3d_repository import Warehouse3dRepository
from app.dto.warehouse_3d_dto import (
    PalletPayload3dDTO,
    RackSlot3dDTO,
    RackStructure3dDTO,
    Warehouse3dStateDTO,
)

class Warehouse3dService:
    """Service orchestrating 3D warehouse layout, slot matching, and pallet classification."""

    # Default Rack Layout Configurations
    RACK_CONFIGS = [
        {
            "rack_id": "R01",
            "name": "Regał Wysokiego Składowania R01",
            "rack_type": "HIGH_BAY",
            "columns": 10,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.70,
            "position_x": -18.0,
            "position_z": -6.0,
        },
        {
            "rack_id": "R02",
            "name": "Regał Wysokiego Składowania R02",
            "rack_type": "HIGH_BAY",
            "columns": 10,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.70,
            "position_x": -18.0,
            "position_z": -2.5,
        },
        {
            "rack_id": "R03",
            "name": "Regał Wysokiego Składowania R03",
            "rack_type": "HIGH_BAY",
            "columns": 10,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.70,
            "position_x": -18.0,
            "position_z": 2.5,
        },
        {
            "rack_id": "R04",
            "name": "Regał Wysokiego Składowania R04",
            "rack_type": "HIGH_BAY",
            "columns": 10,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.70,
            "position_x": -18.0,
            "position_z": 6.0,
        },
        {
            "rack_id": "R05",
            "name": "Regał Paletowy R05",
            "rack_type": "HIGH_BAY",
            "columns": 4,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.65,
            "position_x": 4.0,
            "position_z": -6.0,
        },
        {
            "rack_id": "R06",
            "name": "Regał Paletowy R06",
            "rack_type": "HIGH_BAY",
            "columns": 5,
            "levels": 5,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.65,
            "position_x": 4.0,
            "position_z": -2.0,
        },
        {
            "rack_id": "R07",
            "name": "Regał Paletowy R07",
            "rack_type": "HIGH_BAY",
            "columns": 10,
            "levels": 4,
            "depth_m": 1.25,
            "bay_width_m": 1.45,
            "level_height_m": 1.70,
            "position_x": 4.0,
            "position_z": 2.5,
        },
        {
            "rack_id": "R09",
            "name": "Regał Półkowy R09 (Kompletacja)",
            "rack_type": "SHELVING",
            "columns": 4,
            "levels": 6,
            "depth_m": 1.00,
            "bay_width_m": 1.30,
            "level_height_m": 0.85,
            "position_x": 4.0,
            "position_z": 7.0,
        },
    ]

    @classmethod
    def get_rack_configurations(cls) -> List[Dict[str, Any]]:
        """Returns standard rack layout configurations."""
        return [dict(rc) for rc in cls.RACK_CONFIGS]

    @classmethod
    def get_warehouse_3d_state(cls, linia: str = 'ALL', rack_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Builds full 3D warehouse state with all racks, slots, occupancy, and 3D pallet payloads matching DB stock.
        """
        raw_items = Warehouse3dRepository.fetch_all_active_stock(linia)
        
        # Group items by normalized location code
        items_by_loc: Dict[str, List[Dict[str, Any]]] = {}
        # Track max column and level found per rack in the DB
        rack_max_cols: Dict[str, int] = {}
        rack_max_lvls: Dict[str, int] = {}
        discovered_racks: set = set()

        for it in raw_items:
            norm_loc = cls._normalize_location_key(it.get('location'))
            if not norm_loc:
                continue
            if norm_loc not in items_by_loc:
                items_by_loc[norm_loc] = []
            items_by_loc[norm_loc].append(it)

            # Check if this is a standard rack slot RXXYYZZ
            m_r = re.match(r'^(R\d{2})(\d{2})(\d{2})$', norm_loc)
            if m_r:
                r_id = m_r.group(1)
                c_idx = int(m_r.group(2))
                l_idx = int(m_r.group(3))
                discovered_racks.add(r_id)
                rack_max_cols[r_id] = max(rack_max_cols.get(r_id, 0), c_idx)
                rack_max_lvls[r_id] = max(rack_max_lvls.get(r_id, 0), l_idx)

        racks_output: List[Dict[str, Any]] = []
        total_slots_count = 0
        total_occupied_count = 0
        total_blocked_count = 0
        total_big_bags_count = 0
        total_bags_count = 0
        total_fifo_count = 0
        total_expiring_count = 0
        total_expired_count = 0

        # Build base configuration list (expand standard configs + any newly discovered racks in DB)
        active_configs = [dict(rc) for rc in cls.RACK_CONFIGS]
        existing_rack_ids = {rc['rack_id'] for rc in active_configs}

        for extra_r_id in sorted(discovered_racks - existing_rack_ids):
            active_configs.append({
                "rack_id": extra_r_id,
                "name": f"Regał Paletowy {extra_r_id}",
                "rack_type": "HIGH_BAY",
                "columns": max(4, rack_max_cols.get(extra_r_id, 4)),
                "levels": max(4, rack_max_lvls.get(extra_r_id, 4)),
                "depth_m": 1.25,
                "bay_width_m": 1.45,
                "level_height_m": 1.70,
                "position_x": 4.0,
                "position_z": 10.0 + len(active_configs) * 3.5,
            })

        target_configs = active_configs
        if rack_filter and rack_filter.upper() != 'ALL':
            norm_rf = rack_filter.upper().strip()
            # Support R1 -> R01 matching
            if re.match(r'^R\d$', norm_rf):
                norm_rf = f"R0{norm_rf[1]}"
            target_configs = [rc for rc in active_configs if rc['rack_id'].upper() == norm_rf]

        all_built_pallets: List[Dict[str, Any]] = []

        for rc in target_configs:
            rack_id = rc['rack_id']
            # Dynamic expansion if database items exceed base template columns or levels
            cols = max(rc['columns'], rack_max_cols.get(rack_id, 0))
            levels = max(rc['levels'], rack_max_lvls.get(rack_id, 0))
            slots_map: Dict[str, Dict[str, Any]] = {}
            rack_occupied = 0
            rack_blocked = 0

            for col in range(1, cols + 1):
                for lvl in range(1, levels + 1):
                    loc_code = f"{rack_id}{col:02d}{lvl:02d}"
                    matching_items = items_by_loc.get(loc_code, [])

                    pallets_list: List[Dict[str, Any]] = []
                    slot_is_blocked = False
                    primary_payload_type = 'EMPTY'

                    for item in matching_items:
                        is_blk = bool(item.get('is_blocked') or False)
                        if is_blk:
                            slot_is_blocked = True

                        pkg_type = cls._classify_payload_type(
                            item.get('productName', ''),
                            item.get('typ_opakowania', ''),
                            item.get('pallet_type', '')
                        )
                        if primary_payload_type == 'EMPTY':
                            primary_payload_type = pkg_type

                        if pkg_type == 'BIG_BAG':
                            total_big_bags_count += 1
                        elif pkg_type == 'BAGS':
                            total_bags_count += 1

                        p_nr = str(item.get('nr_palety') or f"PAL-{item.get('id')}")
                        amt = float(item.get('amount') or 0.0)

                        exp_info = cls._calculate_expiry_info(item.get('data_przydatnosci'))
                        if exp_info['is_expired']:
                            total_expired_count += 1
                        elif exp_info['is_expiring_soon']:
                            total_expiring_count += 1

                        p_dto = {
                            'id': item.get('id'),
                            'nr_palety': p_nr,
                            'display_id': p_nr,
                            'product_name': item.get('productName') or 'Nieznany produkt',
                            'pallet_type': item.get('pallet_type') or 'Wyrób Gotowy',
                            'packaging_type': pkg_type,
                            'amount': amt,
                            'weight_kg': amt,
                            'unit': 'szt' if str(item.get('pallet_type')).lower() == 'opakowanie' else 'kg',
                            'location': loc_code,
                            'batch': item.get('nr_partii') or '-',
                            'date_prod': cls._format_date(item.get('data_produkcji')),
                            'date_exp': cls._format_date(item.get('data_przydatnosci')),
                            'date_added': cls._format_date(item.get('created_at'), '%Y-%m-%d %H:%M'),
                            'is_blocked': is_blk,
                            'linia': item.get('linia') or linia,
                            'is_first_fifo': False,
                            'fifo_rank': None,
                            'is_expired': exp_info['is_expired'],
                            'is_expiring_soon': exp_info['is_expiring_soon'],
                            'days_to_exp': exp_info['days_to_exp'],
                            'exp_status_label': exp_info['status_label'],
                            'exp_status_color': exp_info['status_color'],
                            '_sort_date': cls._extract_sort_timestamp(item.get('data_produkcji'), item.get('created_at')),
                        }
                        pallets_list.append(p_dto)
                        all_built_pallets.append(p_dto)

                    is_occupied = len(pallets_list) > 0
                    if is_occupied:
                        rack_occupied += 1
                        total_occupied_count += 1
                    if slot_is_blocked:
                        rack_blocked += 1
                        total_blocked_count += 1

                    slots_map[loc_code] = {
                        'location_code': loc_code,
                        'rack_id': rack_id,
                        'column': col,
                        'column_index': col,
                        'level': lvl,
                        'level_index': lvl,
                        'is_occupied': is_occupied,
                        'is_blocked': slot_is_blocked,
                        'payload_type': primary_payload_type,
                        'primary_payload_type': primary_payload_type,
                        'pallet': pallets_list[0] if pallets_list else None,
                        'pallets': pallets_list,
                    }

            total_rack_slots = cols * levels
            total_slots_count += total_rack_slots
            occ_pct = round((rack_occupied / total_rack_slots) * 100, 1) if total_rack_slots > 0 else 0.0

            racks_output.append({
                'rack_id': rack_id,
                'name': rc['name'],
                'rack_type': rc['rack_type'],
                'columns': cols,
                'levels': levels,
                'columns_count': cols,
                'levels_count': levels,
                'depth_m': rc['depth_m'],
                'bay_width_m': rc['bay_width_m'],
                'level_height_m': rc['level_height_m'],
                'position_x': rc['position_x'],
                'position_z': rc['position_z'],
                'total_slots': total_rack_slots,
                'occupied_slots': rack_occupied,
                'blocked_slots': rack_blocked,
                'occupancy_percent': occ_pct,
                'slots': list(slots_map.values()),
            })

        # Calculate FIFO priority ranks grouped per product
        cls._assign_fifo_ranks(all_built_pallets)
        total_fifo_count = sum(1 for p in all_built_pallets if p.get('is_first_fifo'))

        global_occ = round((total_occupied_count / total_slots_count) * 100, 1) if total_slots_count > 0 else 0.0

        return {
            'success': True,
            'linia': linia,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_racks_count': len(racks_output),
                'total_slots_count': total_slots_count,
                'total_occupied_count': total_occupied_count,
                'total_free_count': total_slots_count - total_occupied_count,
                'total_blocked_count': total_blocked_count,
                'total_big_bags_count': total_big_bags_count,
                'total_bags_count': total_bags_count,
                'total_fifo_count': total_fifo_count,
                'total_expiring_count': total_expiring_count,
                'total_expired_count': total_expired_count,
                'global_occupancy_percent': global_occ,
            },
            'racks': racks_output,
        }

    @staticmethod
    def _normalize_location_key(raw_loc: Optional[str]) -> str:
        """Normalizes location strings to standard RXXYYZZ format."""
        if not raw_loc:
            return ''
        s = str(raw_loc).strip().upper()
        # Handle common typos (e.g. RO1 -> R01, RO01 -> R01)
        if s.startswith('RO'):
            s = 'R0' + s[2:]
        
        # Match with separators: R01-02-03, R1-2-3, R01/02/03, R01_02_03, R01.02.03, R01 02 03
        m_sep = re.match(r'^R\s*0?(\d{1,2})[\s\-_/.]0?(\d{1,2})[\s\-_/.]0?(\d{1,2})$', s)
        if m_sep:
            return f"R{int(m_sep.group(1)):02d}{int(m_sep.group(2)):02d}{int(m_sep.group(3)):02d}"

        # Match compact standard 6-7 char code: R010203, R011002
        cleaned = re.sub(r'[^A-Z0-9]', '', s)
        m_comp = re.match(r'^R(\d{2})(\d{2})(\d{2})$', cleaned)
        if m_comp:
            return f"R{int(m_comp.group(1)):02d}{int(m_comp.group(2)):02d}{int(m_comp.group(3)):02d}"

        # Match compact 5-char code: R10203 -> R010203
        m_short = re.match(r'^R(\d{1})(\d{2})(\d{2})$', cleaned)
        if m_short:
            return f"R{int(m_short.group(1)):02d}{int(m_short.group(2)):02d}{int(m_short.group(3)):02d}"

        return cleaned

    @staticmethod
    def _classify_payload_type(product_name: str, packaging_type: str, pallet_type: str) -> str:
        """
        Classifies product into 3D representation type:
        - BIG_BAG: Big Bag with lifting loops and cylindrical/cubic flexible body
        - BAGS: Interlocking pillow sacks stacked in layers on wooden pallet
        - WRAPPED_PALLET: Boxes, drums, packaging reels, or generic wrapped pallet
        """
        p_name = str(product_name or '').upper()
        pkg = str(packaging_type or '').upper()
        p_type = str(pallet_type or '').upper()

        if 'BIG' in pkg or 'BB' in pkg or 'BIG BAG' in p_name or 'BIGBAG' in p_name or 'BB' in p_name or '1000KG' in p_name or 'WAPNO BB' in p_name:
            return 'BIG_BAG'

        if 'WOREK' in pkg or 'WORKI' in pkg or 'BAG' in pkg or 'WOREK' in p_name or 'WORK' in p_name or '25KG' in p_name or '50KG' in p_name or '20KG' in p_name:
            return 'BAGS'

        if p_type == 'OPAKOWANIE' or 'KARTON' in pkg or 'ROLKA' in pkg or 'FOLIA' in p_name:
            return 'WRAPPED_PALLET'

        # Default for bulk powder raw materials and finished pallets without explicit Big Bag marker is BAGS
        if p_type in ('WYRÓB GOTOWY', 'SUROWIEC', 'DODATEK'):
            return 'BAGS'

        return 'WRAPPED_PALLET'

    @staticmethod
    def _format_date(val: Any, fmt: str = '%Y-%m-%d') -> str:
        if not val:
            return '-'
        if isinstance(val, datetime):
            return val.strftime(fmt)
        return str(val)[:10]

    @classmethod
    def _calculate_expiry_info(cls, exp_val: Any) -> Dict[str, Any]:
        """Calculates days until expiration and status flags safely."""
        if not exp_val or str(exp_val).strip() in ('-', '', 'None', 'NULL'):
            return {
                'days_to_exp': None,
                'is_expired': False,
                'is_expiring_soon': False,
                'status_label': 'Brak daty',
                'status_color': '#94a3b8'
            }

        exp_date = None
        try:
            if hasattr(exp_val, 'date') and callable(getattr(exp_val, 'date')):
                exp_date = exp_val.date()
            elif isinstance(exp_val, datetime):
                exp_date = exp_val.date()
            elif hasattr(exp_val, 'year') and hasattr(exp_val, 'month') and hasattr(exp_val, 'day'):
                # datetime.date object
                exp_date = date(exp_val.year, exp_val.month, exp_val.day)
            else:
                s = str(exp_val).strip()[:10]
                for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
                    try:
                        exp_date = datetime.strptime(s, fmt).date()
                        break
                    except Exception:
                        pass
        except Exception:
            exp_date = None

        if not exp_date:
            return {
                'days_to_exp': None,
                'is_expired': False,
                'is_expiring_soon': False,
                'status_label': 'Nieznana',
                'status_color': '#94a3b8'
            }

        today = datetime.now().date()
        try:
            days = (exp_date - today).days
        except Exception:
            return {
                'days_to_exp': None,
                'is_expired': False,
                'is_expiring_soon': False,
                'status_label': 'Nieznana',
                'status_color': '#94a3b8'
            }

        if days < 0:
            return {
                'days_to_exp': days,
                'is_expired': True,
                'is_expiring_soon': False,
                'status_label': f'Przeterminowana ({abs(days)}d temu)',
                'status_color': '#ef4444'
            }
        elif days <= 30:
            return {
                'days_to_exp': days,
                'is_expired': False,
                'is_expiring_soon': True,
                'status_label': f'Krótki termin ({days}d)',
                'status_color': '#f59e0b'
            }
        else:
            return {
                'days_to_exp': days,
                'is_expired': False,
                'is_expiring_soon': False,
                'status_label': f'Ważna ({days}d)',
                'status_color': '#10b981'
            }

    @staticmethod
    def _extract_sort_timestamp(prod_val: Any, created_val: Any) -> float:
        """Extracts numeric sortable timestamp for FIFO ordering safely."""
        for val in (prod_val, created_val):
            if not val or str(val).strip() in ('-', '', 'None', 'NULL'):
                continue
            try:
                if hasattr(val, 'timestamp') and callable(getattr(val, 'timestamp')):
                    return float(val.timestamp())
                if hasattr(val, 'year') and hasattr(val, 'month') and hasattr(val, 'day'):
                    return datetime(val.year, val.month, val.day).timestamp()
                s = str(val).strip()
                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y'):
                    try:
                        return datetime.strptime(s[:19], fmt).timestamp()
                    except Exception:
                        continue
            except Exception:
                continue
        return 9999999999.0

    @classmethod
    def _assign_fifo_ranks(cls, pallets: List[Dict[str, Any]]) -> None:
        """Groups pallets by product and assigns FIFO priority ranks (oldest first)."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for p in pallets:
            prod_name = str(p.get('product_name') or '').strip().upper()
            if not prod_name:
                prod_name = 'NIEZNANY'
            if prod_name not in grouped:
                grouped[prod_name] = []
            grouped[prod_name].append(p)

        for prod_name, p_list in grouped.items():
            # Sort by production date / created date ascending (oldest first)
            p_list.sort(key=lambda x: (
                x.get('is_blocked', False),
                x.get('_sort_date', 9999999999.0),
                x.get('id') or 0
            ))
            # First eligible non-blocked pallet is FIFO #1
            assigned_first = False
            rank = 1
            for p in p_list:
                p['fifo_rank'] = rank
                if not assigned_first and not p.get('is_blocked') and not p.get('is_expired'):
                    p['is_first_fifo'] = True
                    assigned_first = True
                else:
                    p['is_first_fifo'] = False
                rank += 1

