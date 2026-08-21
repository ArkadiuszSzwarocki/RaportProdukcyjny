import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from app.db import get_db_connection, get_table_name
from app.repositories.bucket_maluch_repository import BucketMaluchRepository


class BucketMaluchService:
    """Service handling business logic for Wiaderka z Maluchami."""

    VALID_STATION_REGEX = re.compile(r'^(KO(0[1-9]|[1-3][0-9]|40|\d{1,2})|BB\d{2}|MZ\d{2})$', re.IGNORECASE)
    VALID_MIXER_REGEX = re.compile(r'^(MI\d{2}|MIX\d{2}|MIESZALNIK[-_\s]*\d*)$', re.IGNORECASE)

    @classmethod
    def generate_bucket_sscc(cls, kod_wiadra: str, plan_id: int, dt: Optional[datetime] = None) -> str:
        """
        Generates SSCC for bucket:
        MAL + (nr wiadra 2 cyfry) + (8 cyfr przypadkowych) + (nr zlecenia) + (godzina HHMMSS) + (suma kontrolna jako wynik cyfr godziny)
        """
        if not dt:
            dt = datetime.now()

        norm_code = cls.normalize_bucket_code(kod_wiadra) or str(kod_wiadra).zfill(2)
        random_8 = f"{random.randint(10000000, 99999999)}"
        plan_str = str(plan_id)
        hhmmss = dt.strftime("%H%M%S")
        checksum = str(sum(int(d) for d in hhmmss))

        return f"MAL{norm_code}{random_8}{plan_str}{hhmmss}{checksum}"

    @classmethod
    def normalize_bucket_code(cls, code: str) -> str:
        """Normalizes bucket code to 01-99 format, e.g. '4' -> '04', 'W04' -> '04', 'MAL04...' -> '04'."""
        if not code:
            return ""
        clean = code.strip().upper()
        # Full SSCC MAL04...
        m_sscc = re.match(r'^MAL(\d{2})', clean)
        if m_sscc:
            num = int(m_sscc.group(1))
            if 1 <= num <= 99:
                return f"{num:02d}"
            return ""

        # Match "04", "4", "W04", "WIADRO_04", "WIADRO 04"
        match = re.search(r'(?:WIADRO|W)?[-_\s]*(\d+)', clean)
        if match:
            num = int(match.group(1))
            if 1 <= num <= 99:
                return f"{num:02d}"
        return ""

    @staticmethod
    def normalize_station_code(code: str) -> str:
        """Normalizes station code, e.g. 'ko4' -> 'KO04', 'ko 04' -> 'KO04', up to KO40."""
        if not code:
            return ""
        clean = code.strip().upper().replace(" ", "")
        match = re.search(r'^(KO|BB|MZ)(\d+)$', clean)
        if match:
            prefix = match.group(1)
            num = int(match.group(2))
            return f"{prefix}{num:02d}"
        return clean

    @staticmethod
    def normalize_mixer_code(code: str) -> Optional[str]:
        """
        The ONLY valid mixer in the entire system is strictly 'MI01'.
        Any other code (e.g. MI02, MIX, warehouse rack) is rejected.
        """
        if not code:
            return None
        clean = code.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
        if clean in ('MI01', 'MI1'):
            return 'MI01'
        return None

    @classmethod
    def start_bucket(
        cls,
        kod_wiadra: str,
        plan_id: int,
        linia: str = 'PSD',
        operator_login: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Starts a new bucket or re-opens an existing active bucket for a plan."""
        norm_code = cls.normalize_bucket_code(kod_wiadra)
        if not norm_code:
            return False, "Nieprawidłowy kod wiadra (np. W04, Wiadro 04)", None

        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            cur.execute(f"SELECT id, produkt, status FROM {table_plan} WHERE id = %s", (plan_id,))
            plan = cur.fetchone()
            if not plan:
                alt_linia = 'AGRO' if linia.upper() == 'PSD' else 'PSD'
                alt_table = get_table_name('plan_produkcji', alt_linia)
                cur.execute(f"SELECT id, produkt, status FROM {alt_table} WHERE id = %s", (plan_id,))
                alt_plan = cur.fetchone()
                if alt_plan:
                    plan = alt_plan
                    linia = alt_linia

            if not plan:
                return False, f"Zlecenie #{plan_id} nie istnieje", None
            if str(plan['status']).strip().lower() not in ('w toku', 'zaplanowane'):
                return False, f"Zlecenie #{plan_id} nie jest aktywne (status: {plan['status']})", None

            now = datetime.now()
            data_produkcji = now
            data_przydatnosci = now + timedelta(hours=24)
            nr_sscc = cls.generate_bucket_sscc(norm_code, plan_id, now)

            # Check if bucket is already currently active (not yet dumped to mixer)
            existing = BucketMaluchRepository.find_active_or_completed_by_code(norm_code, linia)
            if existing:
                if existing['plan_id'] != plan_id:
                    return False, f"Wiadro {norm_code} jest już przypisane do innego aktywnego zlecenia #{existing['plan_id']}", None
                if not existing.get('nr_sscc'):
                    BucketMaluchRepository.update_bucket_sscc(existing['id'], nr_sscc, data_produkcji, data_przydatnosci)
                    existing = BucketMaluchRepository.find_by_id(existing['id'])
                return True, f"Kontynuacja naważania wiadra {norm_code}", existing

            # Create new bucket record
            bucket_id = BucketMaluchRepository.create_bucket(
                kod_wiadra=norm_code,
                plan_id=plan_id,
                linia=linia,
                operator_login=operator_login,
                nr_sscc=nr_sscc,
                data_produkcji=data_produkcji,
                data_przydatnosci=data_przydatnosci
            )
            created = BucketMaluchRepository.find_by_id(bucket_id)
            return True, f"Rozpoczęto naważanie wiadra {norm_code}", created
        finally:
            conn.close()

    @classmethod
    def get_station_material(cls, stacja_kod: str, linia: str = 'PSD') -> str:
        """Finds current raw material assigned to the given station (KO01-KO40)."""
        norm_station = cls.normalize_station_code(stacja_kod)
        if not norm_station:
            return ""

        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            # 1. Check magazyn_surowce
            table_sur = get_table_name('magazyn_surowce', linia)
            cur.execute(
                f"SELECT nazwa FROM {table_sur} WHERE (lokalizacja = %s OR lokalizacja = %s) AND (stan_magazynowy > 0 OR stan_magazynowy IS NULL) ORDER BY updated_at DESC, id DESC LIMIT 1",
                (norm_station, norm_station.lower())
            )
            row = cur.fetchone()
            if row and row.get('nazwa'):
                return str(row['nazwa']).strip()

            # 2. Check alternative line
            alt_linia = 'AGRO' if linia.upper() == 'PSD' else 'PSD'
            alt_table = get_table_name('magazyn_surowce', alt_linia)
            cur.execute(
                f"SELECT nazwa FROM {alt_table} WHERE (lokalizacja = %s OR lokalizacja = %s) AND (stan_magazynowy > 0 OR stan_magazynowy IS NULL) ORDER BY updated_at DESC, id DESC LIMIT 1",
                (norm_station, norm_station.lower())
            )
            row = cur.fetchone()
            if row and row.get('nazwa'):
                return str(row['nazwa']).strip()

            # 3. Check magazyn_ruch / magazyn_agro_ruch
            table_ruch = get_table_name('magazyn_ruch', linia)
            cur.execute(
                f"SELECT surowiec_nazwa FROM {table_ruch} WHERE (zbiornik = %s OR lokalizacja = %s) AND surowiec_nazwa IS NOT NULL AND surowiec_nazwa != '' ORDER BY id DESC LIMIT 1",
                (norm_station, norm_station)
            )
            row_ruch = cur.fetchone()
            if row_ruch and row_ruch.get('surowiec_nazwa'):
                return str(row_ruch['surowiec_nazwa']).strip()

            # 4. Check wiaderka_maluchy_pozycje history
            cur.execute(
                "SELECT surowiec_nazwa FROM wiaderka_maluchy_pozycje WHERE stacja_kod = %s AND surowiec_nazwa NOT LIKE 'Surowiec ze stacji%%' ORDER BY id DESC LIMIT 1",
                (norm_station,)
            )
            row_hist = cur.fetchone()
            if row_hist and row_hist.get('surowiec_nazwa'):
                return str(row_hist['surowiec_nazwa']).strip()

            return f"Surowiec ze stacji {norm_station}"
        except Exception:
            return f"Surowiec ze stacji {norm_station}"
        finally:
            conn.close()

    @classmethod
    def add_item_to_bucket(
        cls,
        bucket_id: int,
        stacja_kod: str,
        surowiec_nazwa: Optional[str] = None,
        waga: float = 0.0,
        operator_login: Optional[str] = None,
        linia: str = 'PSD'
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Adds a micro-ingredient from a station (KO01-KO40) to the bucket."""
        bucket = BucketMaluchRepository.find_by_id(bucket_id)
        if not bucket:
            return False, "Wiadro nie istnieje", None
        if bucket['status'] == 'wrzucone_do_mieszalnika':
            return False, "Wiadro zostało już wsypane do mieszalnika!", None

        norm_station = cls.normalize_station_code(stacja_kod)
        if not norm_station or not cls.VALID_STATION_REGEX.match(norm_station):
            return False, f"Nieprawidłowy kod stacji/zbiornika: {stacja_kod}. Dozwolone: KO01-KO40, BB01-BB24", None

        # Automatically resolve raw material name from station if not provided or placeholder
        if not surowiec_nazwa or not surowiec_nazwa.strip():
            bucket_linia = bucket.get('linia') or linia
            surowiec_nazwa = cls.get_station_material(norm_station, bucket_linia)

        try:
            waga_float = float(str(waga).replace(',', '.')) if waga else 0.0
        except (ValueError, TypeError):
            waga_float = 0.0

        item_id = BucketMaluchRepository.add_item(
            bucket_id=bucket_id,
            stacja_kod=norm_station,
            surowiec_nazwa=surowiec_nazwa.strip(),
            waga=waga_float,
            operator_login=operator_login,
        )
        updated_bucket = BucketMaluchRepository.find_by_id(bucket_id)
        return True, f"Dodano: {norm_station} ({surowiec_nazwa})", updated_bucket

    @classmethod
    def remove_item_from_bucket(cls, item_id: int, bucket_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Removes a position from the bucket."""
        bucket = BucketMaluchRepository.find_by_id(bucket_id)
        if not bucket:
            return False, "Wiadro nie istnieje", None
        if bucket['status'] == 'wrzucone_do_mieszalnika':
            return False, "Wiadro zostało już wsypane do mieszalnika", None

        BucketMaluchRepository.remove_item(item_id, bucket_id)
        updated = BucketMaluchRepository.find_by_id(bucket_id)
        return True, "Usunięto pozycję z wiadra", updated

    @classmethod
    def complete_bucket(cls, bucket_id: int, operator_login: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Marks the bucket as fully completed and ready to be dumped into mixer."""
        bucket = BucketMaluchRepository.find_by_id(bucket_id)
        if not bucket:
            return False, "Wiadro nie istnieje", None
        if not bucket.get('pozycje'):
            return False, "Nie można skompletować pustego wiadra! Dodaj przynajmniej jeden składnik ze stacji KO.", None

        BucketMaluchRepository.complete_bucket(bucket_id)
        updated = BucketMaluchRepository.find_by_id(bucket_id)
        return True, f"Wiadro {updated['kod_wiadra']} skompletowane!", updated

    @classmethod
    def delete_bucket(cls, bucket_id: int, operator_login: Optional[str] = None) -> Tuple[bool, str]:
        """Deletes a bucket in progress or completed before dumping."""
        bucket = BucketMaluchRepository.find_by_id(bucket_id)
        if not bucket:
            return False, "Wiadro nie istnieje"
        if bucket['status'] == 'wrzucone_do_mieszalnika':
            return False, "Nie można usunąć wiadra, które zostało już wsypane do mieszalnika!"

        kod = bucket.get('kod_wiadra', '')
        BucketMaluchRepository.delete_bucket(bucket_id)
        return True, f"Usunięto wiadro {kod}"

    @classmethod
    def scan_and_dump_to_mixer(
        cls,
        kod_wiadra: str,
        plan_id: int,
        szarza_id: Optional[int] = None,
        mieszalnik_kod: str = 'MI01',
        operator_login: Optional[str] = None,
        linia: str = 'PSD'
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Operator on Zasyp scans bucket and mixer location (e.g. MI01).
        Marks the bucket as dumped to the active batch/mixer.
        """
        norm_code = cls.normalize_bucket_code(kod_wiadra)
        if not norm_code:
            return False, "Nieprawidłowy kod wiadra (dozwolone wiadra od 01 do 99)", None

        norm_mixer = cls.normalize_mixer_code(mieszalnik_kod)
        if not norm_mixer:
            return False, f"Nieprawidłowy kod '{mieszalnik_kod}'! Wiadra można wrzucić wyłącznie do mieszalnika MI01.", None

        bucket = BucketMaluchRepository.find_active_or_completed_by_code(norm_code, linia)
        if not bucket:
            alt_linia = 'AGRO' if linia.upper() == 'PSD' else 'PSD'
            bucket = BucketMaluchRepository.find_active_or_completed_by_code(norm_code, alt_linia)
            if bucket:
                linia = alt_linia
            else:
                bucket = BucketMaluchRepository.find_active_or_completed_by_code(norm_code)
                if bucket:
                    linia = bucket.get('linia') or linia

        if not bucket:
            latest = BucketMaluchRepository.find_latest_by_code(norm_code)
            if latest:
                if latest.get('status') == 'wrzucone_do_mieszalnika':
                    czas = latest.get('data_zasypania')
                    czas_str = f" ({czas.strftime('%H:%M')})" if hasattr(czas, 'strftime') else ""
                    return False, f"Wiadro {norm_code} zostało już wsypane do mieszalnika {latest.get('mieszalnik_kod') or 'MI01'}{czas_str}!", None
                else:
                    return False, f"Wiadro {norm_code} ma status: {latest.get('status')}", None
            return False, f"Wiadro {norm_code} nie zostało jeszcze przygotowane w module Maluchów.", None

        # Compare plan IDs safely as ints
        try:
            target_plan_id = int(plan_id)
            bucket_plan_id = int(bucket['plan_id'])
            if target_plan_id != bucket_plan_id:
                return False, f"Wiadro {norm_code} jest przypisane do zlecenia #{bucket_plan_id}, a bieżący zasyp to #{target_plan_id}!", None
        except (ValueError, TypeError):
            pass

        if not bucket.get('pozycje'):
            return False, f"Wiadro {norm_code} jest puste (brak składników)!", None

        # Resolve szarza_id if not provided
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            table_szarze = get_table_name('szarze', linia)

            if not szarza_id:
                cur.execute(f"SELECT id FROM {table_szarze} WHERE plan_id = %s ORDER BY data_dodania DESC, id DESC LIMIT 1", (plan_id,))
                last_sz = cur.fetchone()
                if last_sz and last_sz.get('id'):
                    szarza_id = int(last_sz['id'])

            if szarza_id:
                # Do danego zasypu (szarży) można wrzucić tylko jedno wiadro
                cur.execute(
                    """
                    SELECT id, kod_wiadra, data_zasypania FROM wiaderka_maluchy 
                    WHERE szarza_id = %s AND status = 'wrzucone_do_mieszalnika' AND id != %s
                    LIMIT 1
                    """,
                    (szarza_id, bucket['id'])
                )
                existing_dumped = cur.fetchone()
                if existing_dumped:
                    czas = existing_dumped.get('data_zasypania')
                    czas_str = f" (o {czas.strftime('%H:%M')})" if hasattr(czas, 'strftime') and czas else ""
                    return False, f"Do tego zasypu (szarża #{szarza_id}) zostało już wrzucone wiadro {existing_dumped['kod_wiadra']}{czas_str}! Do jednego zasypu można wrzucić tylko jedno wiadro.", None

            # Mark bucket dumped to mixer
            BucketMaluchRepository.dump_bucket_to_mixer(bucket['id'], szarza_id, operator_login, norm_mixer)

            updated = BucketMaluchRepository.find_by_id(bucket['id'])
            return True, f"Potwierdzono: Wiadro {norm_code} wrzucone do mieszalnika {norm_mixer}!", updated
        finally:
            conn.close()

    @classmethod
    def get_plan_maluchy_summary(cls, plan_id: int, linia: str = 'PSD') -> Dict[str, Any]:
        """Returns all buckets for a plan grouped by status."""
        buckets = BucketMaluchRepository.get_buckets_by_plan(plan_id, linia)
        if not buckets:
            alt_linia = 'AGRO' if linia.upper() == 'PSD' else 'PSD'
            alt_buckets = BucketMaluchRepository.get_buckets_by_plan(plan_id, alt_linia)
            if alt_buckets:
                buckets = alt_buckets

        w_trakcie = [b for b in buckets if b['status'] == 'w_trakcie_nawazania']
        skompletowane = [b for b in buckets if b['status'] == 'skompletowane']
        wrzucone = [b for b in buckets if b['status'] == 'wrzucone_do_mieszalnika']

        total_dumped_kg = sum(float(b['waga_calkowita'] or 0) for b in wrzucone)
        total_ready_kg = sum(float(b['waga_calkowita'] or 0) for b in skompletowane)

        return {
            'plan_id': plan_id,
            'linia': linia,
            'w_trakcie': w_trakcie,
            'skompletowane': skompletowane,
            'wrzucone': wrzucone,
            'total_dumped_kg': total_dumped_kg,
            'total_ready_kg': total_ready_kg,
            'all_buckets': buckets,
        }
