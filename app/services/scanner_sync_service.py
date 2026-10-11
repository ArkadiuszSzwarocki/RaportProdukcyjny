from typing import List, Dict, Any
import json
from app.db import get_db_connection
from app.services.scanner_service import ScannerService

class ScannerSyncService:
    """
    Service handling batch synchronization of scans performed in offline mode.
    Guarantees idempotency via unique client_uuid tracking.
    """

    @staticmethod
    def is_event_already_processed(client_uuid: str) -> bool:
        """Check if an event with this client_uuid was already handled."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM scanner_synced_events WHERE client_uuid = %s", (client_uuid,))
            row = cursor.fetchone()
            return row is not None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def record_synced_event(client_uuid: str, scan_action: str, scanned_code: str, user_login: str, status: str = 'PROCESSED', payload: dict = None) -> int:
        """Persist idempotent synchronization entry."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO scanner_synced_events (
                    client_uuid, scan_action, scanned_code, user_login, status, response_payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """
            cursor.execute(query, (
                client_uuid,
                scan_action,
                scanned_code,
                user_login,
                status,
                json.dumps(payload or {})
            ))
            event_id = cursor.lastrowid
            conn.commit()
            return event_id
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def process_sync_batch(events: List[Dict[str, Any]], user_login: str = 'system') -> Dict[str, Any]:
        """
        Processes a batch of offline-buffered scan events.
        Each event item is expected to have:
          - client_uuid (str): Unique client-generated UUID
          - scan_action (str): LOOKUP only; stock mutations require online confirmation
          - scanned_code (str): Barcode / QR / SSCC code
          - timestamp (str): Client scan timestamp
        """
        results = []
        processed_count = 0
        skipped_duplicates = 0

        for evt in events:
            client_uuid = str(evt.get('client_uuid') or '').strip()
            scan_action = str(evt.get('scan_action') or 'LOOKUP').strip().upper()
            scanned_code = str(evt.get('scanned_code') or '').strip()

            if not client_uuid or not scanned_code:
                results.append({
                    'client_uuid': client_uuid,
                    'status': 'INVALID',
                    'message': 'Brak wymaganego client_uuid lub kodu.'
                })
                continue

            if scan_action != 'LOOKUP':
                results.append({
                    'client_uuid': client_uuid,
                    'status': 'INVALID',
                    'message': 'Ta operacja wymaga potwierdzenia online; nie została wykonana.'
                })
                continue
            if len(client_uuid) > 100 or len(scanned_code) > 255:
                results.append({
                    'client_uuid': client_uuid,
                    'status': 'INVALID',
                    'message': 'Identyfikator lub kod przekracza dopuszczalną długość.'
                })
                continue

            # Idempotency check
            if ScannerSyncService.is_event_already_processed(client_uuid):
                skipped_duplicates += 1
                results.append({
                    'client_uuid': client_uuid,
                    'status': 'DUPLICATE_SKIPPED',
                    'message': 'Zdarzenie zostało już wcześniej zsynchronizowane.'
                })
                continue

            # Record a lookup only; never acknowledge a stock mutation here
            lookup_res = ScannerService.lookup_scanned_code(scanned_code)
            
            ScannerSyncService.record_synced_event(
                client_uuid=client_uuid,
                scan_action=scan_action,
                scanned_code=scanned_code,
                user_login=user_login,
                status='PROCESSED',
                payload=lookup_res
            )

            processed_count += 1
            results.append({
                'client_uuid': client_uuid,
                'status': 'SUCCESS',
                'data': lookup_res
            })

        return {
            'total': len(events),
            'processed': processed_count,
            'duplicates_skipped': skipped_duplicates,
            'items': results
        }
