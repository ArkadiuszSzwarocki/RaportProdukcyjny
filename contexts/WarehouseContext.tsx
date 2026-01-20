
import React, { createContext, useContext, useMemo, PropsWithChildren, useState, useCallback, useEffect } from 'react';
import { RawMaterialLogEntry, Delivery, ExpiringPalletInfo, WarehouseNavLayoutItem, FinishedGoodItem, User, InventorySession, PackagingMaterialLogEntry, AnalysisResult, Document, Supplier, Customer, PalletBalance, PalletTransaction, LocationDefinition, WarehouseInfo, PalletType, View, Permission, DeliveryStatus, AnalysisRange, AnalysisRangeHistoryEntry, DeliveryCorrection } from '../../types';
import { useAuth } from './AuthContext';
import { INITIAL_RAW_MATERIALS, INITIAL_DELIVERIES, INITIAL_PACKAGING_MATERIALS, INITIAL_PRODUCTS, INITIAL_FINISHED_GOODS } from '../../src/initialData';
import { DEFAULT_WAREHOUSE_NAV_LAYOUT, BUFFER_MS01_ID, BUFFER_MP01_ID, SOURCE_WAREHOUSE_ID_MS01, SUB_WAREHOUSE_ID, OSIP_WAREHOUSE_ID, MDM01_WAREHOUSE_ID, KO01_WAREHOUSE_ID, PSD_WAREHOUSE_ID, MGW01_WAREHOUSE_ID, MGW02_WAREHOUSE_ID, MGW01_RECEIVING_AREA_ID, DEFAULT_SETTINGS, SUPPLIERS_LIST, VIRTUAL_LOCATION_ARCHIVED, MOP01_WAREHOUSE_ID, DEFAULT_ANALYSIS_RANGES, API_BASE_URL } from '../../constants';
import { getBlockInfo, getExpiryStatus, generate18DigitId } from '../../src/utils';
import { logger } from '../../utils/logger';

const INITIAL_LOCATIONS: LocationDefinition[] = [
    { id: SOURCE_WAREHOUSE_ID_MS01, name: 'Magazyn Główny', type: 'warehouse', capacity: 500 },
    { id: OSIP_WAREHOUSE_ID, name: 'Magazyn Zewnętrzny OSiP', type: 'warehouse', capacity: 1000 },
    { id: BUFFER_MS01_ID, name: 'Bufor Przyjęć Surowców', type: 'zone', capacity: 50 },
    { id: BUFFER_MP01_ID, name: 'Bufor Produkcyjny', type: 'zone', capacity: 50 },
    { id: SUB_WAREHOUSE_ID, name: 'Magazyn Produkcyjny', type: 'warehouse', capacity: 200 },
    { id: MDM01_WAREHOUSE_ID, name: 'Magazyn Dodatków', type: 'warehouse', capacity: 100 },
    { id: MOP01_WAREHOUSE_ID, name: 'Magazyn Opakowań', type: 'warehouse', capacity: 150 },
    { id: KO01_WAREHOUSE_ID, name: 'Strefa Konfekcji', type: 'zone', capacity: 30 },
    { id: PSD_WAREHOUSE_ID, name: 'Strefa PSD', type: 'zone', capacity: 40 },
    { id: MGW01_WAREHOUSE_ID, name: 'Wyroby Gotowe MGW01', type: 'warehouse', capacity: 400 },
    { id: MGW02_WAREHOUSE_ID, name: 'Wyroby Gotowe MGW02', type: 'warehouse', capacity: 400 },
    { id: MGW01_RECEIVING_AREA_ID, name: 'Przyjęcia Wyrobów Gotowych', type: 'zone', capacity: 20 },
    { id: 'R01', name: 'Regał R01', type: 'rack', capacity: 80 },
    { id: 'R02', name: 'Regał R02', type: 'rack', capacity: 80 },
    { id: 'R03', name: 'Regał R03', type: 'rack', capacity: 80 },
    { id: 'R04', name: 'Regał R04', type: 'rack', capacity: 80 },
    { id: 'R07', name: 'Regał R07', type: 'rack', capacity: 80 },
];

