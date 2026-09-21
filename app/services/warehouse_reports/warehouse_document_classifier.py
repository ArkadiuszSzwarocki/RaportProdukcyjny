"""
Moduł odpowiedzialny za klasyfikację dokumentów magazynowych oraz weryfikację stref i tras.
"""
from typing import Dict, Any, List, Optional
import re


class WarehouseDocumentClassifier:
    @staticmethod
    def is_production_zone(loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja wskazuje na strefę produkcyjną."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        if 'PRODUKCJA' in l or 'PROD' in l:
            return True
        if any(k in l for k in ('ZASYP', 'WORKOWANIE', 'STACJA', 'LP01')):
            return True
        return False

    @staticmethod
    def is_osip_location(loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja należy do OSIP."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        if 'OSIP' in l or 'W_TRANZYCIE_OSIP' in l:
            return True
        if l.startswith('OS'):
            return True
        return False

    @classmethod
    def is_osip_involved(
        cls,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Sprawdza czy operacja magazynowa dotyczy magazynu OSIP (ruch DO OSIP lub Z OSIP)."""
        if cls.is_osip_location(source) or cls.is_osip_location(destination):
            return True

        if items and isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                target_loc = str(it.get('lokalizacja_przyjecia') or it.get('targetSpot') or it.get('lokalizacja_do') or '').strip().upper()
                source_loc = str(it.get('sourceSpot') or it.get('source_location') or it.get('lokalizacja_z') or '').strip().upper()
                if cls.is_osip_location(target_loc) or cls.is_osip_location(source_loc):
                    return True

        return False

    @classmethod
    def is_destination_osip(cls, destination: Optional[str], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Kompatybilność wsteczna: sprawdza powiązanie z OSIP."""
        return cls.is_osip_involved(None, destination, items)

    @staticmethod
    def is_allowed_central_warehouse_location(loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja należy do dozwolonych regałów lub buforów Magazynu Centralnego."""
        if not loc:
            return False
        l = str(loc).strip().upper()

        # OSIP / produkcja / zewnętrzne stacje wykluczone
        if 'OSIP' in l or 'TRANZYT' in l:
            return False
        if l.startswith('OS') or l.startswith('MZ') or l.startswith('KO') or l.startswith('BB') or l.startswith('LP'):
            return False
        if 'PODŁOGA' in l or 'PODLOGA' in l or 'MASZYNA' in l:
            return False

        # Wzorce regałowe (np. R010101, R020603, R-01-01-01, RR030602, 010102)
        cleaned = re.sub(r'[^A-Z0-9]', '', l)
        if re.match(r'^(?:R|RR)?0[1-9]\d{4}$', cleaned) or re.match(r'^0[1-9]\d{4}$', cleaned):
            return True

        allowed_buffers = {
            'MP01', 'MPO1', 'BFMP01', 'BF_MP01', 'BFMS01', 'BF_MS01',
            'MS01', 'PSD', 'PSD01', 'MGW01', 'MGW02', 'MOP01', 'MO01',
            'MDO01', 'MD01', 'MDM01'
        }
        return l in allowed_buffers

    @classmethod
    def is_allowed_central_transfer(
        cls,
        source: Optional[str],
        destination: Optional[str],
        items: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Weryfikuje czy przesunięcie odbywa się wyłącznie wewnątrz dozwolonych stref Magazynu Centralnego."""
        src = str(source or '').strip().upper()
        dest = str(destination or '').strip().upper()

        if not src and not dest:
            return False

        if src == 'WIELE' and (not dest or cls.is_allowed_central_warehouse_location(dest)):
            return True
        if dest == 'WIELE' and (not src or cls.is_allowed_central_warehouse_location(src)):
            return True

        if not src and cls.is_allowed_central_warehouse_location(dest):
            return True
        if not dest and cls.is_allowed_central_warehouse_location(src):
            return True

        if cls.is_allowed_central_warehouse_location(src) and cls.is_allowed_central_warehouse_location(dest):
            return True

        return False

    @staticmethod
    def is_mp01_location(loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja dotyczy strefy MP01."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        return 'MP01' in l or l.startswith('MP') or 'PODŁOGA' in l

    @staticmethod
    def is_rack_location(loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja to standardowy regał magazynowy R01-R09."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        return bool(re.match(r'^R0[1-9]', l))

    @classmethod
    def is_production_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Weryfikuje czy dokument dotyczy przesunięcia z produkcji."""
        supplier = str(dostawa.get('supplier') or '').strip().upper()
        if 'PRODUKCJA' in supplier or supplier.startswith('PROD'):
            return True

        src = str(dostawa.get('lokalizacja_z') or '').strip().upper()
        if cls.is_production_zone(src):
            return True

        ref = str(dostawa.get('order_ref') or '').strip().lower()
        if any(ref.startswith(k) for k in ('czyszczenie', 'zwrot ze stacji', 'zlecenie #', 'zlecenie_')):
            return True

        if items and isinstance(items, list):
            valid_items = [it for it in items if isinstance(it, dict)]
            if valid_items:
                if any(it.get('is_return') for it in valid_items):
                    return True
                if all(cls.is_production_zone(it.get('sourceSpot') or it.get('source_location')) for it in valid_items):
                    return True

        return False

    @classmethod
    def is_internal_mp01_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Weryfikuje czy ruch odbywa się wewnątrz strefy magazynowej / regałów MP01."""
        src = str(dostawa.get('lokalizacja_z') or '').strip().upper()
        dest = str(dostawa.get('lokalizacja_do') or '').strip().upper()

        actual_sources = []
        actual_targets = []
        if items and isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    s = str(it.get('sourceSpot') or it.get('source_location') or '').strip().upper()
                    t = str(it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip().upper()
                    if s and s not in ('DOSTAWA', 'OCZEKUJĄCE', 'OCZEKUJACE', '-'):
                        actual_sources.append(s)
                    if t and t not in ('OCZEKUJĄCE', 'OCZEKUJACE', '-'):
                        actual_targets.append(t)

        is_src_prod = cls.is_production_zone(src) or (actual_sources and any(cls.is_production_zone(s) for s in actual_sources))
        is_dest_mp01 = cls.is_mp01_location(dest) or (actual_targets and any(cls.is_mp01_location(t) for t in actual_targets))
        if is_src_prod and is_dest_mp01:
            return True

        is_src_rack = cls.is_rack_location(src) or (actual_sources and all(cls.is_rack_location(s) for s in actual_sources))
        if is_src_rack and is_dest_mp01:
            return True

        is_src_mp01 = cls.is_mp01_location(src) or (actual_sources and all(cls.is_mp01_location(s) for s in actual_sources))
        is_dest_rack = cls.is_rack_location(dest) or (actual_targets and all(cls.is_rack_location(t) for t in actual_targets))
        if is_src_mp01 and is_dest_rack:
            return True

        if is_src_mp01 and is_dest_mp01:
            return True

        if is_src_rack and is_dest_rack:
            return True

        return False

    @classmethod
    def categorize_delivery_doc(cls, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rozpoznaje szczegółowy typ i metadane dokumentu magazynowego."""
        supplier = (dostawa.get('supplier') or '').strip()
        source_loc = (dostawa.get('lokalizacja_z') or '').strip()
        dest_loc = (dostawa.get('lokalizacja_do') or '').strip()
        ref = dostawa.get('order_ref') or f"#{dostawa.get('id')}"

        has_supplier = bool(supplier) and supplier not in ('-', 'None', '')
        is_external = has_supplier

        actual_target_spots = sorted({
            (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip()
            for it in items
            if (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip() and (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip() != 'OCZEKUJĄCE'
        })
        if (not dest_loc or dest_loc == 'OCZEKUJĄCE') and actual_target_spots:
            dest_loc = ", ".join(actual_target_spots)

        if not source_loc:
            actual_source_spots = sorted({
                (it.get('sourceSpot') or it.get('source_location') or '').strip()
                for it in items
                if (it.get('sourceSpot') or it.get('source_location') or '').strip()
            })
            if actual_source_spots:
                source_loc = ", ".join(actual_source_spots)

        is_dest_osip = cls.is_osip_location(dest_loc) or any(cls.is_osip_location(it.get('lokalizacja_przyjecia') or it.get('targetSpot')) for it in items)

        if is_external:
            if is_dest_osip:
                doc_type_code = 'DOSTAWA_OSIP'
                doc_title = 'Dostawa OSIP'
                header_title = '📦 Raport Przyjęcia: Dostawa OSIP'
                subject_tag = 'Dostawa OSIP'
            else:
                doc_type_code = 'DOSTAWA_CENTRALA'
                doc_title = 'Dostawa Centrala'
                header_title = '📦 Raport Przyjęcia: Dostawa Centrala'
                subject_tag = 'Dostawa Centrala'
            theme_color_from = '#1e3a8a'
            theme_color_to = '#2563eb'
            source_label = 'DOSTAWCA'
            source_value = supplier or 'Dostawca zewnętrzny'
            dest_label = 'LOKALIZACJA DOCELOWA'
            dest_value = dest_loc or 'Magazyn'
            creator_label = 'OTWORZYŁ / WPROWADZIŁ'
            acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
        else:
            doc_type_code = 'PRZESUNIECIE_MM'
            doc_title = 'Przesunięcie MM'
            header_title = '🔄 Raport Realizacji: Przesunięcie MM'
            theme_color_from = '#065f46'
            theme_color_to = '#059669'
            source_label = 'LOKALIZACJA ŹRÓDŁOWA (SKĄD)'
            source_value = source_loc or 'Magazyn'
            dest_label = 'LOKALIZACJA DOCELOWA (DOKĄD)'
            dest_value = dest_loc or 'Magazyn'
            creator_label = 'WYDAŁ / OTWORZYŁ'
            acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
            subject_tag = 'Przesunięcie MM'

        created_by = dostawa.get('created_by') or 'System'
        created_at = dostawa.get('created_at')
        created_str = created_at.strftime('%Y-%m-%d %H:%M') if hasattr(created_at, 'strftime') else str(created_at or '-')

        accepted_by = (
            dostawa.get('potwierdzone_przez') or
            next((it.get('accepted_by') for it in items if it.get('accepted_by')), None) or
            dostawa.get('updated_by') or
            '-'
        )
        accepted_at = (
            dostawa.get('potwierdzone_at') or
            next((it.get('accepted_at') for it in items if it.get('accepted_at')), None) or
            dostawa.get('updated_at')
        )
        accepted_str = accepted_at.strftime('%Y-%m-%d %H:%M') if hasattr(accepted_at, 'strftime') else str(accepted_at or '-')

        return {
            'is_external': is_external,
            'is_dest_osip': is_dest_osip,
            'doc_type_code': doc_type_code,
            'doc_title': doc_title,
            'header_title': header_title,
            'subject_tag': subject_tag,
            'theme_color_from': theme_color_from,
            'theme_color_to': theme_color_to,
            'source_label': source_label,
            'source_value': source_value,
            'dest_label': dest_label,
            'dest_value': dest_value,
            'creator_label': creator_label,
            'creator_value': f"{created_by} ({created_str})" if created_str != '-' else created_by,
            'acceptor_label': acceptor_label,
            'acceptor_value': f"{accepted_by} ({accepted_str})" if accepted_str != '-' else accepted_by,
            'ref': ref,
            'created_by': created_by,
            'created_str': created_str,
            'accepted_by': accepted_by,
            'accepted_str': accepted_str
        }
