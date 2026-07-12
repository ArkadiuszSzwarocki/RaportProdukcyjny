"""Serwis mixowania palet - pozwala na tworzenie jednej palety MIX z wielu palet zrodlowych."""

from __future__ import annotations

import random
import string
import urllib.parse
from datetime import datetime
from typing import Any

from app.db import get_db_connection, get_table_name
from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService, INVENTORY_SOURCES, HISTORIA_TYP


def generate_mix_pallet_id() -> str:
    """Generuje unikalny 18-znakowy identyfikator palety MIX, np. MIX123456789012345"""
    now = datetime.now()
    timestamp_part = now.strftime('%y%m%d%H%M%S')
    random_part = ''.join(random.choices(string.digits, k=3))
    return f"MIX{timestamp_part}{random_part}"


class PalletMixService:

    @staticmethod
    def mix_pallets(
        components: list[dict[str, Any]],
        mix_name: str,
        user_login: str = 'System',
        linia: str = 'AGRO',
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Zdejmuje wagi z podanych palet (components) i tworzy jedną nową paletę MIX.
        components = [
            {'mother_id': int, 'source': str, 'weight_to_take': float, 'nr_palety': str},
            ...
        ]
        """
        if not components:
            return False, 'Brak składników do mixowania.', None

        if not mix_name or not mix_name.strip():
            mix_name = "MIX"

        total_weight = 0.0
        validated_components = []

        now_dt = datetime.now()
        new_sscc = generate_mix_pallet_id()

        min_termin_przydatnosci = None
        min_data_produkcji = None
        child_lokalizacja = 'BF_MS01'

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            for comp in components:
                mother_id = int(comp.get('mother_id', 0))
                source = str(comp.get('source', '')).strip().lower()
                weight_to_take = round(float(comp.get('weight_to_take', 0)), 3)

                if mother_id <= 0 or weight_to_take <= 0:
                    return False, f"Błędne dane komponentu (ID: {mother_id}, Waga: {weight_to_take}).", None

                pal, pal_linia = PalletSplitService.find_by_id(mother_id, source, requested_linia=linia)
                if not pal or not pal_linia:
                    return False, f"Nie znaleziono palety bazowej (ID: {mother_id}, Źródło: {source}).", None

                if pal.get('is_blocked'):
                    return False, f"Paleta {pal.get('nr_palety')} jest zablokowana i nie może być użyta w mixie.", None

                current_weight = PalletSplitService._get_weight(pal, source)
                if weight_to_take >= current_weight:
                    return (
                        False,
                        f"Brak wystarczającej wagi na palecie {pal.get('nr_palety')} (Żądano: {weight_to_take}, Stan: {current_weight}).",
                        None
                    )

                new_weight = round(current_weight - weight_to_take, 3)
                
                termin = pal.get('termin_przydatnosci') or pal.get('data_przydatnosci')
                if termin:
                    termin_str = str(termin)
                    if not min_termin_przydatnosci or termin_str < min_termin_przydatnosci:
                        min_termin_przydatnosci = termin_str

                data_prod = pal.get('data_produkcji')
                if data_prod:
                    data_prod_str = str(data_prod)
                    if not min_data_produkcji or data_prod_str < min_data_produkcji:
                        min_data_produkcji = data_prod_str

                total_weight += weight_to_take
                
                validated_components.append({
                    'mother_id': mother_id,
                    'mother_sscc': pal.get('nr_palety') or str(mother_id),
                    'source': source,
                    'linia': pal_linia,
                    'pal': pal,
                    'weight_to_take': weight_to_take,
                    'current_weight': current_weight,
                    'new_weight': new_weight,
                    'lokalizacja': pal.get('lokalizacja')
                })

            total_weight = round(total_weight, 3)

            table_mix = get_table_name('magazyn_surowce', linia)
            nr_partii_mix = "MIX"
            
            cursor.execute(
                f"""
                INSERT INTO {table_mix} (
                    nr_palety, nazwa, stan_magazynowy, data_produkcji, data_przydatnosci,
                    nr_partii, lokalizacja, linia, typ_opakowania
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'mix')
                """,
                (
                    new_sscc, mix_name, total_weight,
                    min_data_produkcji, min_termin_przydatnosci,
                    nr_partii_mix, child_lokalizacja, linia
                )
            )
            new_mix_id = cursor.lastrowid

            komentarz_mix = f"Utworzono MIX z: " + ", ".join([f"{c['weight_to_take']}kg z {c['mother_sscc']}" for c in validated_components])
            PalletSplitService._log_historia(
                cursor, new_mix_id, linia, 'surowiec', 'MIX_UTWORZENIE',
                user_login, komentarz_mix, child_lokalizacja, child_lokalizacja
            )
            PalletSplitService._log_magazyn_ruch(
                cursor, linia, new_mix_id, 'MIX_IN', total_weight, total_weight,
                child_lokalizacja, user_login, now_dt, komentarz_mix, mix_name
            )

            results_sources = []
            for comp in validated_components:
                source = comp['source']
                mother_id = comp['mother_id']
                mother_sscc = comp['mother_sscc']
                new_weight = comp['new_weight']
                weight_to_take = comp['weight_to_take']
                linia_zrodlowa = comp['linia']
                pal = comp['pal']
                mother_lokalizacja = comp['lokalizacja']
                typ_palety = HISTORIA_TYP.get(source, 'surowiec')
                product_name = pal.get('nazwa') or pal.get('produkt')

                if source == 'surowiec':
                    table = get_table_name('magazyn_surowce', linia_zrodlowa)
                    cursor.execute(f"UPDATE {table} SET stan_magazynowy = %s WHERE id = %s", (new_weight, mother_id))
                elif source == 'opakowanie':
                    table = get_table_name('magazyn_opakowania', linia_zrodlowa)
                    cursor.execute(f"UPDATE {table} SET stan_magazynowy = %s WHERE id = %s", (new_weight, mother_id))
                elif source == 'dodatek':
                    table = 'magazyn_dodatki'
                    cursor.execute(f"UPDATE {table} SET stan_magazynowy = %s WHERE id = %s", (new_weight, mother_id))
                else:
                    table = get_table_name('magazyn_palety', linia_zrodlowa)
                    cursor.execute(f"UPDATE {table} SET waga_netto = %s WHERE id = %s", (new_weight, mother_id))

                mother_comment = f"Przelano {weight_to_take} kg do palety MIX {new_sscc} (pozostało {new_weight} kg)."
                
                PalletSplitService._log_historia(
                    cursor, mother_id, linia_zrodlowa, typ_palety, 'MIX_ODJECIE',
                    user_login, mother_comment, mother_lokalizacja, mother_lokalizacja
                )
                PalletSplitService._log_magazyn_ruch(
                    cursor, linia_zrodlowa, mother_id, 'MIX_OUT', -weight_to_take, new_weight,
                    mother_lokalizacja, user_login, now_dt, mother_comment, product_name
                )

                results_sources.append({
                    'mother_id': mother_id,
                    'mother_nr_palety': mother_sscc,
                    'mother_new_weight': new_weight,
                    'linia': linia_zrodlowa,
                    'source': source,
                    'waga_odjeta': weight_to_take,
                    'produkt': product_name,
                    'nr_partii': pal.get('nr_partii'),
                    'data_produkcji': pal.get('data_produkcji'),
                    'termin_przydatnosci': pal.get('termin_przydatnosci') or pal.get('data_przydatnosci')
                })

            conn.commit()

            return True, 'Mixowanie zakończone pomyślnie.', {
                'mix_pallet': {
                    'id': new_mix_id,
                    'nr_palety': new_sscc,
                    'waga': total_weight,
                    'linia': linia,
                    'source': 'surowiec',
                    'produkt': mix_name,
                    'nazwa': mix_name,
                    'nr_partii': nr_partii_mix,
                    'data_produkcji': min_data_produkcji,
                    'termin_przydatnosci': min_termin_przydatnosci
                },
                'sources': results_sources
            }
        except Exception as exc:
            conn.rollback()
            raise exc
        finally:
            conn.close()