export interface WarehouseContextValue {
    rawMaterialsLogList: RawMaterialLogEntry[];
    setRawMaterialsLogList: React.Dispatch<React.SetStateAction<RawMaterialLogEntry[]>>;
    finishedGoodsList: FinishedGoodItem[];
    setFinishedGoodsList: React.Dispatch<React.SetStateAction<FinishedGoodItem[]>>;
    packagingMaterialsLog: PackagingMaterialLogEntry[];
    setPackagingMaterialsLog: React.Dispatch<React.SetStateAction<PackagingMaterialLogEntry[]>>;
    deliveries: Delivery[];
    setDeliveries: React.Dispatch<React.SetStateAction<Delivery[]>>;
    expiringPalletsDetails: ExpiringPalletInfo[];
    expiryWarningDays: number;
    setExpiryWarningDays: React.Dispatch<React.SetStateAction<number>>;
    expiryCriticalDays: number;
    setExpiryCriticalDays: React.Dispatch<React.SetStateAction<number>>;
    warehouseNavLayout: WarehouseNavLayoutItem[];
    setWarehouseNavLayout: React.Dispatch<React.SetStateAction<WarehouseNavLayoutItem[]>>;
    findPalletByUniversalId: (id: string) => { item: any; type: 'raw' | 'fg' | 'pkg' } | null;
    allProducts: any[];
    inventorySessions: InventorySession[];
    analysisRanges: AnalysisRange[];
    refreshRawMaterials: () => Promise<void>;
    setAnalysisRanges: React.Dispatch<React.SetStateAction<AnalysisRange[]>>;
    analysisRangesHistory: AnalysisRangeHistoryEntry[];
    logAnalysisRangeChange: (data: Omit<AnalysisRangeHistoryEntry, 'id' | 'timestamp' | 'user'>) => void;
    handleUpdateDeliveryStatus: (deliveryId: string, newStatus: DeliveryStatus) => { success: boolean, message: string, newPallets?: any[] };
    handleSaveLabNotes: (itemId: string, isRaw: boolean, notes: string) => { success: boolean; message: string; type: 'success' | 'error' };
    handleAddDocument: (itemId: string, itemType: 'raw' | 'fg', file: File) => { success: boolean; message: string; type: 'success' | 'error' };
    handleDeleteDocument: (itemId: string, itemType: 'raw' | 'fg', documentName: string) => { success: boolean; message: string; type: 'success' | 'error' };
    handleSaveAnalysisResults: (itemId: string, itemType: 'raw' | 'fg', results: AnalysisResult[]) => { success: boolean; message: string; type: 'success' | 'error' };
    allManageableLocations: LocationDefinition[];
    combinedWarehouseInfos: WarehouseInfo[];
    handleArchiveItem: (id: string, type: string) => { success: boolean; message: string };
    handleRestoreItem: (id: string, type: string) => { success: boolean; message: string };
    validatePalletMove: (item: any, locationId: string) => { isValid: boolean; message: string; rulesChecked: any[] };
    handleUniversalMove: (id: string, type: string, locationId: string, notes?: string) => { success: boolean; message: string };
    handleBlockPallet: (itemId: string, itemType: string, reason: string, user: User) => { success: boolean; message: string; };
    handleUnblockPallet: (itemId: string, itemType: string, currentUser: User, notes?: string, newDate?: string) => { success: boolean; message: string; };
    handleStartInventorySession: (name: string, locationIds: string[]) => { success: boolean; message: string; };
    handleCancelInventorySession: (sessionId: string) => { success: boolean; message: string; };
    suppliers: Supplier[];
    customers: Customer[];
    palletBalances: PalletBalance[];
    palletTransactions: PalletTransaction[];
    handleAddSupplier: (name: string) => { success: boolean, message: string };
    handleDeleteSupplier: (value: string) => { success: boolean, message: string };
    handleUpdateSupplier: (value: string, data: Supplier) => { success: boolean, message: string };
    handleLookupNip: (nip: string) => Promise<{ success: boolean, message: string, data?: Partial<Supplier> }>;
    handleAddCustomer: (name: string) => { success: boolean, message: string };
    handleDeleteCustomer: (value: string) => { success: boolean, message: string };
    handleUpdateCustomer: (value: string, data: Customer) => { success: boolean, message: string };
    handleAddPalletTransaction: (data: any) => { success: boolean, message: string };
    handleAddLocation: (loc: LocationDefinition) => { success: boolean; message: string };
    handleUpdateLocation: (id: string, loc: LocationDefinition) => { success: boolean; message: string };
    handleDeleteLocation: (id: string) => { success: boolean; message: string };
    handleDeleteDelivery: (deliveryId: string) => { success: boolean; message: string };
    handleSaveDelivery: (delivery: Delivery) => { success: boolean; message: string; delivery?: Delivery };
    handleRecordInventoryScan: (sessionId: string, locationId: string, palletId: string, qty: number, force: boolean) => { success: boolean; message: string; warning?: string };
    handleUpdateInventoryLocationStatus: (sessionId: string, locationId: string, status: 'pending' | 'scanned') => void;
    handleResolveMissingPallet: (sessionId: string, palletId: string, lastKnownLocation: string) => { success: boolean, message: string };
    handleResolveUnexpectedPallet: (sessionId: string, palletId: string, newLocation: string) => { success: boolean, message: string };
    handleFinalizeInventorySession: (sessionId: string) => { success: boolean; message: string };
    handleCompleteScanningSession: (sessionId: string) => { success: boolean; message: string };
}

export const WarehouseContext = createContext<WarehouseContextValue | undefined>(undefined);

export const useWarehouseContext = (): WarehouseContextValue => {
    const context = useContext(WarehouseContext);
    if (!context) throw new Error('useWarehouseContext must be used within a WarehouseProvider');
    return context;
};

