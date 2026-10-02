"""Add durable auto-label intents and unique print job keys without engine conversion."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.db import get_db_connection
from app.services.auto_label_service import ensure_auto_label_schema


if __name__ == '__main__':
    conn = get_db_connection()
    try:
        ensure_auto_label_schema(conn.cursor())
        conn.commit()
        print('Auto-label recovery schema ready; existing pallets unchanged.')
    finally:
        conn.close()
