
import { View, Permission, UserRole, WarehouseInfo, Recipe, AnalysisRange, PrinterDef } from './types';

// Bezpieczny helper do pobierania zmiennych środowiskowych Vite
const getEnvVar = (key: string, fallback: string): string => {
    // Sprawdzenie dla środowiska Node/CommonJS
    if (typeof process !== 'undefined' && process.env && process.env[key]) {
        return process.env[key] as string;
    }
    // Sprawdzenie dla środowiska Vite/ESM
    try {
        // @ts-ignore - ignorujemy błąd TS w przypadku braku wsparcia import.meta
        if (typeof import.meta !== 'undefined' && import.meta.env) {
            // @ts-ignore
            return import.meta.env[key] || fallback;
        }
    } catch (e) {
        // Ciche przechwycenie błędu, jeśli import.meta nie jest wspierany
    }
    return fallback;
};

// Adres backendu Node.js (serwer-api) - pobierany bezpiecznie
// Normalize API base URL:
// - If VITE_API_URL is a host (http(s)://host:port) and doesn't include '/api', append '/api'.
// - If not set, fallback to the relative '/api' so dev proxy works.
const rawApi = getEnvVar('VITE_API_URL', '/api');
export const API_BASE_URL = (() => {
  try {
    if (!rawApi) return '/api';
    // If value looks like a full URL (starts with http) and doesn't contain '/api', append it
    if (/^https?:\/\//i.test(rawApi) && !/\/api(\/|$)/i.test(rawApi)) {
      return rawApi.replace(/\/+$/,'') + '/api';
    }
    // otherwise return as-is (handles '/api' or relative paths)
    return rawApi.replace(/\/+$/,'');
  } catch (e) {
    return '/api';
  }
})();

export const INITIAL_PRINTERS: PrinterDef[] = [
    { id: 'biuro', name: 'Biuro (TSC)', ip: '192.168.1.236' },
    { id: 'magazyn', name: 'Magazyn (TSC)', ip: '192.168.1.237' },
    { id: 'handel', name: 'Handel (TSC)', ip: '192.168.1.240' },
    { id: 'osip', name: 'OSIP', ip: '192.168.1.160' },
];

export const R_LOCATIONS_R01_CONST: string[] = [];
export const R_LOCATIONS_R02_CONST: string[] = [];
export const R_LOCATIONS_R03_CONST: string[] = [];
export const R_LOCATIONS_R04_CONST = Array.from({ length: 20 }, (_, i) => `R04${(i + 1).toString().padStart(2, '0')}01`);
export const R_LOCATIONS_R05_CONST = Array.from({ length: 20 }, (_, i) => `R05${(i + 1).toString().padStart(2, '0')}01`);
export const R_LOCATIONS_R06_CONST = Array.from({ length: 10 }, (_, i) => `R06${(i + 1).toString().padStart(2, '0')}01`);
export const R_LOCATIONS_R07_CONST = Array.from({ length: 20 }, (_, i) => `R07${(i + 1).toString().padStart(2, '0')}01`);

export const OSIP_LOCATIONS_CONST = Array.from({ length: 77 }, (_, i) => `OS${(i + 1).toString().padStart(2, '0')}`);

export const SOURCE_WAREHOUSE_ID_MS01 = 'MS01';
export const SUB_WAREHOUSE_ID = 'MP01';
export const BUFFER_MS01_ID = 'BF_MS01';
export const BUFFER_MP01_ID = 'BF_MP01';
export const MDM01_WAREHOUSE_ID = 'MDM01';
export const KO01_WAREHOUSE_ID = 'KO01';
export const PSD_WAREHOUSE_ID = 'PSD';
export const MGW01_WAREHOUSE_ID = 'MGW01';
export const MGW02_WAREHOUSE_ID = 'MGW02';
export const MOP01_WAREHOUSE_ID = 'MOP01';
export const MGW01_RECEIVING_AREA_ID = 'MGW01-PRZYJECIA';
export const LOADING_BAY_ID = 'RAMPA';
export const MIXING_ZONE_ID = 'MIX01';
export const VIRTUAL_LOCATION_MISSING = 'ZAGUBIONE';
export const OSIP_WAREHOUSE_ID = 'OSIP';
export const IN_TRANSIT_OSIP_ID = 'W_TRANZYCIE_OSIP';
export const VIRTUAL_LOCATION_ARCHIVED = 'ARCHIVED';


export const PRODUCTION_STATIONS_BB = Array.from({ length: 24 }, (_, i) => `BB${(i + 1).toString().padStart(2, '0')}`);
export const PRODUCTION_STATIONS_MZ = ['MZ01', 'MZ02', 'MZ03', 'MZ04', 'MZ05', 'MZ06', 'MZ05-01', 'MZ06-01'];
export const M_LOCATIONS_BIG_BAGS = ['M01', 'M02'];
export const MZ_LOCATIONS_BAGS: string[] = [];

