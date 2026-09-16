"""
Pakowaczka Signal Trap Service
Monitoruje i rejestruje sygnały z pakowaczki / paletyzatora,
pułapkując nadmiarowe lub zduplikowane impulsy i chroniąc przed podwójnym dodawaniem palet.
"""

import logging
from app.core.database import get_db_connection

logger = logging.getLogger('PakowaczkaSignalTrap')

def _ensure_signal_trap_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pakowaczka_signal_trap (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_machine VARCHAR(64) NOT NULL DEFAULT 'PAKOWACZKA',
            plan_id INT NULL,
            produkt VARCHAR(255) NULL,
            global_counter INT NOT NULL DEFAULT 0,
            local_counter INT NOT NULL DEFAULT 0,
            pallet_counter INT NOT NULL DEFAULT 0,
            delta_counter INT NOT NULL DEFAULT 0,
            bpm FLOAT NOT NULL DEFAULT 0,
            status_text VARCHAR(32) NULL,
            decision VARCHAR(64) NOT NULL,
            pallet_id INT NULL,
            nr_palety VARCHAR(64) NULL,
            nr_palety_lp INT NULL,
            details VARCHAR(255) NULL,
            instance_id VARCHAR(128) NULL,
            INDEX idx_plan_ts (plan_id, timestamp),
            INDEX idx_decision (decision),
            INDEX idx_ts (timestamp)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

class PakowaczkaSignalTrapService:
    @staticmethod
    def log_signal(
        decision: str,
        source_machine: str = 'PAKOWACZKA',
        plan_id: int | None = None,
        produkt: str | None = None,
        global_counter: int = 0,
        local_counter: int = 0,
        pallet_counter: int = 0,
        delta_counter: int = 0,
        bpm: float = 0.0,
        status_text: str | None = None,
        pallet_id: int | None = None,
        nr_palety: str | None = None,
        nr_palety_lp: int | None = None,
        details: str | None = None,
        instance_id: str | None = None,
    ):
        """Zapisuje zdarzenie / sygnał do pułapki sygnałów."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            _ensure_signal_trap_table(cursor)
            cursor.execute("""
                INSERT INTO pakowaczka_signal_trap (
                    timestamp, source_machine, plan_id, produkt, global_counter,
                    local_counter, pallet_counter, delta_counter, bpm, status_text,
                    decision, pallet_id, nr_palety, nr_palety_lp, details, instance_id
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(source_machine)[:64],
                plan_id,
                str(produkt)[:255] if produkt else None,
                int(global_counter or 0),
                int(local_counter or 0),
                int(pallet_counter or 0),
                int(delta_counter or 0),
                float(bpm or 0.0),
                str(status_text)[:32] if status_text else None,
                str(decision)[:64],
                pallet_id,
                str(nr_palety)[:64] if nr_palety else None,
                nr_palety_lp,
                str(details)[:255] if details else None,
                str(instance_id)[:128] if instance_id else None,
            ))
            conn.commit()
        except Exception as e:
            logger.warning("Nie udało się zapisać zdarzenia w pakowaczka_signal_trap: %s", e)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def get_recent_signals(limit: int = 50) -> list[dict]:
        """Pobiera ostatnie zarejestrowane sygnały i pułapki."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            _ensure_signal_trap_table(cursor)
            cursor.execute("""
                SELECT * FROM pakowaczka_signal_trap
                ORDER BY id DESC
                LIMIT %s
            """, (int(limit),))
            return cursor.fetchall() or []
        except Exception as e:
            logger.warning("Błąd odczytu pakowaczka_signal_trap: %s", e)
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