export const WarehouseProvider: React.FC<PropsWithChildren> = ({ children }) => {
    const { currentUser } = useAuth();
    
    const [rawMaterialsLogList, setRawMaterialsLogList] = useState<RawMaterialLogEntry[]>([]);
    const [finishedGoodsList, setFinishedGoodsList] = useState<FinishedGoodItem[]>(INITIAL_FINISHED_GOODS);
    const [deliveries, setDeliveries] = useState<Delivery[]>(INITIAL_DELIVERIES);
    const [packagingMaterialsLog, setPackagingMaterialsLog] = useState<PackagingMaterialLogEntry[]>(INITIAL_PACKAGING_MATERIALS);
    const [inventorySessions, setInventorySessions] = useState<InventorySession[]>([]);
    const [allProducts] = useState<any[]>(INITIAL_PRODUCTS);
    const [warehouseNavLayout, setWarehouseNavLayout] = useState<WarehouseNavLayoutItem[]>(DEFAULT_WAREHOUSE_NAV_LAYOUT);
    
    const [expiryWarningDays, setExpiryWarningDays] = useState<number>(DEFAULT_SETTINGS.EXPIRY_WARNING_DAYS);
    const [expiryCriticalDays, setExpiryCriticalDays] = useState<number>(DEFAULT_SETTINGS.EXPIRY_CRITICAL_DAYS);

    const [suppliers, setSuppliers] = useState<Supplier[]>(SUPPLIERS_LIST);
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [palletBalances, setPalletBalances] = useState<PalletBalance[]>([]);
    const [palletTransactions, setPalletTransactions] = useState<PalletTransaction[]>([]);
    
    const [managedLocations, setManagedLocations] = useState<LocationDefinition[]>(INITIAL_LOCATIONS);

    // Pobierz lokalizacje z API (jeśli backend dostępny)
    const fetchManagedLocations = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/warehouse-locations`);
            if (!res.ok) return;
            const data = await res.json();
            // Mapuj rekordy DB na LocationDefinition używane w aplikacji
            const mapped: LocationDefinition[] = (data || []).map((r: any) => {
                const code = r.code || (`WL-${r.id}`);
                let type: LocationDefinition['type'] = 'zone';
                const zone = (r.zone || '').toString().toLowerCase();
                if (zone.includes('magaz') || (r.warehouse_id && r.warehouse_id !== null)) type = 'warehouse';
                else if (zone.includes('rega') || /^r\d+/i.test(code)) type = 'rack';
                else if (zone.includes('szt') || zone.includes('bin') || zone.includes('pola')) type = 'bin';

                return {
                    id: code,
                    name: r.name || r.display_name || `Lok_${code}`,
                    type,
                    capacity: r.capacity || 0,
                    description: r.zone || undefined,
                } as LocationDefinition;
            });

            // Jeśli otrzymano cokolwiek, nadpisz lokalny stan
            if (mapped.length > 0) setManagedLocations(mapped);
        } catch (err) {
            console.warn('Nie udało się pobrać lokalizacji z API, używane lokalne wartości:', err);
        }
    }, []);

    // Pobierz listę dostawców z backendu
    const fetchSuppliers = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/suppliers`);
            if (!res.ok) return;
            const data = await res.json();
            const mapped: Supplier[] = (data || []).map((s: any) => ({
                value: String(s.id),
                label: s.name,
                nip: s.nip || undefined,
                address: s.address || undefined,
                city: s.city || undefined,
                zip: s.postal_code || undefined,
                email: s.email || undefined,
                phone: s.phone || undefined,
                notes: s.notes || undefined
            }));
            setSuppliers(mapped);
        } catch (err) {
            console.warn('Nie udało się pobrać dostawców z API:', err);
        }
    }, []);

    const [analysisRanges, setAnalysisRanges] = useState<AnalysisRange[]>(DEFAULT_ANALYSIS_RANGES);
    const [analysisRangesHistory, setAnalysisRangesHistory] = useState<AnalysisRangeHistoryEntry[]>([]);

    // Pobieranie surowców z API
    const fetchRawMaterials = useCallback(async () => {
        const tryFetch = async (url: string) => {
            try {
                const r = await fetch(url);
                return r;
            } catch (e) {
                return null;
            }
        };

        try {
            // 1) Primary: configured API_BASE_URL
            let response = await tryFetch(`${API_BASE_URL}/raw-materials`);

            // 2) If response missing, 404 or HTML (vite dev server returned index.html), fallback to relative /api
            const isHtml = (res: Response | null) => {
                if (!res) return false;
                const ct = res.headers.get('content-type') || '';
                return ct.includes('text/html');
            };

            if (!response || response.status === 404 || isHtml(response)) {
                response = await tryFetch('/api/raw-materials');
            }

            // 3) Final fallback: direct localhost backend
            if (!response || response.status === 404 || isHtml(response)) {
                response = await tryFetch('http://localhost:5001/api/raw-materials');
            }

            if (response && response.ok) {
                const data = await response.json();
                // Transformuj dane z bazy na format aplikacji
                const transformed: RawMaterialLogEntry[] = data.map((row: any) => ({
                    id: row.id,
                    palletData: {
                        nrPalety: row.nrPalety,
                        nazwa: row.nazwa,
                        dataProdukcji: row.dataProdukcji,
                        dataPrzydatnosci: row.dataPrzydatnosci,
                        initialWeight: parseFloat(row.initialWeight),
                        currentWeight: parseFloat(row.currentWeight),
                        isBlocked: row.isBlocked === 1,
                        blockReason: row.blockReason,
                        batchNumber: row.batchNumber,
                        packageForm: row.packageForm,
                        unit: row.unit,
                        labAnalysisNotes: row.labAnalysisNotes,
                    },
                    currentLocation: row.currentLocation,
                    locationHistory: [],
                    dateAdded: row.createdAt,
                    lastValidatedAt: row.updatedAt,
                }));
                setRawMaterialsLogList(transformed);
            }
        } catch (err) {
            console.error('Błąd pobierania surowców z API:', err);
            logger.logError(err as Error, 'WarehouseContext:fetchRawMaterials');
        }
    }, []);

    // Pobierz dane na starcie i co 5 sekund
    useEffect(() => {
        fetchRawMaterials(); // Pobierz na starcie
        fetchManagedLocations();
        fetchSuppliers();
        const interval = setInterval(() => {
            fetchRawMaterials();
            // odśwież dostawców co 30s w tle
        }, 5000); // Odśwież co 5 sekund

        const suppliersInterval = setInterval(() => {
            fetchSuppliers();
        }, 30000);

        return () => {
            clearInterval(interval);
            clearInterval(suppliersInterval);
        };
    }, [fetchManagedLocations, fetchSuppliers]);

    const logAnalysisRangeChange = useCallback((data: Omit<AnalysisRangeHistoryEntry, 'id' | 'timestamp' | 'user'>) => {
        const newEntry: AnalysisRangeHistoryEntry = {
            id: `range-hist-${Date.now()}`,
            timestamp: new Date().toISOString(),
            user: currentUser?.username || 'system',
            ...data
        };
        setAnalysisRangesHistory(prev => [newEntry, ...prev].slice(0, 100));
    }, [currentUser, setAnalysisRangesHistory]);

    const combinedWarehouseInfos = useMemo((): WarehouseInfo[] => {
        const baseInfos: Record<string, { label: string, view: View, isLink?: boolean }> = {
            'all': { label: 'Wszystkie Magazyny', view: View.AllWarehousesView },
            [SOURCE_WAREHOUSE_ID_MS01]: { label: 'Magazyn Główny (MS01)', view: View.SourceWarehouseMS01 },
            [OSIP_WAREHOUSE_ID]: { label: 'Magazyn Zewnętrzny (OSiP)', view: View.OsipWarehouse },
            [BUFFER_MS01_ID]: { label: 'Bufor Przyjęć Surowców (BF_MS01)', view: View.BufferMS01View },
            [BUFFER_MP01_ID]: { label: 'Bufor Produkcyjny (BF_MP01)', view: View.BufferMP01View },
            [SUB_WAREHOUSE_ID]: { label: 'Magazyn Produkcyjny (MP01)', view: View.SubWarehouseMP01 },
            [MDM01_WAREHOUSE_ID]: { label: 'Magazyn Dodatków (MDM01)', view: View.MDM01View },
            [KO01_WAREHOUSE_ID]: { label: 'Strefa Konfekcji (KO01)', view: View.KO01View },
            [PSD_WAREHOUSE_ID]: { label: 'Magazyn PSD', view: View.PSD_WAREHOUSE },
            [MOP01_WAREHOUSE_ID]: { label: 'Magazyn Opakowań (MOP01)', view: View.MOP01View },
            [MGW01_RECEIVING_AREA_ID]: { label: 'Strefa Przyjęć WG', view: View.MGW01_Receiving },
            [MGW01_WAREHOUSE_ID]: { label: 'Wyroby Gotowe (MGW01)', view: View.MGW01 },
            [MGW02_WAREHOUSE_ID]: { label: 'Wyroby Gotowe (MGW02)', view: View.MGW02 },
            'pending_labels': { label: 'Etykiety Oczekujące', view: View.PendingLabels }
        };

        const dynamicInfos: WarehouseInfo[] = managedLocations
            .filter(loc => loc.type === 'rack' || loc.type === 'zone' || loc.type === 'bin')
            .map(loc => ({
                id: loc.id,
                label: loc.name,
                view: View.LocationDetail,
                isLocationDetailLink: true
            }));

        const staticInfos: WarehouseInfo[] = Object.entries(baseInfos).map(([id, info]) => ({
            id,
            label: info.label,
            view: info.view,
            isLocationDetailLink: info.isLink
        }));

        return [...staticInfos, ...dynamicInfos];
    }, [managedLocations]);

    const findPalletByUniversalId = useCallback((id: string) => {
        const raw = (rawMaterialsLogList || []).find(p => p.id === id || p.palletData.nrPalety === id);
        if (raw) return { item: raw, type: 'raw' as const };
        const fg = (finishedGoodsList || []).find(p => p.id === id || p.finishedGoodPalletId === id);
        if (fg) return { item: fg, type: 'fg' as const };
        const pkg = (packagingMaterialsLog || []).find(p => p.id === id);
        if (pkg) return { item: pkg, type: 'pkg' as const };
        return null;
    }, [rawMaterialsLogList, finishedGoodsList, packagingMaterialsLog]);

    const expiringPalletsDetails = useMemo((): ExpiringPalletInfo[] => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const allPallets = [
            ...(rawMaterialsLogList || []).map(p => ({ pallet: p, isRaw: true })),
            ...(finishedGoodsList || []).map(p => ({ pallet: p, isRaw: false })),
        ];
        return allPallets.map(({ pallet, isRaw }) => {
            const expiryDateStr = isRaw ? (pallet as RawMaterialLogEntry).palletData.dataPrzydatnosci : (pallet as FinishedGoodItem).expiryDate;
            if (!expiryDateStr) return null;
            const expiryDate = new Date(expiryDateStr);
            const daysLeft = Math.floor((expiryDate.getTime() - today.getTime()) / (1000 * 3600 * 24));
            let status: 'expired' | 'critical' | 'warning' | 'default' = 'default';
            if (daysLeft < 0) status = 'expired';
            else if (daysLeft < expiryCriticalDays) status = 'critical';
            else if (daysLeft < expiryWarningDays) status = 'warning';
            if (status !== 'default') return { pallet, daysLeft, status: status as any, isRaw };
            return null;
        }).filter((p): p is ExpiringPalletInfo => p !== null).sort((a, b) => a.daysLeft - b.daysLeft);
    }, [rawMaterialsLogList, finishedGoodsList, expiryWarningDays, expiryCriticalDays]);

    const validatePalletMove = useCallback((item: any, locationId: string) => {
        const { isBlocked, reason } = getBlockInfo(item);
        if (isBlocked) return { isValid: false, message: `Paleta zablokowana: ${reason}`, rulesChecked: [] };
        if (item.currentLocation === locationId) return { isValid: false, message: "Paleta już jest w tej lokalizacji.", rulesChecked: [] };
        return { isValid: true, message: "OK", rulesChecked: [] };
    }, []);

    const handleUniversalMove = useCallback((id: string, type: string, locationId: string, notes?: string) => {
        const timestamp = new Date().toISOString();
        const moveEntry = { movedBy: currentUser?.username || 'system', movedAt: timestamp, targetLocation: locationId, action: 'move', notes };
        if (type === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: locationId, locationHistory: [...p.locationHistory, { ...moveEntry, previousLocation: p.currentLocation }] } : p));
        } else if (type === 'fg') {
            setFinishedGoodsList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: locationId, locationHistory: [...(p.locationHistory || []), { ...moveEntry, previousLocation: p.currentLocation }] } : p));
        } else {
            setPackagingMaterialsLog(prev => prev.map(p => p.id === id ? { ...p, currentLocation: locationId, locationHistory: [...p.locationHistory, { ...moveEntry, previousLocation: p.currentLocation }] } : p));
        }
        return { success: true, message: "Przeniesiono pomyślnie." };
    }, [currentUser, setRawMaterialsLogList, setFinishedGoodsList, setPackagingMaterialsLog]);

    const handleBlockPallet = useCallback((itemId: string, itemType: string, reason: string, user: User) => {
        const timestamp = new Date().toISOString();
        if (itemType === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === itemId ? {
                ...p, 
                palletData: { ...p.palletData, isBlocked: true, blockReason: reason },
                locationHistory: [...p.locationHistory, { movedBy: user.username, movedAt: timestamp, action: 'lab_pallet_blocked', notes: reason, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === itemId ? {
                ...p, 
                isBlocked: true, status: 'blocked', blockReason: reason,
                locationHistory: [...p.locationHistory, { movedBy: user.username, movedAt: timestamp, action: 'finished_good_blocked', notes: reason, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        }
        return { success: true, message: "Zablokowano paletę." };
    }, [setRawMaterialsLogList, setFinishedGoodsList]);

    const handleUnblockPallet = useCallback((itemId: string, itemType: string, user: User, notes?: string, newDate?: string) => {
        const timestamp = new Date().toISOString();
        if (itemType === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === itemId ? {
                ...p, 
                palletData: { ...p.palletData, isBlocked: false, dataPrzydatnosci: newDate || p.palletData.dataPrzydatnosci },
                locationHistory: [...p.locationHistory, { movedBy: user.username, movedAt: timestamp, action: 'lab_pallet_unblocked', notes, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === itemId ? {
                ...p, 
                isBlocked: false, status: 'available', expiryDate: newDate || p.expiryDate,
                locationHistory: [...p.locationHistory, { movedBy: user.username, movedAt: timestamp, action: 'lab_pallet_unblocked', notes, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        }
        return { success: true, message: "Zwolniono paletę." };
    }, [setRawMaterialsLogList, setFinishedGoodsList]);

    const handleArchiveItem = useCallback((id: string, type: string) => {
        const timestamp = new Date().toISOString();
        const target = VIRTUAL_LOCATION_ARCHIVED;
        if (type === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: target, locationHistory: [...p.locationHistory, { movedBy: currentUser?.username || 'system', movedAt: timestamp, action: 'archive', previousLocation: p.currentLocation, targetLocation: target }] } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: target, locationHistory: [...(p.locationHistory || []), { movedBy: currentUser?.username || 'system', movedAt: timestamp, action: 'archive', previousLocation: p.currentLocation, targetLocation: target }] } : p));
        }
        return { success: true, message: "Zarchiwizowano." };
    }, [currentUser, setRawMaterialsLogList, setFinishedGoodsList]);

    const handleRestoreItem = useCallback((id: string, type: string) => {
        const timestamp = new Date().toISOString();
        const target = SOURCE_WAREHOUSE_ID_MS01;
        if (type === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: target, locationHistory: [...p.locationHistory, { movedBy: currentUser?.username || 'system', movedAt: timestamp, action: 'restore', previousLocation: p.currentLocation, targetLocation: target }] } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === id ? { ...p, currentLocation: target, locationHistory: [...(p.locationHistory || []), { movedBy: currentUser?.username || 'system', movedAt: timestamp, action: 'restore', previousLocation: p.currentLocation, targetLocation: target }] } : p));
        }
        return { success: true, message: "Przywrócono." };
    }, [currentUser, setRawMaterialsLogList, setFinishedGoodsList]);

    const handleAddLocation = async (loc: LocationDefinition) => {
        try {
            const payload = { code: loc.id, name: loc.name, zone: loc.description || loc.type, capacity: loc.capacity };
            const res = await fetch(`${API_BASE_URL}/warehouse-locations`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            if (!res.ok) return { success: false, message: 'Błąd API podczas dodawania lokalizacji.' };
            const body = await res.json();
            // jeśli zwrócono id, dodaj do stanu
            setManagedLocations(prev => [...prev, loc]);
            return { success: true, message: 'Lokalizacja dodana.' };
        } catch (err) {
            console.error('Błąd dodawania lokalizacji:', err);
            return { success: false, message: 'Błąd podczas dodawania lokalizacji.' };
        }
    };

    const handleUpdateLocation = async (id: string, loc: LocationDefinition) => {
        try {
            const payload = { warehouse_id: null, code: loc.id, name: loc.name, zone: loc.description || loc.type, capacity: loc.capacity, is_active: true };
            const res = await fetch(`${API_BASE_URL}/warehouse-locations/${encodeURIComponent(id)}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            if (!res.ok) return { success: false, message: 'Błąd API podczas aktualizacji lokalizacji.' };
            setManagedLocations(prev => prev.map(l => l.id === id ? loc : l));
            return { success: true, message: 'Lokalizacja zaktualizowana.' };
        } catch (err) {
            console.error('Błąd aktualizacji lokalizacji:', err);
            return { success: false, message: 'Błąd podczas aktualizacji lokalizacji.' };
        }
    };

    const handleDeleteLocation = async (id: string) => {
        try {
            // W API używamy soft-delete
            const res = await fetch(`${API_BASE_URL}/warehouse-locations/${encodeURIComponent(id)}`, { method: 'DELETE' });
            if (!res.ok) return { success: false, message: 'Błąd API podczas usuwania lokalizacji.' };
            setManagedLocations(prev => prev.filter(l => l.id !== id));
            return { success: true, message: 'Lokalizacja usunięta.' };
        } catch (err) {
            console.error('Błąd usuwania lokalizacji:', err);
            return { success: false, message: 'Błąd podczas usuwania lokalizacji.' };
        }
    };

    const handleDeleteDelivery = useCallback((deliveryId: string) => {
        setDeliveries(prev => prev.filter(d => d.id !== deliveryId));
        logger.log('warn', `Usunięto dostawę ${deliveryId}`, 'Logistics', currentUser?.username);
        return { success: true, message: `Dostawa ${deliveryId} została usunięta.` };
    }, [currentUser, setDeliveries]);

    const handleSaveDelivery = useCallback((delivery: Delivery) => {
        let success = false;
        let message = '';
        
        setDeliveries(prev => {
            const existingDeliveryIndex = prev.findIndex(d => d.id === delivery.id);
            if (existingDeliveryIndex !== -1) {
                const existingDelivery = prev[existingDeliveryIndex];
                const updatedDelivery = { ...delivery };
                
                // Jeśli dostawa była już zakończona, rejestrujemy korektę
                if (existingDelivery.status === 'COMPLETED') {
                    const correctionEntry: DeliveryCorrection = {
                        timestamp: new Date().toISOString(),
                        user: currentUser?.username || 'system',
                        notes: 'Korekta danych w zamkniętym zleceniu dostawy.'
                    };
                    updatedDelivery.correctionLog = [...(existingDelivery.correctionLog || []), correctionEntry];
                    message = `Zapisano korektę dostawy ${delivery.orderRef || ''}`;
                    logger.log('warn', `Wykonano korektę zamkniętej dostawy ${delivery.id}`, 'Logistics', currentUser?.username);
                } else {
                    message = `Zaktualizowano dostawę ${delivery.orderRef || ''}`;
                    logger.log('info', `Zaktualizowano dostawę ${delivery.id}`, 'Logistics', currentUser?.username);
                }
                
                success = true;
                const newDeliveries = [...prev];
                newDeliveries[existingDeliveryIndex] = updatedDelivery;
                return newDeliveries;
            } else {
                const newId = `DEL-${Date.now()}`;
                const newDelivery = { ...delivery, id: newId, createdAt: new Date().toISOString() };
                success = true;
                message = `Utworzono nową dostawę ${delivery.orderRef || ''}`;
                logger.log('info', `Utworzono dostawę ${newId}`, 'Logistics', currentUser?.username);
                return [...prev, newDelivery];
            }
        });
        
        return { success, message, delivery };
    }, [currentUser, setDeliveries]);

    const handleUpdateDeliveryStatus = useCallback((deliveryId: string, newStatus: DeliveryStatus) => {
        let success = false;
        let newPallets: any[] = [];

        setDeliveries(prev => prev.map(d => {
            if (d.id === deliveryId) {
                success = true;
                const updated = { ...d, status: newStatus };
                
                if (newStatus === 'COMPLETED') {
                    updated.warehouseStageCompletedAt = new Date().toISOString();
                    
                    newPallets = d.items.map(item => {
                        const newPalletId = generate18DigitId();
                        const newPallet: RawMaterialLogEntry = {
                            id: newPalletId,
                            palletData: {
                                nrPalety: newPalletId,
                                nazwa: item.productName,
                                dataProdukcji: item.productionDate,
                                dataPrzydatnosci: item.expiryDate,
                                initialWeight: item.netWeight || 0,
                                currentWeight: item.netWeight || 0,
                                isBlocked: item.isBlocked,
                                batchNumber: item.batchNumber,
                                packageForm: item.packageForm,
                                unit: item.unit || 'kg',
                                analysisResults: item.analysisResults,
                                documents: item.documents,
                                labAnalysisNotes: item.labNotes
                            },
                            currentLocation: d.destinationWarehouse || BUFFER_MS01_ID,
                            locationHistory: [{
                                movedBy: currentUser?.username || 'system',
                                movedAt: new Date().toISOString(),
                                previousLocation: null,
                                targetLocation: d.destinationWarehouse || BUFFER_MS01_ID,
                                action: 'added_new_to_delivery_buffer',
                                deliveryOrderRef: d.orderRef,
                                deliveryDate: d.deliveryDate
                            }],
                            dateAdded: new Date().toISOString(),
                            lastValidatedAt: new Date().toISOString()
                        };
                        return newPallet;
                    });

                    setRawMaterialsLogList(prevRaw => [...prevRaw, ...newPallets]);
                }
                
                return updated;
            }
            return d;
        }));

        const msg = `Zmieniono status dostawy na: ${newStatus}`;
        logger.log('info', msg, 'Logistics', currentUser?.username);
        return { success, message: msg, newPallets };
    }, [currentUser, setDeliveries, setRawMaterialsLogList]);

    const handleSaveLabNotes = useCallback((id: string, isRaw: boolean, notes: string) => {
        const timestamp = new Date().toISOString();
        const action = 'lab_note_added';
        const user = currentUser?.username || 'system';

        if (isRaw) {
            setRawMaterialsLogList(prev => prev.map(p => p.id === id ? {
                ...p,
                palletData: { ...p.palletData, labAnalysisNotes: notes },
                locationHistory: [...p.locationHistory, { movedBy: user, movedAt: timestamp, action, notes, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === id ? {
                ...p,
                labAnalysisNotes: notes,
                locationHistory: [...p.locationHistory, { movedBy: user, movedAt: timestamp, action, notes, previousLocation: p.currentLocation, targetLocation: p.currentLocation! }]
            } : p));
        }
        return { success: true, message: 'Notatka zapisana.', type: 'success' as const };
    }, [currentUser, setRawMaterialsLogList, setFinishedGoodsList]);

    const handleSaveAnalysisResults = useCallback((id: string, itemType: 'raw' | 'fg', results: AnalysisResult[]) => {
        if (itemType === 'raw') {
            setRawMaterialsLogList(prev => prev.map(p => p.id === id ? {
                ...p,
                palletData: { ...p.palletData, analysisResults: results }
            } : p));
        } else {
            setFinishedGoodsList(prev => prev.map(p => p.id === id ? {
                ...p,
                analysisResults: results
            } : p));
        }
        return { success: true, message: 'Wyniki analiz zapisane.', type: 'success' as const };
    }, [setRawMaterialsLogList, setFinishedGoodsList]);

    const value = {
        rawMaterialsLogList, setRawMaterialsLogList, finishedGoodsList, setFinishedGoodsList, packagingMaterialsLog, setPackagingMaterialsLog,
        deliveries, setDeliveries, expiringPalletsDetails, expiryWarningDays, setExpiryWarningDays, expiryCriticalDays, setExpiryCriticalDays,
        warehouseNavLayout, setWarehouseNavLayout, findPalletByUniversalId, allProducts, inventorySessions,
        analysisRanges, setAnalysisRanges, analysisRangesHistory, logAnalysisRangeChange,
        refreshRawMaterials: fetchRawMaterials,
        handleUpdateDeliveryStatus,
        handleSaveLabNotes,
        handleAddDocument: (id: any, type: any, file: any) => ({ success: true, message: 'Dokument dodany.', type: 'success' as const }),
        handleDeleteDocument: (id: any, type: any, name: any) => ({ success: true, message: 'Dokument usunięty.', type: 'success' as const }),
        handleSaveAnalysisResults,
        allManageableLocations: managedLocations, combinedWarehouseInfos,
        handleArchiveItem, handleRestoreItem,
        validatePalletMove, handleUniversalMove, handleUnblockPallet,
        handleBlockPallet,
        handleStartInventorySession: () => ({ success: true, message: 'OK' }),
        handleCancelInventorySession: () => ({ success: true, message: 'OK' }),
        suppliers, customers, palletBalances, palletTransactions,
        handleAddSupplier: async (name: string) => {
            try {
                const token = localStorage.getItem('jwt_token');
                const headers: any = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const resp = await fetch(`${API_BASE_URL}/suppliers`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ name })
                });
                if (!resp.ok) {
                    const txt = await resp.text();
                    console.error('Błąd zapisu dostawcy:', txt);
                    return { success: false, message: 'Błąd zapisu dostawcy' };
                }
                await fetchSuppliers();
                return { success: true, message: 'Dostawca dodany.' };
            } catch (err) {
                console.error('Błąd sieci przy dodawaniu dostawcy:', err);
                return { success: false, message: 'Błąd sieci' };
            }
        },
        handleDeleteSupplier: async (value: string) => {
            try {
                const id = value;
                const token = localStorage.getItem('jwt_token');
                const headers: any = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const resp = await fetch(`${API_BASE_URL}/suppliers/${encodeURIComponent(id)}`, { method: 'DELETE', headers });
                if (!resp.ok) {
                    console.error('Błąd usuwania dostawcy:', await resp.text());
                    return { success: false, message: 'Błąd usuwania dostawcy' };
                }
                setSuppliers(prev => prev.filter(s => s.value !== value));
                setDeliveries(prev => prev.map(d => (d && String((d as any).supplier) === String(value)) ? { ...d, supplier: '' } : d ));
                return { success: true, message: 'Dostawca usunięty.' };
            } catch (err) {
                console.error('Błąd sieci przy usuwaniu dostawcy:', err);
                return { success: false, message: 'Błąd sieci' };
            }
        },
        handleUpdateSupplier: async (value: string, data: Supplier) => {
            try {
                const id = value;
                const token = localStorage.getItem('jwt_token');
                const headers: any = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                const body = {
                    name: data.label,
                    nip: data.nip,
                    address: data.address,
                    city: data.city,
                    postal_code: data.zip,
                    phone: data.phone,
                    email: data.email,
                    notes: data.notes
                };
                const resp = await fetch(`${API_BASE_URL}/suppliers/${encodeURIComponent(id)}`, { method: 'PUT', headers, body: JSON.stringify(body) });
                if (!resp.ok) {
                    console.error('Błąd aktualizacji dostawcy:', await resp.text());
                    return { success: false, message: 'Błąd aktualizacji dostawcy' };
                }
                await fetchSuppliers();
                setDeliveries(prev => prev.map(d => (d && String((d as any).supplier) === String(id)) ? { ...d, supplier: data.label } : d ));
                return { success: true, message: 'Zaktualizowano dostawcę.' };
            } catch (err) {
                console.error('Błąd sieci przy aktualizacji dostawcy:', err);
                return { success: false, message: 'Błąd sieci' };
            }
        },
        handleLookupNip: async (nip: string) => ({ success: true, message: 'OK (Mock)', data: { label: 'Firma Testowa Sp. z o.o.', nip, city: 'Gdańsk', address: 'ul. Morska 1', zip: '80-001' } }),
        handleAddCustomer: (name: string) => {
            const newCustomer = { value: name.toLowerCase().replace(/\s+/g, '_'), label: name };
            setCustomers(prev => [...prev, newCustomer]);
            return { success: true, message: 'Klient dodany.' };
        },
        handleDeleteCustomer: (v: any) => ({ success: true, message: 'OK' }),
        handleUpdateCustomer: (v: any, d: any) => ({ success: true, message: 'OK' }),
        handleAddPalletTransaction: () => ({ success: true, message: 'OK' }),
        handleAddLocation, handleUpdateLocation, handleDeleteLocation,
        handleDeleteDelivery,
        handleSaveDelivery,
        handleRecordInventoryScan: () => ({ success: true, message: 'OK' }),
        handleUpdateInventoryLocationStatus: () => {},
        handleResolveMissingPallet: () => ({ success: true, message: 'OK' }),
        handleResolveUnexpectedPallet: () => ({ success: true, message: 'OK' }),
        handleFinalizeInventorySession: () => ({ success: true, message: 'OK' }),
        handleCompleteScanningSession: () => ({ success: true, message: 'OK' }),
    };

    return <WarehouseContext.Provider value={value as any}>{children}</WarehouseContext.Provider>;
};
