import React from 'react';
import { View, Permission, WarehouseNavLayoutItem, WarehouseInfo } from '../types'; 
import QrCodeIcon from '../components/icons/QrCodeIcon';
import WarehouseIcon from '../components/icons/WarehouseIcon';
import UserIcon from '../components/icons/UserIcon';
import ClipboardListIcon from '../components/icons/ClipboardListIcon';
import ArchiveBoxIcon from '../components/icons/ArchiveBoxIcon';
import InboxArrowDownIcon from '../components/icons/InboxArrowDownIcon';
import ListBulletIcon from '../components/icons/ListBulletIcon';
import CogIcon from '../components/icons/CogIcon'; 
import Squares2X2Icon from '../components/icons/Squares2X2Icon'; 
import TruckIcon from '../components/icons/TruckIcon'; 
import ShieldCheckIcon from '../components/icons/ShieldCheckIcon'; 
import MapIcon from '../components/icons/MapIcon'; 
import CalendarDaysIcon from '../components/icons/CalendarDaysIcon';
import PlayIcon from '../components/icons/PlayIcon';
import ChartBarSquareIcon from '../components/icons/ChartBarSquareIcon';
import MixerIcon from '../components/icons/MixerIcon';
import WifiSlashIcon from '../components/icons/WifiSlashIcon';
import ViewColumnsIcon from '../components/icons/ViewColumnsIcon';
import RectangleGroupIcon from '../components/icons/RectangleGroupIcon';
import ArrowLeftRightIcon from '../components/icons/ArrowLeftRightIcon';
import BeakerIcon from '../components/icons/BeakerIcon';
import CubeIcon from '../components/icons/CubeIcon';
import AdjustmentsHorizontalIcon from '../components/icons/AdjustmentsHorizontalIcon';
import PlusIcon from '../components/icons/PlusIcon';
import DocumentTextIcon from '../components/icons/DocumentTextIcon';
import ShareIcon from '../components/icons/ShareIcon';

export const WAREHOUSE_SUB_VIEWS = new Set([
  View.AllWarehousesView,
  View.WarehouseDashboard,
  View.SourceWarehouseMS01,
  View.BufferMS01View,
  View.BufferMP01View,
  View.SubWarehouseMP01,
  View.MDM01View,
  View.PSD_WAREHOUSE,
  View.MGW01_Receiving,
  View.MGW01,
  View.MGW02,
  View.MOP01View,
  View.KO01View,
  View.PendingLabels,
  View.LocationDetail,
  View.OsipWarehouse,
]);

export interface NavItemDef {
    key: string;
    view?: View;
    label: string;
    icon?: React.ReactNode;
    isGroup?: boolean;
    groupKey?: string;
    separatorBefore?: boolean;
    isSeparator?: boolean;
    defaultOpen?: boolean;
    subItems?: NavItemDef[];
    permission?: Permission;
    allowedRoles?: string[];
    warehouseContextId?: string;
    action?: () => void;
    hidden?: boolean;
}

