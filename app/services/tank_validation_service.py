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
                if norm_assigned != norm_current:
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
        norm_code = AgroTanksRepository.normalize_production_tank(kod_zbiornika)
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
            tank_code = AgroTanksRepository.normalize_production_tank(item.get('zbiornik'))
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
        if not kod_zbiornika or not str(kod_zbiornika).strip():
            return False, "⚠️ Brak kodu stacji/zbiornika!"

        from app.utils.location_validator import validate_production_tank
        is_tank_ok, norm_tank, tank_err = validate_production_tank(kod_zbiornika)
        if not is_tank_ok:
            return False, tank_err

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

        # A shared word or a partial name does not identify the assigned material.
        if norm_assigned == norm_scanned:
            return True, None

        # Disallow dispatch
        error_msg = (
            f"⛔ BŁĄD WALIDACJI ZBIORNIKA: Do stacji/zbiornika {norm_tank} przypisany jest surowiec: "
            f"\"{assigned_name}\". Próba wydania niezgodnego surowca: \"{scanned_name}\" jest zablokowana!"
        )
        return False, error_msg

    @classmethod
    def get_material_tank_map(cls, linia: str = 'AGRO') -> Dict[str, List[Dict[str, Any]]]:
        """Return a mapping of normalized raw material name -> list of tanks where it is active or assigned."""
        by_material: Dict[str, Dict[str, Dict[str, Any]]] = {}

        def _register(raw_name: Optional[str], tank_code: Optional[str], source: str, amount_kg: Optional[float] = None) -> None:
            norm_name = _normalize_name_for_comparison(raw_name)
            norm_tank = _normalize_tank_code(tank_code)
            if not norm_name or not norm_tank:
                return
            tanks_for_mat = by_material.setdefault(norm_name, {})
            existing = tanks_for_mat.get(norm_tank)
            if existing:
                if existing['source'] != source:
                    existing['source'] = 'both'
                if amount_kg is not None:
                    existing['amount_kg'] = round(float(existing.get('amount_kg') or 0) + float(amount_kg), 2)
            else:
                tanks_for_mat[norm_tank] = {
                    'code': norm_tank,
                    'source': source,
                    'amount_kg': round(float(amount_kg), 2) if amount_kg is not None else None,
                }

        try:
            for rule in TankValidationRepository.get_all_rules():
                if rule.is_active and rule.nazwa_surowca and rule.kod_zbiornika:
                    _register(rule.nazwa_surowca, rule.kod_zbiornika, 'rule', None)
        except Exception:
            pass

        try:
            snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia or 'AGRO', show_empty=False)
            for item in snapshot or []:
                amount = float(item.get('stan_systemowy') or 0)
                if amount <= 0:
                    continue
                tank_code = AgroTanksRepository.normalize_production_tank(item.get('zbiornik'))
                raw_name = item.get('surowiec_nazwa') or item.get('nazwa')
                _register(raw_name, tank_code, 'production', amount)
        except Exception:
            pass

        return {
            norm_name: [tanks[code] for code in sorted(tanks.keys())]
            for norm_name, tanks in by_material.items()
        }

    @classmethod
    def get_tanks_for_materials(cls, material_names, linia: str = 'AGRO') -> Dict[str, Dict[str, Any]]:
        """Resolve tank locations and validation status for a list of raw material names."""
        tank_map = cls.get_material_tank_map(linia=linia)
        result: Dict[str, Dict[str, Any]] = {}
        for raw_name in material_names or []:
            key = str(raw_name or '').strip()
            if not key or key in result:
                continue
            norm_name = _normalize_name_for_comparison(key)
            tanks = tank_map.get(norm_name, [])
            result[key] = {
                'is_assigned': bool(tanks),
                'tanks': tanks,
                'tank_codes': [t['code'] for t in tanks],
            }
        return result

    @classmethod
    def get_maluchy_used_tanks(cls, cursor, plan_id: int, szarza_id: Optional[int] = None) -> List[str]:
        """Return distinct tank/station codes with premix/premiks ingredients already dumped via Maluchy."""
        try:
            if szarza_id:
                cursor.execute(
                    """
                    SELECT DISTINCT UPPER(TRIM(COALESCE(p.stacja_kod, ''))) AS stacja_kod
                    FROM wiaderka_maluchy w
                    JOIN wiaderka_maluchy_pozycje p ON p.wiaderko_id = w.id
                    WHERE w.plan_id = %s
                      AND w.szarza_id = %s
                      AND w.status = 'wrzucone_do_mieszalnika'
                      AND TRIM(COALESCE(p.stacja_kod, '')) <> ''
                      AND (LOWER(COALESCE(p.surowiec_nazwa, '')) LIKE %s
                           OR LOWER(COALESCE(p.surowiec_nazwa, '')) LIKE %s)
                    ORDER BY stacja_kod ASC
                    """,
                    (plan_id, szarza_id, '%premix%', '%premiks%'),
                )
            else:
                cursor.execute(
                    """
                    SELECT DISTINCT UPPER(TRIM(COALESCE(p.stacja_kod, ''))) AS stacja_kod
                    FROM wiaderka_maluchy w
                    JOIN wiaderka_maluchy_pozycje p ON p.wiaderko_id = w.id
                    WHERE w.plan_id = %s
                      AND w.status = 'wrzucone_do_mieszalnika'
                      AND TRIM(COALESCE(p.stacja_kod, '')) <> ''
                      AND (LOWER(COALESCE(p.surowiec_nazwa, '')) LIKE %s
                           OR LOWER(COALESCE(p.surowiec_nazwa, '')) LIKE %s)
                    ORDER BY stacja_kod ASC
                    """,
                    (plan_id, '%premix%', '%premiks%'),
                )
            return [
                _normalize_tank_code(row[0] if not isinstance(row, dict) else row.get('stacja_kod'))
                for row in (cursor.fetchall() or [])
                if (row[0] if not isinstance(row, dict) else row.get('stacja_kod'))
            ]
        except Exception:
            return []

    @classmethod
    def group_dosypka_materials(
        cls,
        material_names,
        material_tanks: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        linia: str = 'AGRO',
        maluchy_tanks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Group allowed raw materials into BB/MZ/KO tank-assigned buckets and unassigned items."""
        tank_map = material_tanks if material_tanks is not None else cls.get_material_tank_map(linia=linia)
        maluchy_set = {_normalize_tank_code(c) for c in (maluchy_tanks or []) if c}
        buckets: Dict[str, List[Dict[str, Any]]] = {'BB': [], 'MZ': [], 'KO': [], 'INNE': []}
        assigned_names: List[str] = []
        unassigned_names: List[str] = []
        seen_assigned = set()

        for raw_name in material_names or []:
            name = str(raw_name or '').strip()
            if not name:
                continue
            tanks = tank_map.get(_normalize_name_for_comparison(name), [])
            if not tanks:
                unassigned_names.append(name)
                continue

            if name.casefold() not in seen_assigned:
                seen_assigned.add(name.casefold())
                assigned_names.append(name)

            codes = [str(t.get('code') or '').strip().upper() for t in tanks if t.get('code')]
            by_prefix: Dict[str, List[str]] = {}
            for code in codes:
                prefix = code[:2] if code[:2] in ('BB', 'MZ', 'KO') else 'INNE'
                by_prefix.setdefault(prefix, []).append(code)

            is_premix_name = 'premix' in name.casefold() or 'premiks' in name.casefold()
            for prefix, group_codes in by_prefix.items():
                matched_maluchy = [code for code in group_codes if is_premix_name and code in maluchy_set]
                buckets[prefix].append({
                    'name': name,
                    'tanks': group_codes,
                    'all_tanks': codes,
                    'in_maluchy': bool(matched_maluchy),
                    'maluchy_tanks': matched_maluchy,
                })

        group_defs = [
            ('BB', 'Zbiorniki BB'),
            ('MZ', 'Zbiorniki MZ'),
            ('KO', 'Zbiorniki KO'),
            ('INNE', 'Inne zbiorniki'),
        ]
        groups = []
        for code, title in group_defs:
            items = sorted(buckets[code], key=lambda item: item['name'].casefold())
            if items or code in ('BB', 'MZ', 'KO'):
                groups.append({'code': code, 'title': title, 'items': items})

        return {
            'assigned_names': sorted(assigned_names, key=str.casefold),
            'unassigned_names': sorted(unassigned_names, key=str.casefold),
            'maluchy_tanks': sorted(maluchy_set),
            'groups': groups,
        }
