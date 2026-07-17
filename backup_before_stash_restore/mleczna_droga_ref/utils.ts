
import { RawMaterialLogEntry, FinishedGoodItem, PackagingMaterialLogEntry } from '../types';

/**
 * Zwraca liczbę dni w danym miesiącu i roku.
 */
export const getDaysInMonth = (month: number, year: number): number => {
    // month jest 1-indexed (1-12)
    return new Date(year, month, 0).getDate();
};

/**
 * Generuje 18-cyfrowy identyfikator palety (format SSCC-podobny).
 * Liczony od daty 1982-06-07 w milisekundach.
 */
export const generate18DigitId = (): string => {
    const epoch1982 = new Date('1982-06-07T00:00:00Z').getTime();
    const diff = Math.max(0, Date.now() - epoch1982);
    const base = `${diff}`; 
    const needed = 18 - base.length;
    
    if (needed > 0) {
        const randomPart = Math.floor(Math.random() * Math.pow(10, needed))
            .toString()
            .padStart(needed, '0');
        return `${base}${randomPart}`;
    }
    
    return base.substring(0, 18);
};

export const normalizePrintServerUrl = (url: string): string => {
    if (!url) return '';
    let cleanUrl = url.trim().replace(/\/+$/, '');
    if (cleanUrl.includes('192.168.1.143')) return 'https://192.168.1.143:3001';
    if (!cleanUrl.startsWith('http://') && !cleanUrl.startsWith('https://')) cleanUrl = `https://${cleanUrl}`;
    let protocol = cleanUrl.startsWith('http://') ? 'http://' : 'https://';
    let hostPart = cleanUrl.replace(/^(https?):\/\//, '');
    if (hostPart && !hostPart.includes(':')) hostPart = `${hostPart}:3001`;
    return `${protocol}${hostPart}`;
};

export const formatDate = (dateString: string | undefined, includeTime: boolean = false, includeSeconds: boolean = true): string => {
    if (!dateString) return '---';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return '---';
        const options: Intl.DateTimeFormatOptions = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        };
        if (includeTime) {
            options.hour = '2-digit';
            options.minute = '2-digit';
            if (includeSeconds) options.second = '2-digit';
        }
        return date.toLocaleString('pl-PL', options);
    } catch (e) {
        return '---';
    }
};

export const normalizeLocationId = (locationId: string): string => {
    const trimmed = locationId.trim().toUpperCase();
    if (trimmed === 'BFMS01') return 'BF_MS01';
    if (trimmed === 'BFMP01') return 'BF_MP01';
    return trimmed;
};

export const getBlockInfo = (item: any): { isBlocked: boolean; reason: string | null; type: 'M' | 'A' | null } => {
    if (!item) return { isBlocked: false, reason: null, type: null };
    const isRaw = 'palletData' in item;
    const today = new Date().toISOString().split('T')[0];
    const isBlockedManually = isRaw ? item.palletData?.isBlocked : (item.status === 'blocked' || item.isBlocked);
    const blockReasonManual = isRaw ? item.palletData?.blockReason : item.blockReason;
    let isExpired = false;
    const expiryDateString = isRaw ? item.palletData?.dataPrzydatnosci : item.expiryDate;
    if (expiryDateString) {
        const datePart = typeof expiryDateString === 'string' && expiryDateString.includes('T') ? expiryDateString.split('T')[0] : expiryDateString;
        isExpired = datePart < today;
    }
    if (isBlockedManually) return { isBlocked: true, reason: blockReasonManual || 'Blokada ręczna', type: 'M' };
    if (isExpired) return { isBlocked: true, reason: `Przeterminowana (${formatDate(expiryDateString)})`, type: 'A' };
    return { isBlocked: false, reason: null, type: null };
};

export const getActionLabel = (action: string): string => {
    const ACTION_LABELS: Record<string, string> = {
        'added_new_to_delivery_buffer': 'Przyjęcie (Bufor)',
        'move': 'Przesunięcie',
        'lab_pallet_blocked': 'Zablokowanie (Lab)',
        'lab_pallet_unblocked': 'Zwolnienie (Lab)',
        'consumed_in_production': 'Zużycie produkcyjne',
        'produced': 'Wyprodukowano',
        'consumed_and_archived': 'Wydana (Archiwum)',
        'correction': 'Korekta'
    };
    return ACTION_LABELS[action] || action;
};

