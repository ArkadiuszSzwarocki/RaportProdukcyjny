/**
 * Offline Scan Buffer & Idempotent Sync Manager
 * Buffers barcode/SSCC scans only in memory for the lifetime of the current page.
 *
 * Security: mutation payloads must never survive logout/login on a shared
 * workstation, therefore this queue intentionally does not use localStorage or
 * sessionStorage. Legacy persisted queue data is removed on startup.
 */

(function (global) {
    'use strict';

    const LEGACY_STORAGE_KEY = 'rp_offline_scan_buffer';

    try {
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        sessionStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch (e) {
        // Storage can be unavailable; the in-memory queue still works.
    }

    class OfflineScanBuffer {
        constructor() {
            this.queue = [];
            this.isSyncing = false;
            this.initNetworkListeners();
        }

        generateUUID() {
            return 'scan-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        }

        saveQueue() {
            // Deliberately memory-only. Persisting write operations across a
            // session boundary could replay user A's action as user B.
            this.updateUIBadge();
        }

        enqueueScan(code, action = 'LOOKUP') {
            const eventItem = {
                client_uuid: this.generateUUID(),
                scan_action: action,
                scanned_code: String(code).trim(),
                timestamp: new Date().toISOString()
            };
            this.queue.push(eventItem);
            this.saveQueue();
            console.log('[OfflineBuffer] Enqueued scan for current page:', eventItem.client_uuid);

            if (navigator.onLine) {
                this.sync();
            }
            return eventItem;
        }

        async sync() {
            if (this.isSyncing || this.queue.length === 0 || !navigator.onLine) {
                return;
            }

            this.isSyncing = true;
            const payload = { events: [...this.queue] };

            try {
                const response = await fetch('/api/scanner/sync-batch', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        console.log('[OfflineBuffer] Synced successfully:', result.data);
                        this.queue = [];
                        this.saveQueue();
                    }
                } else if (response.status === 401 || response.status === 403) {
                    // Never retain a mutation when the authenticated context is
                    // gone or no longer authorized.
                    this.queue = [];
                    this.saveQueue();
                }
            } catch (err) {
                console.warn('[OfflineBuffer] Sync failed, keeping queue only for this page:', err);
            } finally {
                this.isSyncing = false;
            }
        }

        initNetworkListeners() {
            window.addEventListener('online', () => {
                console.log('[OfflineBuffer] Network restored. Syncing current-page queue...');
                this.sync();
            });

            window.addEventListener('offline', () => {
                console.warn('[OfflineBuffer] Network lost. Buffer remains in memory only.');
                this.updateUIBadge();
            });

            window.addEventListener('pagehide', () => {
                this.queue = [];
            });
        }

        updateUIBadge() {
            let badge = document.getElementById('offline-sync-badge');
            if (!badge) {
                badge = document.createElement('div');
                badge.id = 'offline-sync-badge';
                badge.style.cssText = 'position:fixed;bottom:16px;right:16px;background:#0f172a;color:#fff;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;display:none;z-index:99999;box-shadow:0 4px 12px rgba(0,0,0,0.2);align-items:center;gap:6px;';
                document.body.appendChild(badge);
            }

            const count = this.queue.length;
            if (!navigator.onLine || count > 0) {
                badge.style.display = 'inline-flex';
                badge.style.background = !navigator.onLine ? '#ef4444' : '#f59e0b';
                badge.innerHTML = !navigator.onLine
                    ? `📡 OFFLINE (${count} w buforze tej strony)`
                    : `⏳ Synchronizacja (${count} skanów)`;
            } else {
                badge.style.display = 'none';
            }
        }
    }

    global.offlineScanBuffer = new OfflineScanBuffer();
})(window);