export const getNavItemsDefinition = (
    onOpenFeedbackModal: () => void, 
    isInventoryActive: boolean = false, 
    userRole: string = '',
    userSubRole: string = 'AGRO'
): NavItemDef[] => {
    
    // Rola nadrzędna - Administrator i Boss widzą WSZYSTKO
    const isAdmin = userRole === 'admin' || userRole === 'boss';
    const isPsdOperator = userRole === 'operator_psd';
    const isNotAgro = userSubRole !== 'AGRO';
    
    // Warunki ukrycia dla ról o ograniczonym dostępie
    const shouldRestrict = !isAdmin && (isPsdOperator || isNotAgro);
    const alwaysShowInventoryRoles = ['admin', 'planista', 'kierownik magazynu', 'lider', 'boss'];
    const showInventory = alwaysShowInventoryRoles.includes(userRole) || isInventoryActive;

    return [
    { key: 'view-dashboard', view: View.Dashboard, label: 'Pulpit', icon: React.createElement(Squares2X2Icon, { className: "h-6 w-6" }) },
    
    {
        key: 'group-magazyn',
        label: 'Magazyn',
        icon: React.createElement(WarehouseIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && isPsdOperator,
        subItems: [
            { key: 'view-warehouse-dashboard', view: View.WarehouseDashboard, label: 'Przegląd Magazynów', hidden: shouldRestrict },
            { key: 'view-delivery-list', view: View.DeliveryList, label: 'Przyjęcia (Realizacja)', hidden: shouldRestrict },
            { key: 'view-dispatch-fulfillment', view: View.Logistics, label: 'Realizacja Wydań', permission: Permission.MANAGE_DISPATCH_ORDERS, hidden: shouldRestrict },
            { key: 'view-pallet-balances', view: View.ManagePalletBalances, label: 'Saldy Opakowań', permission: Permission.MANAGE_DELIVERIES, hidden: shouldRestrict },
            { key: 'view-inventory', view: View.InventoryDashboard, label: 'Inwentaryzacja', hidden: !showInventory || (shouldRestrict && !isAdmin) },
            { key: 'view-split-pallet', view: View.SplitPallet, label: 'Podziel Paletę', hidden: shouldRestrict },
        ]
    },

    // `Kartoteki` przeniesione jako podmenu do sekcji `System i Administracja` (usuwa duplikaty)

    {
        key: 'group-planowanie',
        label: 'Planowanie',
        icon: React.createElement(CalendarDaysIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && (isPsdOperator || isNotAgro),
        subItems: [
            // 'Planowanie Dostaw' usunięte — korzystamy z widoku 'Przyjęcia' w sekcji Magazyn
            { key: 'view-internal-transfers', view: View.InternalTransfers, label: 'Transfery OSiP', icon: React.createElement(ArrowLeftRightIcon, { className: "h-4 w-4 opacity-70" }), permission: Permission.MANAGE_INTERNAL_TRANSFERS },
            // 'Zlecenia Wydania' przeniesione do 'Realizacja Wydań' w sekcji Magazyn
            { key: 'view-agro-planning', view: View.ProductionPlanningAgro, label: 'Harmonogram AGRO', permission: Permission.PLAN_PRODUCTION_AGRO },
            { key: 'view-psd-planning', view: View.ProductionPlanning2, label: 'Harmonogram PSD', permission: Permission.PLAN_PRODUCTION_PSD },
            { key: 'view-mixing-planner', view: View.MIXING_PLANNER, label: 'Planowanie Miksowania', permission: Permission.PLAN_MIXING },
            { key: 'view-raw-material-demand', view: View.RawMaterialDemand, label: 'Zapotrzebowanie Surowcowe' },
            { key: 'view-packaging-demand', view: View.PackagingDemand, label: 'Zapotrzebowanie Opakowań' },
        ]
    },

    {
        key: 'group-produkcja',
        label: 'Produkcja',
        icon: React.createElement(CogIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && isNotAgro,
        subItems: [
            { key: 'view-prod-stock', view: View.ProductionStock, label: 'Surowce w Produkcji', hidden: !isAdmin && isPsdOperator },
            { key: 'view-curr-prod', view: View.CurrentProductionRun, label: 'Linia AGRO', permission: Permission.EXECUTE_PRODUCTION_AGRO, hidden: !isAdmin && isPsdOperator },
            { key: 'view-lpsd-prod', view: View.LPSD_PRODUCTION, label: 'Linia PSD', permission: Permission.EXECUTE_PRODUCTION_PSD },
            { key: 'view-mixing-worker', view: View.MIXING_WORKER, label: 'Miksowanie', permission: Permission.EXECUTE_MIXING },
            { key: 'view-pkg-operator', view: View.PackagingOperator, label: 'Pakowanie / Rejestracja', allowedRoles: ['admin', 'magazynier', 'operator_agro', 'planista', 'boss', 'operator_procesu', 'operator_psd'] },
            { key: 'view-manage-adj', view: View.ManageAdjustments, label: 'Dosypki / Korekty', allowedRoles: ['admin', 'magazynier', 'operator_psd', 'operator_agro', 'planista', 'lab'] },
        ]
    },

    {
        key: 'group-zestawienia',
        label: 'Zestawienia Stanów',
        icon: React.createElement(RectangleGroupIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && (isPsdOperator || isNotAgro),
        subItems: [
            { key: 'view-all-raw-materials', view: View.AllRawMaterialsView, label: 'Suma Surowców' },
            { key: 'view-all-finished-goods', view: View.AllFinishedGoodsView, label: 'Suma Wyrobów Gotowych' },
            { key: 'view-all-packaging-materials', view: View.AllPackagingMaterialsView, label: 'Suma Opakowań' },
        ]
    },

    {
        key: 'group-laboratorium',
        label: 'Laboratorium',
        icon: React.createElement(BeakerIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        allowedRoles: ['admin', 'lab', 'boss'],
        hidden: !isAdmin && isNotAgro,
        subItems: [
            { key: 'view-recipes', view: View.Recipes, label: 'Receptury' },
            { key: 'view-recipe-adj', view: View.RecipeAdjustments, label: 'Korekty Receptur', allowedRoles: ['admin', 'lab', 'planista'] },
            { key: 'view-lab-release', view: View.LabPalletRelease, label: 'Zwalnianie Palet' },
            { key: 'view-production-release', view: View.ProductionRelease, label: 'Zwalnianie Produkcji', permission: Permission.PROCESS_ANALYSIS },
            { key: 'view-lab-ranges', view: View.LabAnalysisRanges, label: 'Zakresy Analiz', permission: Permission.PROCESS_ANALYSIS },
            { key: 'view-lab-archive', view: View.LAB_ARCHIVE_SAMPLING, label: 'Próbkowanie', icon: React.createElement(ArchiveBoxIcon, { className: "h-6 w-6" }), permission: Permission.PROCESS_ANALYSIS },
        ]
    },

    {
        key: 'group-archiwa',
        label: 'Archiwum',
        icon: React.createElement(ArchiveBoxIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && (isPsdOperator || isNotAgro),
        subItems: [
            { key: 'view-material-archive', view: View.MaterialArchive, label: 'Archiwum Materiałów', icon: React.createElement(ArchiveBoxIcon, { className: "h-4 w-4 opacity-70" }) },
            { key: 'view-agro-run-archive', view: View.ArchivedProductionRuns, label: 'Archiwum Zleceń AGRO', icon: React.createElement(ArchiveBoxIcon, { className: "h-4 w-4 opacity-70" }) },
            { key: 'view-delivery-archive', view: View.ARCHIVED_DELIVERIES, label: 'Archiwum Dostaw', icon: React.createElement(ArchiveBoxIcon, { className: "h-4 w-4 opacity-70" }) },
            { key: 'view-dispatch-archive', view: View.ARCHIVED_DISPATCH_ORDERS, label: 'Archiwum Wydań', icon: React.createElement(ArchiveBoxIcon, { className: "h-4 w-4 opacity-70" }) },
            { key: 'view-mixing-archive', view: View.ARCHIVED_MIXING_ORDERS, label: 'Archiwum Miksowania', icon: React.createElement(ArchiveBoxIcon, { className: "h-4 w-4 opacity-70" }) },
        ]
    },
    
    {
        key: 'group-raporty',
        label: 'Raporty i Analizy',
        icon: React.createElement(ChartBarSquareIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && (isPsdOperator || isNotAgro),
        subItems: [
            { key: 'view-reports-landing', view: View.Reporting, label: 'Centrum Raportów' },
            { key: 'view-inv-reports', view: View.InventoryReports, label: 'Raporty Inwentaryzacji' },
        ]
    },
    
    {
        key: 'group-system',
        label: 'System i Administracja',
        icon: React.createElement(CogIcon, { className: "h-6 w-6" }),
        isGroup: true,
        separatorBefore: true,
        defaultOpen: false,
        hidden: !isAdmin && isNotAgro,
        subItems: [
            { key: 'view-settings', view: View.Settings, label: 'Ustawienia' },
            { key: 'view-roles-management', view: View.RolesManagement, label: 'Role i Oddziały', permission: Permission.MANAGE_PERMISSIONS },
            { key: 'view-users', view: View.Users, label: 'Użytkownicy', permission: Permission.MANAGE_USERS },
            { key: 'view-permissions', view: View.UserPermissions, label: 'Uprawnienia Indywidualne', permission: Permission.MANAGE_PERMISSIONS },
            {
                key: 'group-kartoteki',
                label: 'Kartoteki',
                icon: React.createElement(ListBulletIcon, { className: "h-5 w-5 opacity-80" }),
                isGroup: true,
                defaultOpen: false,
                hidden: !isAdmin && isPsdOperator,
                subItems: [
                    { key: 'view-products', view: View.ManageProducts, label: 'Katalog Produktów', permission: Permission.MANAGE_PRODUCTS },
                    { key: 'view-suppliers', view: View.ManageSuppliers, label: 'Kontrahenci (Dostawcy)' },
                    { key: 'view-customers', view: View.ManageCustomers, label: 'Kontrahenci (Klienci)' },
                    { key: 'view-packaging-forms', view: View.ManagePackagingForms, label: 'Formy Opakowań', permission: Permission.MANAGE_PRODUCTS },
                ]
            },
            { key: 'view-prod-stations', view: View.ManageProductionStations, label: 'Stacje Zasypowe', permission: Permission.MANAGE_PRODUCTION_STATIONS },
            { key: 'view-warehouse-admin', view: View.WarehouseAdmin, label: 'Lokalizacje Magazynowe', permission: Permission.MANAGE_SYSTEM_SETTINGS },
            { key: 'view-sidebar-settings', view: View.SidebarLayoutSettings, label: 'Konfiguracja Menu', permission: Permission.MANAGE_SYSTEM_SETTINGS },
            { key: 'view-app-logs', view: View.AppLogs, label: 'Logi Systemowe', permission: Permission.MANAGE_SYSTEM_SETTINGS },
            { key: 'view-workflow-viz', view: View.WORKFLOW_VISUALIZATION, label: 'Schemat Procesów', icon: React.createElement(ShareIcon, { className: "h-6 w-6" }) },
        ]
    },
];
};

export const ALL_NAV_DEFINITIONS: Map<string, any> = new Map(
    getNavItemsDefinition(() => {}, false, '', '').flatMap(item => {
        const items = [item, ...(item.subItems || [])];
        return items.map(i => [i.key, i]);
    })
);