export const ALL_MANAGEABLE_WAREHOUSES: WarehouseInfo[] = [
    { id: 'all', label: 'Wszystkie Magazyny', view: View.AllWarehousesView },
    { id: SOURCE_WAREHOUSE_ID_MS01, label: 'Magazyn Główny (MS01)', view: View.SourceWarehouseMS01 },
    { id: OSIP_WAREHOUSE_ID, label: 'Magazyn Zewnętrzny (OSiP)', view: View.OsipWarehouse },
    { id: BUFFER_MS01_ID, label: 'Bufor Surowców (BF_MS01)', view: View.BufferMS01View },
    { id: BUFFER_MP01_ID, label: 'Bufor Produkcyjny (BF_MP01)', view: View.BufferMP01View },
    { id: SUB_WAREHOUSE_ID, label: 'Magazyn Produkcyjny (MP01)', view: View.SubWarehouseMP01 },
    { id: MDM01_WAREHOUSE_ID, label: 'Magazyn Dodatków (MDM01)', view: View.MDM01View },
    { id: KO01_WAREHOUSE_ID, label: 'Strefa Konfekcji (KO01)', view: View.KO01View },
    { id: PSD_WAREHOUSE_ID, label: 'Magazyn PSD', view: View.PSD_WAREHOUSE },
    { id: MOP01_WAREHOUSE_ID, label: 'Magazyn Opakowań (MOP01)', view: View.MOP01View },
    { id: 'pending_labels', label: 'Etykiety Oczekujące', view: View.PendingLabels },
    { id: MGW01_RECEIVING_AREA_ID, label: 'Strefa Przyjęć Wyrobów Gotowych', view: View.MGW01_Receiving },
    { id: MGW01_WAREHOUSE_ID, label: 'Magazyn Wyrobów Gotowych (MGW01)', view: View.MGW01 },
    { id: MGW02_WAREHOUSE_ID, label: 'Magazyn Wyrobów Gotowych (MGW02)', view: View.MGW02 },
    { id: MIXING_ZONE_ID, label: 'Strefa Miksowania', view: View.MIXING_WORKER },
    { id: 'R01', label: 'Regał R01', view: View.LocationDetail, isLocationDetailLink: true },
    { id: 'R02', label: 'Regał R02', view: View.LocationDetail, isLocationDetailLink: true },
    { id: 'R03', label: 'Regał R03', view: View.LocationDetail, isLocationDetailLink: true },
    { id: 'R04', label: 'Regał R04', view: View.LocationDetail, isLocationDetailLink: true },
    { id: 'R07', label: 'Regał R07', view: View.LocationDetail, isLocationDetailLink: true },
];

export const MGW01_LAYOUT_ROWS = 10;
export const MGW01_LAYOUT_SPOTS_PER_ROW = 10;
export const MGW02_LAYOUT_ROWS_PER_SIDE = 5;
export const MGW02_LAYOUT_SPOTS_PER_ROW = 10;

export const WAREHOUSE_RACK_PREFIX_MAP: Record<string, string[]> = {
    [SUB_WAREHOUSE_ID]: ['R01', 'R02', 'R03', 'R04', 'R05', 'R07'],
    [MDM01_WAREHOUSE_ID]: ['R06'],
};

export const SUPPLIERS_LIST = [
    { value: 'supplier_a', label: 'Dostawca A' },
    { value: 'supplier_b', label: 'Dostawca B' },
    { value: 'supplier_c', label: 'Dostawca C' },
    { value: 'transfer_wewnetrzny', label: 'Transfer Wewnętrzny' },
];

export const SAMPLE_RECIPES: Recipe[] = [];

export const AGRO_LINE_PRODUCTION_RATE_KG_PER_MINUTE = 40000 / (8 * 60); // 40,000 kg / 8h
export const PRODUCTION_RATE_KG_PER_MINUTE = 50;
export const DEFAULT_SETTINGS = { EXPIRY_WARNING_DAYS: 45, EXPIRY_CRITICAL_DAYS: 7, SESSION_TIMEOUT_MINUTES: 15, PROMPT_TIMEOUT_MINUTES: 2 };
export const DEFAULT_PRINT_SERVER_URL = 'https://192.168.1.143:3001';

// FIX: Added missing exported constants to resolve compilation errors.
export const CHANGELOG_DATA = [
  {
    version: '1.0.0',
    date: '2024-01-01',
    changes: [
      { type: 'new', description: 'Initial release' }
    ]
  }
];

export const PREDEFINED_ROLES = ['admin', 'planista', 'magazynier', 'kierownik magazynu', 'lab', 'operator_psd', 'operator_agro', 'operator_procesu', 'user', 'boss', 'lider'];

export const DEFAULT_WAREHOUSE_NAV_LAYOUT: any[] = [];

export const DEFAULT_ANALYSIS_RANGES: any[] = [];

export const STATION_RAW_MATERIAL_MAPPING_DEFAULT: Record<string, string> = {};

export const ADJUSTMENT_REASONS = [
  { value: 'underweight', label: 'Niedowaga' },
  { value: 'quality_fail', label: 'Błąd jakości' },
  { value: 'other', label: 'Inny' }
];

export const DEFAULT_NOTIFICATION_SERVER_URL = 'http://localhost:3000';

export const SOUND_OPTIONS = [
  { id: 'default', label: 'Domyślny', path: '/sounds/notification.mp3' }
];
