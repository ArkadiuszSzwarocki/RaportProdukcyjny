/**
 * Offline Scan Buffer & Idempotent Sync Manager
 *
 * Scans are persisted in the shared user-scoped IndexedDB store, so they
 * survive navigation, refresh and browser restart. They can only be loaded by
 * the same authenticated user id that created them.
 */
(function (global) {
    'use strict';

    const QUEUE_KEY = 'rp_offline_scan_buffer';

    function cloneQueue(queue) {
        try {
            return JSON.parse(JSON.stringify(Array.isArray(queue) ? queue : []));
        } catch (e) {
            return [];
        }
    }

    function mergeQueues(first, second) {
        const seen = new Set();
        const result = [];
        [...cloneQueue(first), ...cloneQueue(second)].forEach((item) => {
            const identity = String(item && (item.client_uuid || item.id) || JSON.stringify(item));
            if (seen.has(identity)) return;
            seen.add(identity);
            result.push(item);
        });
        return result;
    }

    class OfflineScanBuffer {
        constructor() {
            this.queue = [];
            this.isSyncing = false;
            this.authBlocked = false;
            this.initNetworkListeners();
            this.ready = this.restoreQueue();
            this.ready.then(() => {
                this.updateUIBadge();
                if (navigator.onLine) this.sync();
            });
        }

        generateUUID() {
            if (global.crypto && typeof global.crypto.randomUUID === 'function') {
                return 'scan-' + global.crypto.randomUUID();
            }
            return 'scan-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11);
        }

        async restoreQueue() {
            const pendingCreatedBeforeRestore = cloneQueue(this.queue);
            if (!global.RPOfflineStore || !global.RPOfflineStore.ownerUserId) {
                this.queue = pendingCreatedBeforeRestore;
                return;
            }

            try {
                const storedQueue = await global.RPOfflineStore.getQueue(QUEUE_KEY);
                this.queue = mergeQueues(storedQueue, pendingCreatedBeforeRestore);
                await global.RPOfflineStore.setQueue(QUEUE_KEY, this.queue);
                console.log(`[OfflineBuffer] Restored ${this.queue.length} scan(s) for current user.`);
            } catch (error) {
                console.warn('[OfflineBuffer] Failed to restore IndexedDB queue.', error);
                this.queue = pendingCreatedBeforeRestore;
            }
        }

        async persistQueue() {
            if (!global.RPOfflineStore || !global.RPOfflineStore.ownerUserId) {
                this.updateUIBadge();
                return;
            }
            try {
                await global.RPOfflineStore.setQueue(QUEUE_KEY, this.queue);
            } catch (error) {
                console.warn('[OfflineBuffer] Failed to persist queue.', error);
            }
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
            void this.persistQueue();
            console.log('[OfflineBuffer] Enqueued durable scan:', eventItem.client_uuid);

            if (navigator.onLine && !this.authBlocked) {
                void this.sync();
            }
            return eventItem;
        }

        async sync() {
            await this.ready;
            if (this.isSyncing || this.authBlocked || this.queue.length === 0 || !navigator.onLine) {
                return;
            }

            this.isSyncing = true;
            const payload = { events: cloneQueue(this.queue) };

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
                        await this.persistQueue();
                    }
                } else if (response.status === 401 || response.status === 403) {
                    // Keep the queue under its original owner. Do not replay it
                    // under another session; a same-user login/page reload can
                    // resume it because IndexedDB is partitioned by user id.
                    this.authBlocked = true;
                    console.warn('[OfflineBuffer] Sync paused until the owner authenticates again.');
                }
            } catch (err) {
                console.warn('[OfflineBuffer] Sync failed; durable queue kept for later.', err);
            } finally {
                this.isSyncing = false;
                this.updateUIBadge();
            }
        }

        initNetworkListeners() {
            window.addEventListener('online', () => {
                console.log('[OfflineBuffer] Network restored. Syncing durable queue...');
                void this.sync();
            });

            window.addEventListener('offline', () => {
                console.warn('[OfflineBuffer] Network lost. Scans remain in IndexedDB.');
                this.updateUIBadge();
            });

            window.addEventListener('pagehide', () => {
                // Best-effort persistence. The queue is intentionally NOT
                // cleared because offline work must survive navigation.
                void this.persistQueue();
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
                    ? `📡 OFFLINE (${count} zapisano lokalnie)`
                    : `⏳ Synchronizacja (${count} skanów)`;
            } else {
                badge.style.display = 'none';
            }
        }
    }

    global.offlineScanBuffer = new OfflineScanBuffer();
})(window);
