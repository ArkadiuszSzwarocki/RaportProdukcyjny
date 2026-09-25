"""Watchdog integration service for centralized error reporting and alerting."""

import time
import threading
import hashlib
import requests
from typing import Optional
from app.config import WATCHDOG_URL


class WatchdogService:
    """Service responsible for dispatching application errors to the external Watchdog service."""

    _last_sent_cache: dict[str, float] = {}
    _cache_lock = threading.Lock()
    _DEDUP_WINDOW_SECONDS = 5.0

    @classmethod
    def send_log(
        cls,
        app_name: str = "RaportProdukcyjny",
        error_type: str = "Unknown Error",
        details: str = "",
        file_path: str = "",
        line_num: str = ""
    ) -> bool:
        """Dispatch error asynchronously in a background daemon thread with deduplication.

        Args:
            app_name: Identifying application name.
            error_type: Classification of the error (e.g. 'Backend Exception', 'JS Error').
            details: Error description or stack trace.
            file_path: Originating file name, URL or path.
            line_num: Line number if available.

        Returns:
            bool: True if queued for dispatch, False if rate-limited or disabled.
        """
        if not WATCHDOG_URL:
            return False

        # Compute deduplication hash to prevent database flooding
        raw_key = f"{app_name}:{error_type}:{file_path}:{line_num}:{str(details)[:120]}"
        dedup_key = hashlib.md5(raw_key.encode("utf-8", errors="ignore")).hexdigest()

        now = time.time()
        with cls._cache_lock:
            last_time = cls._last_sent_cache.get(dedup_key, 0.0)
            if now - last_time < cls._DEDUP_WINDOW_SECONDS:
                return False
            cls._last_sent_cache[dedup_key] = now

            # Clean stale entries if cache grows
            if len(cls._last_sent_cache) > 200:
                cls._last_sent_cache = {
                    k: v for k, v in cls._last_sent_cache.items()
                    if now - v < cls._DEDUP_WINDOW_SECONDS
                }

        payload = {
            "app_name": str(app_name or "RaportProdukcyjny"),
            "error_type": str(error_type or "Unknown Error"),
            "details": str(details or "No details provided"),
            "file_path": str(file_path or ""),
            "line_num": str(line_num or "")
        }

        # Dispatch asynchronously in daemon thread to guarantee zero latency on web workers
        thread = threading.Thread(
            target=cls._perform_post,
            args=(WATCHDOG_URL, payload),
            daemon=True
        )
        thread.start()
        return True

    @classmethod
    def send_error(
        cls,
        error_type: str,
        details: str,
        file_path: str = "",
        line_num: str = "",
        app_name: str = "RaportProdukcyjny"
    ) -> bool:
        """Alias for send_log to maintain backwards compatibility."""
        return cls.send_log(
            app_name=app_name,
            error_type=error_type,
            details=details,
            file_path=file_path,
            line_num=line_num
        )

    @staticmethod
    def _perform_post(url: str, payload: dict) -> None:
        """Internal synchronous POST to Watchdog endpoint with 1.5s timeout."""
        try:
            requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=(1.0, 1.5)
            )
        except Exception:
            # Silent fallback - telemetry failures must never disrupt main application flow
            pass
