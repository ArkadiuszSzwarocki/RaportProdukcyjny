/**
 * User-scoped persistent offline mutation store.
 *
 * Queued writes survive page changes and browser restarts, but are isolated by
 * the authenticated user id rendered by the server. A different user gets a
 * different IndexedDB record and cannot accidentally replay the previous
 * user's pending operations with their own session.
 */
(function (global) {
    'use strict';

    const DB_NAME = 'raportprodukcyjny_offline_v2';
    const DB_VERSION = 1;
    const STORE_NAME = 'queues';
    const ALLOWED_QUEUE_KEYS = new Set([
        'agromes_offline_queue',
        'rp_offline_scan_buffer'
    ]);

    const rawUserId = global.__RP_OFFLINE_USER_ID;
    const ownerUserId = /^\d+$/.test(String(rawUserId == null ? '' : rawUserId).trim())
        ? String(rawUserId).trim()
        : '';

    const memoryQueues = new Map();
    const touchedBeforeReady = new Set();
    let db = null;
    let isReady = false;

    function normalizeQueueKey(key) {
        const normalized = String(key || '').trim();
        if (!ALLOWED_QUEUE_KEYS.has(normalized)) {
            throw new Error('Offline mutation queue key is not allowed.');
        }
        return normalized;
    }

    function cloneQueue(queue) {
        try {
            return JSON.parse(JSON.stringify(Array.isArray(queue) ? queue : []));
        } catch (e) {
            return [];
        }
    }

    function parseQueue(value) {
        if (Array.isArray(value)) return cloneQueue(value);
        if (value == null || value === '') return [];
        try {
            const parsed = JSON.parse(String(value));
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function itemIdentity(item) {
        if (!item || typeof item !== 'object') return JSON.stringify(item);
        return String(
            item.client_uuid || item.id || item.uuid ||
            JSON.stringify(item)
        );
    }

    function mergeQueues(storedQueue, pendingQueue) {
        const result = [];
        const seen = new Set();
        [...cloneQueue(storedQueue), ...cloneQueue(pendingQueue)].forEach((item) => {
            const identity = itemIdentity(item);
            if (seen.has(identity)) return;
            seen.add(identity);
            result.push(item);
        });
        return result;
    }

    function storageKey(queueKey) {
        return `${ownerUserId}:${queueKey}`;
    }

    function openDatabase() {
        return new Promise((resolve, reject) => {
            if (!ownerUserId || !('indexedDB' in global)) {
                resolve(null);
                return;
            }

            let request;
            try {
                request = global.indexedDB.open(DB_NAME, DB_VERSION);
            } catch (error) {
                reject(error);
                return;
            }

            request.onupgradeneeded = () => {
                const database = request.result;
                if (!database.objectStoreNames.contains(STORE_NAME)) {
                    database.createObjectStore(STORE_NAME, { keyPath: 'key' });
                }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error('IndexedDB open failed.'));
        });
    }

    function readRecord(queueKey) {
        return new Promise((resolve) => {
            if (!db || !ownerUserId) {
                resolve([]);
                return;
            }
            try {
                const tx = db.transaction(STORE_NAME, 'readonly');
                const request = tx.objectStore(STORE_NAME).get(storageKey(queueKey));
                request.onsuccess = () => resolve(parseQueue(request.result && request.result.queue));
                request.onerror = () => resolve([]);
            } catch (e) {
                resolve([]);
            }
        });
    }

    function writeRecord(queueKey, queue) {
        return new Promise((resolve) => {
            if (!db || !ownerUserId) {
                resolve(false);
                return;
            }
            try {
                const tx = db.transaction(STORE_NAME, 'readwrite');
                tx.objectStore(STORE_NAME).put({
                    key: storageKey(queueKey),
                    owner_user_id: ownerUserId,
                    queue_name: queueKey,
                    queue: cloneQueue(queue),
                    updated_at: new Date().toISOString()
                });
                tx.oncomplete = () => resolve(true);
                tx.onerror = () => resolve(false);
                tx.onabort = () => resolve(false);
            } catch (e) {
                resolve(false);
            }
        });
    }

    function deleteRecord(queueKey) {
        return new Promise((resolve) => {
            if (!db || !ownerUserId) {
                resolve(false);
                return;
            }
            try {
                const tx = db.transaction(STORE_NAME, 'readwrite');
                tx.objectStore(STORE_NAME).delete(storageKey(queueKey));
                tx.oncomplete = () => resolve(true);
                tx.onerror = () => resolve(false);
                tx.onabort = () => resolve(false);
            } catch (e) {
                resolve(false);
            }
        });
    }

    // Remove payloads created by the old unscoped implementation. They cannot
    // be safely attributed to the currently authenticated user.
    try {
        ALLOWED_QUEUE_KEYS.forEach((key) => {
            global.localStorage.removeItem(key);
            global.sessionStorage.removeItem(key);
        });
    } catch (e) {
        // Storage can be disabled by browser policy. IndexedDB remains optional.
    }

    async function initialize() {
        try {
            db = await openDatabase();
            if (!ownerUserId || !db) {
                isReady = true;
                return;
            }

            for (const queueKey of ALLOWED_QUEUE_KEYS) {
                const storedQueue = await readRecord(queueKey);
                const currentQueue = memoryQueues.get(queueKey) || [];
                const merged = touchedBeforeReady.has(queueKey)
                    ? mergeQueues(storedQueue, currentQueue)
                    : storedQueue;
                memoryQueues.set(queueKey, merged);
                if (touchedBeforeReady.has(queueKey)) {
                    await writeRecord(queueKey, merged);
                }
            }
        } catch (error) {
            console.warn('[OfflineStore] IndexedDB unavailable; queue remains page-local.', error);
        } finally {
            isReady = true;
            try {
                global.dispatchEvent(new CustomEvent('rp-offline-store-ready'));
            } catch (e) {
                // CustomEvent can be unavailable in minimal test/browser contexts.
            }
        }
    }

    const ready = initialize();

    const syncStorage = Object.freeze({
        getItem(key) {
            const queueKey = normalizeQueueKey(key);
            const queue = memoryQueues.get(queueKey);
            return queue ? JSON.stringify(queue) : null;
        },
        setItem(key, value) {
            const queueKey = normalizeQueueKey(key);
            const queue = parseQueue(value);
            if (!isReady) touchedBeforeReady.add(queueKey);
            memoryQueues.set(queueKey, queue);
            ready.then(() => writeRecord(queueKey, memoryQueues.get(queueKey) || []));
        },
        removeItem(key) {
            const queueKey = normalizeQueueKey(key);
            if (!isReady) touchedBeforeReady.add(queueKey);
            memoryQueues.set(queueKey, []);
            ready.then(() => deleteRecord(queueKey));
        }
    });

    async function getQueue(queueKey) {
        const normalized = normalizeQueueKey(queueKey);
        await ready;
        return cloneQueue(memoryQueues.get(normalized) || []);
    }

    async function setQueue(queueKey, queue) {
        const normalized = normalizeQueueKey(queueKey);
        await ready;
        const safeQueue = cloneQueue(queue);
        memoryQueues.set(normalized, safeQueue);
        await writeRecord(normalized, safeQueue);
        return cloneQueue(safeQueue);
    }

    async function clearQueue(queueKey) {
        const normalized = normalizeQueueKey(queueKey);
        await ready;
        memoryQueues.set(normalized, []);
        await deleteRecord(normalized);
    }

    function whenReady(callback) {
        return ready.then(() => {
            if (typeof callback === 'function') return callback();
            return undefined;
        });
    }

    function withOwner(options) {
        const headers = new Headers(options && options.headers || {});
        headers.set('X-RP-Offline-Owner', ownerUserId);
        headers.set('X-Requested-With', 'XMLHttpRequest');
        return { ...options, headers, credentials: 'same-origin', redirect: 'error' };
    }

    const api = Object.freeze({
        dbName: DB_NAME,
        ownerUserId,
        ready,
        syncStorage,
        getQueue,
        setQueue,
        clearQueue,
        withOwner,
        whenReady
    });

    Object.defineProperty(global, 'RPOfflineStore', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: api
    });
    Object.defineProperty(global, '__offlineMutationStorage', {
        configurable: false,
        enumerable: false,
        writable: false,
        value: syncStorage
    });
})(window);
