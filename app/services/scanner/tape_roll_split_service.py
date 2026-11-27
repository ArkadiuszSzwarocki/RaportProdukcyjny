"""Command service for registering sub-rolls inside a master packaging pallet."""
from __future__ import annotations

from app import db as app_db
from app.dto.packaging_subroll_dto import SubrollInsertSpec
from app.dto.tape_split_dto import TapePrintOptions, TapeSplitCommand
from app.repositories.packaging_subroll_repository import PackagingSubrollRepository
from app.services.inwentaryzacja_service import InwentaryzacjaService
from app.services.print_server import get_printer
from app.services.scanner.packaging_subroll_commands import generate_subroll_code
from app.services.scanner.packaging_subroll_queries import PackagingSubrollQueries
from app.services.warehouse_history.movement_recorder import MovementRecorder


class TapeRollSplitService:
    """Validate and register Nested HU sub-rolls inside a master packaging pallet."""

    @staticmethod
    def parse_command(payload: dict) -> tuple[TapeSplitCommand | None, str | None]:
        """Parse and validate incoming JSON request payload."""
        pallet_id = payload.get('pallet_id') or payload.get('surowiec_id') or payload.get('id')
        nr_palety = str(payload.get('nr_palety') or payload.get('sscc') or '').strip()
        raw_rolls = payload.get('rolls_szt')

        if not pallet_id and not nr_palety:
            return None, 'Brak identyfikatora palety taśmy.'
        if not isinstance(raw_rolls, list) or len(raw_rolls) < 1:
            return None, 'Podaj co najmniej 1 podrolkę do rozpisania.'

        cleaned_rolls: list[int] = []
        for idx, raw_val in enumerate(raw_rolls, start=1):
            try:
                qty = int(round(float(str(raw_val).replace(',', '.'))))
            except (TypeError, ValueError):
                return None, f'Nieprawidłowa ilość dla rolki #{idx}.'
            if qty <= 0:
                return None, f'Ilość dla rolki #{idx} musi być większa od 0.'
            cleaned_rolls.append(qty)

        try:
            copies = max(1, int(payload.get('copies') or 2))
        except (TypeError, ValueError):
            copies = 2

        printing = TapePrintOptions(
            enabled=bool(payload.get('print_labels', True)),
            printer_ip=payload.get('printer_ip') or payload.get('override_ip'),
            printer_name=payload.get('printer_name') or payload.get('override_name'),
            copies=copies,
        )
        command = TapeSplitCommand(
            pallet_id=pallet_id,
            nr_palety=nr_palety,
            rolls_szt=cleaned_rolls,
            bag_weight_kg=payload.get('bag_weight_kg'),
            save_bag_weight=bool(payload.get('save_bag_weight', False)),
            printing=printing,
        )
        return command, None

    @staticmethod
    def _fetch_locked_pallet(cur, command: TapeSplitCommand) -> dict | None:
        """Lock and return target packaging pallet row."""
        if command.pallet_id:
            cur.execute(
                "SELECT * FROM magazyn_opakowania WHERE id = %s LIMIT 1 FOR UPDATE",
                (command.pallet_id,),
            )
            return cur.fetchone()
        cur.execute(
            "SELECT * FROM magazyn_opakowania WHERE UPPER(nr_palety) = %s LIMIT 1 FOR UPDATE",
            (command.nr_palety.upper(),),
        )
        return cur.fetchone()

    @staticmethod
    def _insert_subrolls(
        cur,
        pal_id: int,
        rolls_szt: list[int],
        bag_weight_kg: float | str | None,
        worker: str,
    ) -> list[dict]:
        """Insert NA_PALECIE sub-roll records inside the master pallet."""
        start_nr = PackagingSubrollRepository.next_roll_number(cur, pal_id)
        bag_kg = None
        if bag_weight_kg not in (None, ''):
            try:
                parsed_kg = float(str(bag_weight_kg).replace(',', '.'))
                if parsed_kg > 0:
                    bag_kg = parsed_kg
            except (TypeError, ValueError):
                bag_kg = None

        created: list[dict] = []
        for offset, roll_qty in enumerate(rolls_szt):
            roll_nr = start_nr + offset
            roll_code = generate_subroll_code(roll_nr)
            est_kg = round(roll_qty * bag_kg, 3) if bag_kg else None
            sub_id = PackagingSubrollRepository.insert_subroll(
                cur,
                SubrollInsertSpec(
                    parent_id=pal_id,
                    kod_rolki=roll_code,
                    nr_rolki=roll_nr,
                    ilosc_szt=roll_qty,
                    waga_kg=est_kg,
                    zrodlo='PODZIAL',
                    created_by=worker,
                ),
            )
            created.append({
                'id': sub_id,
                'nr_palety': roll_code,
                'kod_rolki': roll_code,
                'nr_rolki': roll_nr,
                'stan_magazynowy': roll_qty,
                'ilosc_szt': roll_qty,
                'is_source': False,
                'is_subroll': True,
            })
        return created

    @staticmethod
    def _print_roll_labels(
        rolls: list[dict],
        pal_linia: str,
        opts: TapePrintOptions,
    ) -> tuple[int, list[str]]:
        """Queue ZPL label printing for newly registered ROL... sub-rolls."""
        if not opts.enabled:
            return 0, []
        printed_count = 0
        print_errors: list[str] = []
        printer = get_printer()
        for item in rolls:
            code = item['kod_rolki']
            try:
                lbl_data = PackagingSubrollQueries.get_subroll_label_data(code, linia=pal_linia)
                if lbl_data:
                    ok, msg = printer.print_pallet_label(
                        lbl_data,
                        override_ip=opts.printer_ip,
                        override_name=opts.printer_name,
                        copies=opts.copies,
                    )
                    if ok:
                        printed_count += 1
                    else:
                        print_errors.append(f"{code}: {msg}")
            except Exception as err:  # pylint: disable=broad-exception-caught
                print_errors.append(f"{code}: {err}")
        return printed_count, print_errors

    @staticmethod
    def _save_optional_bag_weight(command: TapeSplitCommand, tape_name: str, worker: str) -> None:
        """Persist updated single-bag weight when requested by the operator."""
        if not command.save_bag_weight or command.bag_weight_kg in (None, ''):
            return
        try:
            InwentaryzacjaService.save_tape_conversions_bulk(
                [{'nazwa': tape_name, 'waga_worka_kg': command.bag_weight_kg}],
                user_login=worker,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    @staticmethod
    def _validate_split_pool(
        cur,
        pal: dict | None,
        total_szt: int,
    ) -> tuple[int, tuple[dict, int] | None]:
        """Verify master pallet stock and unassigned pool capacity."""
        if not pal:
            return 0, (
                {
                    'success': False,
                    'error': 'Nie znaleziono palety taśmy w magazynie opakowań.',
                },
                404,
            )

        source_qty_int = int(round(float(pal.get('stan_magazynowy') or 0)))
        if source_qty_int <= 0:
            return 0, ({'success': False, 'error': 'Paleta ma zerowy stan magazynowy.'}, 400)

        existing = PackagingSubrollRepository.list_active_by_parent(cur, int(pal['id']))
        already_assigned = sum(int(r.get('ilosc_szt') or 0) for r in existing)
        available_pool = max(source_qty_int - already_assigned, 0)
        if total_szt > available_pool:
            err = (
                f"Suma wpisanych podrolek ({total_szt} szt) przekracza nierozpisaną pulę "
                f"na palecie ({available_pool} szt z {source_qty_int} szt) "
                f"o {total_szt - available_pool} szt."
            )
            return 0, ({'success': False, 'error': err}, 400)
        return available_pool - total_szt, None

    @staticmethod
    def _build_split_response(
        command: TapeSplitCommand,
        pal: dict,
        result_rolls: list[dict],
        remaining_szt: int,
        worker_login: str,
    ) -> tuple[dict, int]:
        """Run post-commit optional side effects and build API response dictionary."""
        total_szt = sum(command.rolls_szt)
        src_sscc = pal.get('nr_palety') or f"OPK-{pal['id']}"
        pal_linia = pal.get('linia') or 'AGRO'

        TapeRollSplitService._save_optional_bag_weight(command, pal['nazwa'], worker_login)
        printed_count, print_errors = TapeRollSplitService._print_roll_labels(
            result_rolls,
            pal_linia,
            command.printing,
        )

        if len(result_rolls) == 1:
            first_nr = result_rolls[0]['nr_rolki']
            msg = f"Dodano podrolkę #{first_nr} ({total_szt} szt) do palety {src_sscc}"
        else:
            msg = (
                f"Dodano {len(result_rolls)} podrolek "
                f"(razem {total_szt} szt) do palety {src_sscc}"
            )
        if remaining_szt > 0:
            msg += f" — nierozpisane na palecie: {remaining_szt} szt"

        return {
            'success': True,
            'message': msg,
            'source_sscc': src_sscc,
            'remaining_szt': remaining_szt,
            'rolls': result_rolls,
            'printed_count': printed_count,
            'print_errors': print_errors,
        }, 200

    @staticmethod
    def execute(
        command: TapeSplitCommand,
        worker_login: str,
        default_linia: str,
    ) -> tuple[dict, int]:
        """Register sub-rolls inside master pallet without duplicating pallets on racks."""
        total_szt = sum(command.rolls_szt)
        conn = app_db.get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            PackagingSubrollRepository.ensure_table(cur)
            pal = TapeRollSplitService._fetch_locked_pallet(cur, command)
            remaining_szt, err_resp = TapeRollSplitService._validate_split_pool(cur, pal, total_szt)
            if err_resp or not pal:
                conn.rollback()
                return err_resp or ({'success': False, 'error': 'Brak palety.'}, 404)

            old_qty = float(pal.get('stan_magazynowy') or 0)
            src_sscc = pal.get('nr_palety') or f"OPK-{pal['id']}"
            result_rolls = TapeRollSplitService._insert_subrolls(
                cur,
                int(pal['id']),
                command.rolls_szt,
                command.bag_weight_kg,
                worker_login,
            )
            MovementRecorder.record_movement(
                pal['id'],
                pal.get('linia') or default_linia,
                'opakowanie',
                'ROZPISANIE_PODROLEK',
                pal.get('lokalizacja') or 'MOP01',
                pal.get('lokalizacja') or 'MOP01',
                (
                    f"Przypisano {len(result_rolls)} podrolek ({total_szt} szt) "
                    f"do palety {src_sscc}; nierozpisana pula: {remaining_szt} szt"
                ),
                worker_login,
                src_sscc,
                cursor=cur,
                connection=conn,
                quantity_before=old_qty,
                quantity_after=old_qty,
            )
            pal['linia'] = pal.get('linia') or default_linia
            conn.commit()
        except Exception as err:  # pylint: disable=broad-exception-caught
            conn.rollback()
            return {'success': False, 'error': f'Błąd rozpisywania podrolek: {err}'}, 500
        finally:
            conn.close()

        return TapeRollSplitService._build_split_response(
            command,
            pal,
            result_rolls,
            remaining_szt,
            worker_login,
        )
