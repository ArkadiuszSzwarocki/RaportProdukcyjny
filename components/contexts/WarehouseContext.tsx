
import React, { createContext, useContext, useMemo, PropsWithChildren, useState, useCallback, useEffect } from 'react';
import { RawMaterialLogEntry, Delivery, ExpiringPalletInfo, WarehouseNavLayoutItem, FinishedGoodItem, User, InventorySession, PackagingMaterialLogEntry, AnalysisResult, Document, Supplier, Customer, PalletBalance, PalletTransaction, LocationDefinition, WarehouseInfo, PalletType, View, Permission, DeliveryStatus, AnalysisRange, AnalysisRangeHistoryEntry, DeliveryCorrection } from '../../types';
import { useAuth } from './AuthContext';
import { INITIAL_FINISHED_GOODS } from '../../src/initialData';
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
    refreshInventorySessions: () => Promise<void>;
    handleUpdateDeliveryStatus: (deliveryId: string, newStatus: DeliveryStatus) => { success: boolean, message: string, newPallets?: any[] };
    handleUniversalMove: (id: string, type: string, locationId: string, notes?: string) => { success: boolean; message: string };
    handleStartInventorySession: (name: string, locationIds: string[]) => Promise<{ success: boolean; message: string; }>;
    handleCancelInventorySession: (sessionId: string) => Promise<{ success: boolean; message: string; }>;
    handleRecordInventoryScan: (sessionId: string, locationId: string, palletId: string, qty: number, force: boolean) => Promise<{ success: boolean; message: string; warning?: string }>;
    handleUpdateInventoryLocationStatus: (sessionId: string, locationId: string, status: 'pending' | 'scanned') => Promise<void>;
    handleFinalizeInventorySession: (sessionId: string) => Promise<{ success: boolean; message: string }>;
    handleCompleteScanningSession: (sessionId: string) => Promise<{ success: boolean; message: string }>;
    combinedWarehouseInfos: WarehouseInfo[];
    allManageableLocations: LocationDefinition[];
}

const WarehouseContext = createContext<WarehouseContextValue | undefined>(undefined);

export const useWarehouseContext = () => {
    const context = useContext(WarehouseContext);
    if (!context) throw new Error('useWarehouseContext must be used within a WarehouseProvider');
    return context;
};

