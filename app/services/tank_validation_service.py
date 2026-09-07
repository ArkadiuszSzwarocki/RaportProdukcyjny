import re
from typing import List, Dict, Any, Optional, Tuple
from app.repositories.tank_validation_repository import TankValidationRepository
from app.repositories.agro_tanks_repository import AgroTanksRepository, _normalize_tank_code, _classify_tank_zone
from app.services.agro.agro_tanks_service import AgroTanksService


def _normalize_name_for_comparison(text: str) -> str:
    """Normalize string for robust material name comparison."""
    if not text:
        return ""
    cleaned = re.sub(r'[\s\-_\.,\(\)\/]+', ' ', str(text).upper()).strip()
    return cleaned


class TankValidationService:
    """Service for validating and managing production tank material assignments."""

    @classmethod
    def get_all_tanks_with_state(cls, linia: str = 'Agro') -> Dict[str, Any]:
        """Fetch all predefined production tanks with their configured rules,

        active production materials, and raw materials dictionary.
        """
        rules = {r.kod_zbiornika.upper(): r for r in TankValidationRepository.get_all_rules()}
        prod_snapshot = {
            _normalize_tank_code(item.get('zbiornik')): item
            for item in AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=True)
            if item.get('zbiornik')
        }

        all_tanks_dict = AgroTanksRepository.get_production_tanks()
        all_tank_codes = all_tanks_dict.get('ALL', [])

        items = []
        for tank_code in all_tank_codes:
            norm_code = _normalize_tank_code(tank_code)
            rule = rules.get(norm_code)
            prod_item = prod_snapshot.get(norm_code, {})
            current_prod_material = prod_item.get('surowiec_nazwa') or prod_item.get('nazwa') or ""
            current_prod_qty = float(prod_item.get('stan_systemowy') or 0.0)

            if rule:
                assigned_material = rule.nazwa_surowca
                is_rule_active = rule.is_active
                rule_id = rule.id
            else:
                # Default: active with current production material if available
                assigned_material = current_prod_material
                is_rule_active = bool(current_prod_material.strip())
                rule_id = None

            # Check if current production matches assigned rule
            is_mismatch = False
            if is_rule_active and assigned_material and current_prod_material:
                norm_assigned = _normalize_name_for_comparison(assigned_material)
                norm_current = _normalize_name_for_comparison(current_prod_material)
                if norm_assigned != norm_current and norm_assigned not in norm_current and norm_current not in norm_assigned:
                    is_mismatch = True

            items.append({
                'kod_zbiornika': norm_code,
                'strefa': _classify_tank_zone(norm_code),
                'rule_id': rule_id,
                'assigned_material': assigned_material,
                'is_rule_active': is_rule_active,
                'opis': rule.opis if rule else "",
                'updated_at': rule.updated_at.strftime('%Y-%m-%d %H:%M') if (rule and rule.updated_at) else "",
                'updated_by': rule.updated_by if rule else "",
                'current_prod_material': current_prod_material,
                'current_prod_qty': current_prod_qty,
                'is_mismatch': is_mismatch,
            })

        # Grouping
        def get_group_name(tank: str) -> str:
            m = re.match(r'([A-Z]+)[ -]?(\d+)', tank.upper())
            if not m:
                return 'Inne Stacje'
            prefix = m.group(1)
            num = int(m.group(2))
            if prefix == 'BB':
                if 1 <= num <= 6:
                    return 'Waga01 (BB01-BB06)'
                if 11 <= num <= 14:
                    return 'Waga02 (BB11-BB14)'
                if 15 <= num <= 22:
                    return 'Waga03 (BB15-BB22)'
                return 'Pozostałe Big-Bag'
            if prefix == 'MZ':
                if 7 <= num <= 10:
                    return 'Waga02 (MZ07-MZ10)'
                if 23 <= num <= 24:
                    return 'Waga03 (MZ23-MZ24)'
                return 'Pozostałe MZ'
            if prefix == 'KO':
                if 1 <= num <= 12:
                    return 'KO - Rząd 1 (KO01-KO12)'
                if 13 <= num <= 24:
                    return 'KO - Rząd 2 (KO13-KO24)'
                if 25 <= num <= 40:
                    return 'KO - Rząd 3 (KO25-KO40)'
                return 'Pozostałe KO'
            return 'Inne Stacje'

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            grp = get_group_name(it['kod_zbiornika'])
            if grp not in grouped:
                grouped[grp] = []
            grouped[grp].append(it)

        dictionary = TankValidationRepository.get_raw_materials_dictionary()

        return {
            'items': items,
            'grouped': grouped,
            'dictionary': dictionary,
        }

    @classmethod
    def save_tank_rule(
        cls,
        kod_zbiornika: str,
        nazwa_surowca: str,
        surowiec_id: Optional[int] = None,
        opis: Optional[str] = None,
        is_active: bool = True,
        user_login: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Save or update validation rule for a specific tank."""
        norm_code = _normalize_tank_code(kod_zbiornika)
        if not norm_code:
            return False, "Nieprawidłowy kod zbiornika."

        norm_name = (nazwa_surowca or "").strip()
        if not norm_name:
            if not is_active:
                TankValidationRepository.delete_rule(norm_code)
                return True, f"Wyłączono blokadę dla zbiornika {norm_code}."
            return False, "Podaj nazwę surowca lub wyłącz blokadę dla tego zbiornika."

        success = TankValidationRepository.upsert_rule(
            kod_zbiornika=norm_code,
            nazwa_surowca=norm_name,
            surowiec_id=surowiec_id,
            opis=opis,
            is_active=is_active,
            updated_by=user_login
        )
        if success:
            return True, f"Zapisano konfigurację zbiornika {norm_code}."
        return False, "Błąd podczas zapisu w bazie danych."

    @classmethod
    def clear_tank_rule(cls, kod_zbiornika: str) -> Tuple[bool, str]:
        """Remove validation rule for a tank."""
        norm_code = _normalize_tank_code(kod_zbiornika)
        if not norm_code:
            return False, "Nieprawidłowy kod zbiornika."

        success = TankValidationRepository.delete_rule(norm_code)
        if success:
            return True, f"Wyczyszczono przypisanie dla zbiornika {norm_code}."
        return False, "Błąd podczas usuwania reguły."

    @classmethod
    def populate_from_active_production(cls, linia: str = 'Agro', user_login: Optional[str] = None) -> Tuple[bool, str, int]:
        """Auto-populate tank rules based on currently active materials in production tanks."""
        snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=False)
        count = 0
        for item in snapshot:
            tank_code = _normalize_tank_code(item.get('zbiornik'))
            raw_material = item.get('surowiec_nazwa') or item.get('nazwa')
            if tank_code and raw_material and float(item.get('stan_systemowy') or 0) > 0:
                TankValidationRepository.upsert_rule(
                    kod_zbiornika=tank_code,
                    nazwa_surowca=raw_material.strip(),
                    surowiec_id=item.get('surowiec_id'),
                    opis="Automatycznie pobrano z bieżącej produkcji",
                    is_active=True,
                    updated_by=user_login or 'system'
                )
                count += 1
        return True, f"Pomyślnie zsynchronizowano {count} zbiorników z aktualną produkcją.", count

    @classmethod
    def validate_tank_material(
        cls,
        kod_zbiornika: str,
        surowiec_nazwa: str,
        surowiec_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate if a raw material is allowed to be dispatched into a tank.

        Returns (is_valid, error_message).
        """
        norm_tank = _normalize_tank_code(kod_zbiornika)
        if not norm_tank:
            return True, None

        rule = TankValidationRepository.get_rule_by_tank(norm_tank)
        assigned_name = ""
        if rule:
            if not rule.is_active:
                return True, None
            assigned_name = (rule.nazwa_surowca or "").strip()
        else:
            # Fallback: check currently active material in production for this tank
            snapshot = AgroTanksService.get_production_inventory_snapshot(show_empty=False)
            for item in snapshot:
                if _normalize_tank_code(item.get('zbiornik')) == norm_tank and float(item.get('stan_systemowy') or 0) > 0:
                    assigned_name = (item.get('surowiec_nazwa') or item.get('nazwa') or "").strip()
                    break

        if not assigned_name:
            # No material configured or active in this tank -> allow
            return True, None

        scanned_name = (surowiec_nazwa or "").strip()

        norm_assigned = _normalize_name_for_comparison(assigned_name)
        norm_scanned = _normalize_name_for_comparison(scanned_name)

        if not norm_scanned:
            return False, f"BŁĄD: Brak nazwy skanowanego surowca do weryfikacji ze zbiornikiem {norm_tank}."

        # Strict match or substring match
        if norm_assigned == norm_scanned or norm_assigned in norm_scanned or norm_scanned in norm_assigned:
            return True, None

        # Disallow dispatch
        error_msg = (
            f"⛔ BŁĄD WALIDACJI ZBIORNIKA: Do stacji/zbiornika {norm_tank} przypisany jest surowiec: "
            f"\"{assigned_name}\". Próba wydania niezgodnego surowca: \"{scanned_name}\" jest zablokowana!"
        )
        return False, error_msg
