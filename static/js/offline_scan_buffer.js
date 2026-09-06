/**
 * Offline Scan Buffer & Idempotent Sync Manager
 * Buffers barcode/SSCC scans locally during Wi-Fi signal loss and automatically syncs when online.
 */

(function (global) {
    'use strict';

    const STORAGE_KEY = 'rp_offline_scan_buffer';

    class OfflineScanBuffer {
        constructor() {
            this.queue = this.loadQueue();
            this.isSyncing = false;
            this.initNetworkListeners();
        }

        generateUUID() {
            return 'scan-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        }

        loadQueue() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                return raw ? JSON.parse(raw) : [];
            } catch (e) {
                console.warn('[OfflineBuffer] Failed to load queue from storage', e);
                return [];
            }
        }

        saveQueue() {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(this.queue));
                this.updateUIBadge();
            } catch (e) {
                console.warn('[OfflineBuffer] Failed to persist queue', e);
            }
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
            console.log('[OfflineBuffer] Enqueued scan:', eventItem);

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
                }
            } catch (err) {
                console.warn('[OfflineBuffer] Sync failed, will retry when online:', err);
            } finally {
                this.isSyncing = false;
            }
        }

        initNetworkListeners() {
            window.addEventListener('online', () => {
                console.log('[OfflineBuffer] Network restored. Syncing...');
                this.sync();
            });

            window.addEventListener('offline', () => {
                console.warn('[OfflineBuffer] Network lost. Operating in offline buffer mode.');
                this.updateUIBadge();
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
                    ? `📡 OFFLINE (${count} w buforze)`
                    : `⏳ Synchronizacja (${count} skanów)`;
            } else {
                badge.style.display = 'none';
            }
        }
    }

    global.offlineScanBuffer = new OfflineScanBuffer();
})(window);