export const getFinishedGoodStatusLabel = (status: string): string => {
    switch (status) {
        case 'pending_label': return 'Oczekuje na etykietę';
        case 'available': return 'Dostępna';
        case 'blocked': return 'Zablokowana';
        default: return status;
    }
};

export const getExpiryStatus = (palletData: any, warningDays: number, criticalDays: number): 'expired' | 'critical' | 'warning' | 'default' => {
    if (!palletData?.dataPrzydatnosci) return 'default';
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const expiryDate = new Date(palletData.dataPrzydatnosci); expiryDate.setHours(0, 0, 0, 0);
    const diffDays = Math.ceil((expiryDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return 'expired';
    if (diffDays < criticalDays) return 'critical';
    if (diffDays < warningDays) return 'warning';
    return 'default';
};

export const getExpiryStatusClass = (status: string): string => {
    switch (status) {
        case 'expired': return 'text-red-600 font-bold';
        case 'critical': return 'text-orange-600 font-bold';
        case 'warning': return 'text-yellow-600 font-semibold';
        default: return 'text-gray-600';
    }
};

export const formatProductionTime = (minutes: number): string => {
    if (minutes <= 0) return '0m';
    const h = Math.floor(minutes / 60); const m = Math.round(minutes % 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
};

export const getProductionRunStatusLabel = (status: string): string => {
    switch (status) {
        case 'planned': return 'Zaplanowane';
        case 'ongoing': return 'W trakcie';
        case 'completed': return 'Zakończone';
        default: return status;
    }
};

export const exportToCsv = (filename: string, rows: any[]) => {
    if (!rows || !rows.length) return;
    const separator = ';';
    const keys = Object.keys(rows[0]);
    const csvContent = [keys.join(separator), ...rows.map(row => keys.map(k => `"${String(row[k] || '').replace(/"/g, '""')}"`).join(separator))].join('\n');
    const blob = new Blob(["\uFEFF" + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
};

export const getExpiryStatusText = (status: string): string => {
    switch (status) {
        case 'expired': return 'PRZETERMINOWANA';
        case 'critical': return 'TERMIN KRYTYCZNY';
        case 'warning': return 'KRÓTKI TERMIN';
        default: return '';
    }
};

export const getAdjustmentOrderStatusLabel = (status: string) => {
    switch (status) {
        case 'planned': return { label: 'Zaplanowane', color: 'bg-gray-200 text-gray-800' };
        case 'material_picking': return { label: 'Kompletacja', color: 'bg-blue-100 text-blue-800' };
        case 'processing': return { label: 'W trakcie', color: 'bg-indigo-100 text-indigo-800' };
        case 'completed': return { label: 'Zakończone', color: 'bg-green-100 text-green-800' };
        case 'cancelled': return { label: 'Anulowane', color: 'bg-red-100 text-red-800' };
        default: return { label: status, color: 'bg-gray-100 text-gray-800' };
    }
};

export const getDispatchOrderStatusLabel = (status: string): string => {
    switch (status) {
        case 'planned': return 'Zaplanowane';
        case 'in_fulfillment': return 'W realizacji';
        case 'completed': return 'Zakończone';
        case 'cancelled': return 'Anulowane';
        default: return status;
    }
};

export const getMixingTaskStatusLabel = (status: string): string => {
    switch (status) {
        case 'planned': return 'Zaplanowane';
        case 'ongoing': return 'W toku';
        case 'completed': return 'Zakończone';
        case 'cancelled': return 'Anulowane';
        default: return status;
    }
};

export const getDeliveryStatusLabel = (status: string): string => {
    switch (status) {
        case 'REGISTRATION': return 'Rejestracja';
        case 'PENDING_LAB': return 'Oczekuje na Lab';
        case 'PENDING_WAREHOUSE': return 'Oczekuje na Magazyn';
        case 'COMPLETED': return 'Zakończona';
        default: return status;
    }
};

export const getArchivizationCountdown = (completedAt?: string): string | null => {
    if (!completedAt) return null;
    const now = new Date();
    const completionDate = new Date(completedAt);
    const archDate = new Date(completionDate.getTime() + 7 * 24 * 60 * 60 * 1000);
    const diff = archDate.getTime() - now.getTime();

    if (diff <= 0) return null;

    const days = Math.floor(diff / (24 * 60 * 60 * 1000));
    const hours = Math.floor((diff % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));

    if (days > 0) return `${days}d ${hours}h`;
    const minutes = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000));
    return `${hours}h ${minutes}m`;
};