export const WarehouseProvider: React.FC<PropsWithChildren> = ({ children }) => {
    const { currentUser } = useAuth();
    const [rawMaterialsLogList, setRawMaterialsLogList] = useState<RawMaterialLogEntry[]>([]);
    const [finishedGoodsList, setFinishedGoodsList] = useState<FinishedGoodItem[]>(INITIAL_FINISHED_GOODS);
    const [deliveries, setDeliveries] = useState<Delivery[]>([]);
    const [packagingMaterialsLog, setPackagingMaterialsLog] = useState<PackagingMaterialLogEntry[]>([]);
    const [inventorySessions, setInventorySessions] = useState<InventorySession[]>([]);
    const [expiryWarningDays, setExpiryWarningDays] = useState(45);
    const [expiryCriticalDays, setExpiryCriticalDays] = useState(7);
    const [managedLocations] = useState<LocationDefinition[]>(INITIAL_LOCATIONS);
    const [warehouseNavLayout, setWarehouseNavLayout] = useState<WarehouseNavLayoutItem[]>(DEFAULT_WAREHOUSE_NAV_LAYOUT);

    const refreshRawMaterials = useCallback(async () => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/raw-materials`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            console.log('refreshRawMaterials ->', `${API_BASE_URL}/raw-materials`, 'status', res.status);
            if (res.ok) {
                const data = await res.json();
                console.log('refreshRawMaterials -> received', Array.isArray(data) ? data.length : typeof data, 'items');
                const transformed = data.map((row: any) => ({
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
            console.error('Fetch raw materials failed', err);
        }
    }, []);

    const refreshInventorySessions = useCallback(async () => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/sessions`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            console.log('refreshInventorySessions ->', `${API_BASE_URL}/inventory/sessions`, 'status', res.status);
            if (res.ok) {
                const data = await res.json();
                setInventorySessions(data);
            }
        } catch (err) {
            console.error('Fetch inventory sessions failed', err);
        }
    }, []);

    useEffect(() => {
        if (currentUser) {
            refreshRawMaterials();
            refreshInventorySessions();
            const interval = setInterval(() => {
                refreshRawMaterials();
                refreshInventorySessions();
            }, 10000);
            return () => clearInterval(interval);
        }
    }, [currentUser, refreshRawMaterials, refreshInventorySessions]);

    const handleStartInventorySession = async (name: string, locationIds: string[]) => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/sessions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ name, locationIds, createdBy: currentUser?.username })
            });
            if (res.ok) {
                await refreshInventorySessions();
                return { success: true, message: 'Sesja inwentaryzacyjna rozpoczęta.' };
            }
            return { success: false, message: 'Błąd podczas tworzenia sesji.' };
        } catch (err) {
            return { success: false, message: err.message };
        }
    };

    const handleRecordInventoryScan = async (sessionId: string, locationId: string, palletId: string, qty: number, force: boolean) => {
        // Logika progu przeliczenia (ostrzeżenie przed zatwierdzeniem dużej różnicy)
        if (!force) {
            const session = inventorySessions.find(s => s.id === sessionId);
            const snapshotItem = session?.snapshot.find(s => s.palletId === palletId);
            if (snapshotItem) {
                const diff = Math.abs(qty - snapshotItem.expectedQuantity);
                if (diff > snapshotItem.expectedQuantity * 0.1) {
                    return { success: false, message: 'Wykryto dużą rozbieżność.', warning: 'RECOUNT_NEEDED' };
                }
            }
        }

        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/scans`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ sessionId, locationId, palletId, countedQuantity: qty, scannedBy: currentUser?.username })
            });
            if (res.ok) {
                await refreshInventorySessions();
                return { success: true, message: 'Skan zarejestrowany.' };
            }
            return { success: false, message: 'Błąd zapisu skanu.' };
        } catch (err) {
            return { success: false, message: err.message };
        }
    };

    const handleUpdateInventoryLocationStatus = async (sessionId: string, locationId: string, status: 'pending' | 'scanned') => {
        // Status lokalizacji w spisie ślepym jest pochodną istnienia skanów w bazie, 
        // ale możemy też zaimplementować jawne flago "ukończone dla lokalizacji" jeśli potrzeba.
        // Tutaj upraszczamy - odświeżamy sesje.
        await refreshInventorySessions();
    };

    const handleCompleteScanningSession = async (sessionId: string) => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/sessions/${sessionId}/status`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ status: 'pending_review' })
            });
            if (res.ok) {
                await refreshInventorySessions();
                return { success: true, message: 'Skanowanie zakończone. Przekazano do weryfikacji.' };
            }
            return { success: false, message: 'Błąd aktualizacji statusu.' };
        } catch (err) {
            return { success: false, message: err.message };
        }
    };

    const handleFinalizeInventorySession = async (sessionId: string) => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/sessions/${sessionId}/finalize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ finalizedBy: currentUser?.username })
            });
            if (res.ok) {
                await refreshInventorySessions();
                await refreshRawMaterials();
                return { success: true, message: 'Inwentaryzacja zakończona pomyślnie. Stany zaktualizowane.' };
            }
            const errData = await res.json();
            return { success: false, message: errData.error || 'Błąd finalizacji.' };
        } catch (err) {
            return { success: false, message: err.message };
        }
    };

    const handleCancelInventorySession = async (sessionId: string) => {
        try {
            const token = localStorage.getItem('jwt_token');
            const res = await fetch(`${API_BASE_URL}/inventory/sessions/${sessionId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                await refreshInventorySessions();
                return { success: true, message: 'Inwentaryzacja anulowana.' };
            }
            return { success: false, message: 'Błąd podczas usuwania sesji.' };
        } catch (err) {
            return { success: false, message: err.message };
        }
    };

    const handleUniversalMove = useCallback((id: string, type: string, locationId: string, notes?: string) => {
        // Implementacja move przez API...
        return { success: true, message: "Przeniesiono pomyślnie." };
    }, []);

    const findPalletByUniversalId = useCallback((id: string) => {
        const raw = rawMaterialsLogList.find(p => p.id === id || p.palletData.nrPalety === id);
        if (raw) return { item: raw, type: 'raw' as const };
        const fg = finishedGoodsList.find(p => p.id === id || p.finishedGoodPalletId === id);
        if (fg) return { item: fg, type: 'fg' as const };
        return null;
    }, [rawMaterialsLogList, finishedGoodsList]);

    const combinedWarehouseInfos = useMemo(() => {
        return managedLocations.map(loc => ({
            id: loc.id,
            label: loc.name,
            view: View.LocationDetail,
        }));
    }, [managedLocations]);

    const value = {
        rawMaterialsLogList, setRawMaterialsLogList, finishedGoodsList, setFinishedGoodsList, packagingMaterialsLog, setPackagingMaterialsLog,
        deliveries, setDeliveries, inventorySessions, refreshRawMaterials, refreshInventorySessions,
        expiryWarningDays, setExpiryWarningDays, expiryCriticalDays, setExpiryCriticalDays,
        warehouseNavLayout, setWarehouseNavLayout, findPalletByUniversalId,
        allProducts: [], analysisRanges: [], analysisRangesHistory: [], logAnalysisRangeChange: () => {},
        handleUpdateDeliveryStatus: () => ({ success: true, message: 'OK' }),
        handleUniversalMove,
        handleStartInventorySession, handleCancelInventorySession, handleRecordInventoryScan,
        handleUpdateInventoryLocationStatus, handleFinalizeInventorySession, handleCompleteScanningSession,
        combinedWarehouseInfos, allManageableLocations: managedLocations,
        // Dodane pola, aby uproszczony kontekst nie łamał komponentów oczekujących tych wartości
        suppliers: SUPPLIERS_LIST,
        customers: [],
        palletBalances: [],
        palletTransactions: [],
        expiringPalletsDetails: [] // uproszczone dla przykładu
    };

    return <WarehouseContext.Provider value={value as any}>{children}</WarehouseContext.Provider>;
};
