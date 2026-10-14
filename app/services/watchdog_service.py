"""Watchdog integration service for centralized error reporting and alerting."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import time
from typing import Optional

import requests

from app.config import WATCHDOG_URL


_WATCHDOG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='watchdog')


class WatchdogService:
    """Dispatch application errors without creating an unbounded thread per event."""

    _last_sent_cache: dict[str, float] = {}
    _cache_lock = threading.Lock()
    _DEDUP_WINDOW_SECONDS = 5.0

    @classmethod
    def send_log(
        cls,
        app_name: str = 'RaportProdukcyjny',
        error_type: str = 'Unknown Error',
        details: str = '',
        file_path: str = '',
        line_num: str = '',
    ) -> bool:
        """Queue telemetry in a bounded executor with short-window deduplication."""
        if not WATCHDOG_URL:
            return False

        raw_key = f'{app_name}:{error_type}:{file_path}:{line_num}:{str(details)[:120]}'
        dedup_key = hashlib.sha256(raw_key.encode('utf-8', errors='ignore')).hexdigest()

        now = time.time()
        with cls._cache_lock:
            last_time = cls._last_sent_cache.get(dedup_key, 0.0)
            if now - last_time < cls._DEDUP_WINDOW_SECONDS:
                return False
            cls._last_sent_cache[dedup_key] = now
            if len(cls._last_sent_cache) > 200:
                cls._last_sent_cache = {
                    key: value
                    for key, value in cls._last_sent_cache.items()
                    if now - value < cls._DEDUP_WINDOW_SECONDS
                }

        payload = {
            'app_name': str(app_name or 'RaportProdukcyjny'),
            'error_type': str(error_type or 'Unknown Error'),
            'details': str(details or 'No details provided'),
            'file_path': str(file_path or ''),
            'line_num': str(line_num or ''),
        }

        try:
            _WATCHDOG_EXECUTOR.submit(cls._perform_post, WATCHDOG_URL, payload)
            return True
        except RuntimeError:
            return False

    @classmethod
    def send_error(
        cls,
        error_type: str,
        details: str,
        file_path: str = '',
        line_num: str = '',
        app_name: str = 'RaportProdukcyjny',
    ) -> bool:
        return cls.send_log(
            app_name=app_name,
            error_type=error_type,
            details=details,
            file_path=file_path,
            line_num=line_num,
        )

    @staticmethod
    def _perform_post(url: str, payload: dict) -> None:
        """Send one telemetry record with strict network timeouts."""
        try:
            requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=(1.0, 1.5),
            )
        except requests.RequestException:
            # Telemetry failures must not disrupt the main application flow.
            pass
