import React, { ReactNode } from 'react';

export interface PrinterDef {
  id: string;
  name: string;
  ip: string;
}

export enum View {
  Dashboard = 1,
  Scan,
  Users,
  Settings,
  Information,
  Instructions,
  History,
  Traceability,
  ProductionStock,
  QueueStatus,
  Recipes,
  MyAccount,
  Control,
  GenerateLoginQr,
  LabPalletRelease,
  LabAnalysisPage,
  LabAnalysisRanges,
  WhatsNew,
  GlobalSearch,
  SplitPallet,
  Logistics,
  DispatchFulfillment,
  ProductionPlanningAgro,
  CurrentProductionRun,
  ArchivedProductionRuns,
  ProductionPlanning2,
  MIXING_PLANNER,
  MIXING_WORKER,
  ADD_MIXING_ORDER,
  EDIT_MIXING_ORDER,
  ARCHIVED_MIXING_ORDERS,
  ARCHIVED_DISPATCH_ORDERS,
  ARCHIVED_DELIVERIES,
  Reporting,
  OEE_REPORT,
  DELIVERY_REPORT,
  BLOCKED_PALLETS_REPORT,
  SLOW_MOVING_PALLETS_REPORT,
  YIELD_VARIANCE_REPORT,
  SUPPLIER_PERFORMANCE_REPORT,
  InventoryReports,
  ADJUSTMENT_REPORT,
  LPSD_PRODUCTION,
  PSD_REPORTS,
  RawMaterialDemand,
  PackagingDemand,
  PSD_TASK_REPORT,
  RecipeAdjustments,
  CreateAdjustmentOrder,
  ManageAdjustments,
  ManageProducts,
  ManageSuppliers,
  ManageCustomers,
  ManagePalletBalances,
  InventoryDashboard,
  InventorySession,
  InventoryReview,
  InventoryFinalization,
  AllRawMaterialsView,
  AllFinishedGoodsView,
  AllPackagingMaterialsView,
  ManageProductionStations,
  AppLogs,
  SidebarLayoutSettings,
  WarehouseGroupSettings,
  WarehouseAdmin,
  GoodsDeliveryReception,
  DeliveryList,
  UserPermissions,
  PalletMovementTester,
  LAB_ARCHIVE_SAMPLING,
  InternalTransfers,
  InternalTransferReception,
  WORKFLOW_VISUALIZATION,
  ProductionRelease,
  PackagingOperator,
  AssemblyReport,
  ARCHIVED_PRODUCTION_RUN_REPORT,
  MaterialArchive,
  NotFound,
  WarehouseDashboard,
  SourceWarehouseMS01,
  BufferMS01View,
  BufferMP01View,
  SubWarehouseMP01,
  MDM01View,
  PSD_WAREHOUSE,
  MGW01_Receiving,
  MGW01,
  MGW02,
  MOP01View,
  KO01View,
  PendingLabels,
  LocationDetail,
  OsipWarehouse,
  AllWarehousesView,
  LogoShowcase,
  RolesManagement,
    ManagePackagingForms,
}

export interface Supplier {
    value: string;
    label: string;
    nip?: string;
    address?: string;
    city?: string;
    zip?: string;
    email?: string;
    phone?: string;
    notes?: string;
}

export interface Customer extends Supplier {
    contactPerson?: string;
    paymentTerms?: string;
    priceList?: string;
}

export type PalletType = 'EUR' | 'EPAL' | 'H1' | 'IND' | 'PLASTIC';

export interface PalletBalance {
    contractorValue: string; 
    contractorLabel: string;
    balances: Record<PalletType, number>;
}

export interface PalletTransaction {
    id: string;
    timestamp: string;
    contractorValue: string;
    type: PalletType;
    quantity: number; 
    direction: 'IN' | 'OUT';
    referenceDoc?: string;
    createdBy: string;
}

export enum Permission {
  MANAGE_USERS = 'manage_users',
  MANAGE_PERMISSIONS = 'manage_permissions',
  MANAGE_SYSTEM_SETTINGS = 'manage_system_settings',
  MANAGE_PRODUCTS = 'manage_products',
  MANAGE_PRODUCTION_STATIONS = 'manage_production_stations',
  CREATE_DELIVERY = 'create_delivery',
  PROCESS_DELIVERY_LAB = 'process_delivery_lab',
  PROCESS_DELIVERY_WAREHOUSE = 'process_delivery_warehouse',
  MANAGE_DELIVERIES = 'manage_deliveries',
  PLAN_PRODUCTION_AGRO = 'plan_production_agro',
  EXECUTE_PRODUCTION_AGRO = 'execute_production_agro',
  PLAN_PRODUCTION_PSD = 'plan_production_psd',
  EXECUTE_PRODUCTION_PSD = 'execute_production_psd',
  PLAN_MIXING = 'plan_mixing',
  EXECUTE_MIXING = 'execute_mixing',
  PLAN_DISPATCH_ORDERS = 'plan_dispatch_orders',
  MANAGE_DISPATCH_ORDERS = 'manage_dispatch_orders',
  PROCESS_ANALYSIS = 'process_analysis',
  MANAGE_ADJUSTMENTS = 'manage_adjustments',
  MANAGE_PALLET_LOCK = 'manage_pallet_lock',
  EXTEND_EXPIRY_DATE = 'extend_expiry_date',
  PLAN_INTERNAL_TRANSFERS = 'plan_internal_transfers',
  MANAGE_INTERNAL_TRANSFERS = 'manage_internal_transfers',
  MANAGE_RECIPES = 'manage_recipes',
  VIEW_TRACEABILITY = 'view_traceability',
  MANAGE_SUPPLIERS_CUSTOMERS = 'manage_suppliers_customers'
}

export type UserRole = 'admin' | 'planista' | 'magazynier' | 'kierownik magazynu' | 'lab' | 'operator_psd' | 'operator_agro' | 'operator_procesu' | 'user' | 'boss' | 'lider' | string;

export interface User {
  id: string;
  username: string;
  // FIX: Added password property to User interface for legacy support and initial setup.
  password?: string;
  role: UserRole;
  subRole: string; 
  pin?: string;
  email?: string;
  isActive?: boolean | number;
  passwordLastChanged?: string;
  isTemporaryPassword?: boolean;
  permissions?: Permission[];
}

export type ProductionEventType = 'problem' | 'downtime' | 'shift_change' | 'transition' | 'breakdown' | 'other';

export interface ProductionEvent {
    id: string;
    timestamp: string;
    type: ProductionEventType;
    description: string;
    user: string;
}

export interface WarehouseInfo {
  id: string;
  label: string;
  view: View;
  isLocationDetailLink?: boolean;
  permission?: Permission;
}

export interface MoveMetadata {
  movedBy: string;
  movedAt: string;
  previousLocation: string | null;
  targetLocation: string;
  action: string;
  notes?: string;
  deliveryOrderRef?: string;
  deliveryDate?: string;
  documentName?: string;
  deliveryPosition?: number;
}

export interface Document {
  name: string;
  type: string;
  url: string;
  addedBy: string;
  addedAt: string;
}

export interface AnalysisResult {
    name: string;
    value: string;
    unit: string;
}

export interface PalletData {
  nrPalety: string;
  nazwa: string;
  productGroup?: string;
  dataProdukcji: string;
  dataPrzydatnosci: string;
  initialWeight: number;
  currentWeight: number;
  isBlocked: boolean;
  blockReason?: string;
  batchNumber?: string;
  packageForm?: string;
  unit?: string; 
  labAnalysisNotes?: string;
  unitsPerPallet?: number;
  weightPerBag?: number;
  analysisResults?: AnalysisResult[];
  documents?: Document[];
  deliveryPosition?: number;
}

export interface RawMaterialLogEntry {
  id: string;
  palletData: PalletData;
  currentLocation: string | null;
  locationHistory: MoveMetadata[];
  dateAdded: string;
  lastValidatedAt: string;
}

export interface PackagingMaterialLogEntry {
    id: string;
    productName: string;
    initialWeight: number;
    currentWeight: number;
    dateAdded: string;
    unit?: string; 
    supplier?: string;
    batchNumber?: string;
    currentLocation: string | null;
    isBlocked?: boolean;
    blockReason?: string;
    locationHistory: MoveMetadata[];
    packageForm?: string;
}

export interface FinishedGoodItem {
  id: string;
  displayId: string;
  finishedGoodPalletId: string;
  productName: string;
  palletType: string;
  quantityKg: number;
  producedWeight: number;
  grossWeightKg: number;
  productionDate: string;
  expiryDate: string;
  status: 'pending_label' | 'available' | 'blocked' | 'dispatched' | 'consumed_in_mixing' | 'consumed_in_split' | 'returned_to_production' | 'consumed_and_archived';
  blockReason?: string;
  isBlocked: boolean;
  currentLocation: string | null;
  productionRunId?: string;
  sourceMixingTaskId?: string;
  psdTaskId?: string;
  batchId?: string;
  batchSplit?: { batchId: string; weight: number }[];
  sourceComposition?: { productName: string, weight: number, sourcePalletId: string }[];
  labAnalysisNotes?: string;
  documents?: Document[];
  analysisResults?: AnalysisResult[];
  locationHistory: MoveMetadata[];
  producedAt: string;
}

export interface AnalysisRange {
  id: string;
  name: string;
  min: number;
  max: number;
  unit: string;
}

export interface RecipeIngredient {
    productName: string;
    quantityKg: number;
}

export interface PackagingBOM {
    bag: { id: string; name: string };
    bagCapacityKg: number;
    foilRoll: { id: string; name: string };
    foilWeightPerBagKg: number;
    palletType: string;
    stretchFilm?: { id: string; name: string };
    slipSheet?: { id: string; name: string };
}

export interface Recipe {
    id: string;
    name: string;
    productionRateKgPerMinute: number;
    ingredients: RecipeIngredient[];
    packagingBOM?: PackagingBOM;
}

export interface DeliveryItem {
    id: string;
    position: number;
    productId: string;
    // FIX: Added productCode property to DeliveryItem interface as used in components.
    productCode: string;
    productName: string;
    batchNumber?: string;
    productionDate: string;
    expiryDate: string;
    netWeight?: number;
    unit?: string; 
    weightPerBag?: number;
    unitsPerPallet?: number;
    packageForm?: string;
    isBlocked: boolean;
    blockReason?: string;
    labNotes?: string;
    analysisResults?: AnalysisResult[];
    documents?: Document[];
    isCopied?: boolean;
}

// FIX: Added 'ARCHIVED' to DeliveryStatus type.
export type DeliveryStatus = 'REGISTRATION' | 'PENDING_LAB' | 'PENDING_WAREHOUSE' | 'COMPLETED' | 'ARCHIVED';

export interface DeliveryEvent {
    timestamp: string;
    user: string;
    action: string;
    details?: string;
}

export interface DeliveryCorrection {
    timestamp: string;
    user: string;
    notes?: string;
}

export interface Delivery {
    id: string;
    orderRef: string;
    supplier: string;
    deliveryDate: string;
    status: DeliveryStatus;
    items: DeliveryItem[];
    createdBy: string;
    createdAt: string;
    requiresLab: boolean;
    // FIX: Added optional notes property to Delivery interface.
    notes?: string;
    destinationWarehouse?: string;
    warehouseStageCompletedAt?: string;
    correctionLog?: DeliveryCorrection[];
    eventLog?: DeliveryEvent[];
}

export interface AgroConsumedMaterial {
    consumptionId: string;
    isAnnulled: boolean;
    productName: string;
    actualConsumedQuantityKg: number;
    actualSourcePalletId: string;
    batchId: string;
    isAdjustment?: boolean;
    adjustmentBucketId?: string;
}

export interface PsdTask {
    id: string;
    name: string;
    recipeId: string;
    recipeName: string;
    targetQuantity: number;
    plannedDate: string;
    shelfLifeMonths: number;
    status: 'planned' | 'ongoing' | 'completed' | 'cancelled';
    startTime?: string;
    createdAt: string;
    createdBy: string;
    updatedAt?: string;
    completedAt?: string;
    batches: PsdBatch[];
    notes?: string;
    hasShortages?: boolean;
    orderIndex?: number;
    events?: ProductionEvent[];
    samples?: LabSample[];
    suggestedTransferPallets?: string[];
}

export interface PsdBatch {
    id: string;
    batchNumber: number;
    targetWeight: number;
    status: 'planned' | 'ongoing' | 'completed';
    startTime?: string;
    endTime?: string;
    consumedPallets?: PsdConsumedMaterial[];
    producedGoods: PsdFinishedGood[];
    notes?: string;
    confirmationStatus?: {
        nirs?: 'pending' | 'ok' | 'nok';
        sampling?: 'pending' | 'ok';
    };
    weighingFinishedIngredients?: string[];
}

export interface PsdFinishedGood {
    id: string;
    displayId: string;
    productName: string;
    producedWeight: number;
    productionDate: string;
    expiryDate: string;
    isAnnulled: boolean;
}

export interface PsdConsumedMaterial {
    palletId: string;
    displayId: string;
    productName: string;
    consumedWeight: number;
    isAdjustment?: boolean;
}

export interface ProductionRun {
    id: string;
    recipeId: string;
    recipeName: string;
    targetBatchSizeKg: number;
    actualProducedQuantityKg?: number;
    plannedDate: string;
    status: 'planned' | 'ongoing' | 'paused' | 'completed' | 'archived' | 'cancelled';
    startTime?: string;
    endTime?: string;
    createdBy: string;
    createdAt: string;
    updatedAt?: string;
    notes?: string;
    hasShortages?: boolean;
    shelfLifeMonths: number;
    batches: PsdBatch[];
    actualIngredientsUsed?: AgroConsumedMaterial[];
    plannedIngredients?: { productName: string; requiredQuantityKg: number }[];
    events?: ProductionEvent[];
    samples?: LabSample[];
    suggestedTransferPallets?: string[];
    // FIX: Added downtimes property to track production pauses and interruptions as used in the production contexts.
    downtimes?: {
        type: string;
        startTime: string;
        endTime: string;
        durationMinutes: number;
        description: string;
    }[];
}

export interface AdjustmentOrder {
    id: string;
    status: 'planned' | 'material_picking' | 'processing' | 'completed' | 'cancelled';
    createdAt: string;
    createdBy: string;
    materials: AdjustmentMaterial[];
    productionRunId: string;
    recipeName: string;
    productionType: 'AGRO' | 'PSD';
    batchId?: string;
    reason?: string;
    preparationLocation?: string;
    completedAt?: string;
}

export interface AdjustmentMaterial {
    productName: string;
    quantityKg: number;
    pickedQuantityKg: number;
    sourcePalletId?: string;
}

export interface InventorySession {
    id: string;
    name: string;
    status: 'ongoing' | 'pending_review' | 'completed' | 'cancelled';
    createdAt: string;
    createdBy: string;
    locations: {
        locationId: string;
        status: 'pending' | 'scanned';
        scannedPallets: {
            palletId: string;
            countedQuantity: number;
        }[];
    }[];
    snapshot: {
        palletId: string;
        productName: string;
        expectedQuantity: number;
        locationId: string;
    }[];
    resolvedDiscrepancies?: {
        palletId: string;
        type: string;
        resolvedAt: string;
        resolvedBy: string;
    }[];
}

export interface LocationDefinition {
    id: string;
    name: string;
    type: 'warehouse' | 'zone' | 'rack' | 'shelf' | 'bin';
    capacity: number;
    description?: string;
    isLocked?: boolean;
}

export interface SortConfig<T> {
    key: keyof T | string;
    direction: 'ascending' | 'descending';
}

export interface InternalTransferOrder {
    id: string;
    status: 'PLANNED' | 'IN_TRANSIT' | 'COMPLETED' | 'CANCELLED';
    sourceWarehouse: string;
    destinationWarehouse: string;
    items: InternalTransferItem[];
    pallets: { palletId: string; productName: string; displayId?: string }[];
    createdBy: string;
    createdAt: string;
    dispatchedBy?: string;
    dispatchedAt?: string;
    receptionDetails?: {
        receivedBy: string;
        receivedAt: string;
    };
}

export interface InternalTransferItem {
    productName: string;
    requestedQty: number;
    unit: string;
}

export interface SelectOption {
    value: string | number;
    label: string;
}

export interface DispatchOrderItem {
    id: string;
    productName: string;
    itemType: 'finished_good' | 'mixing';
    requestedWeightKg: number;
    fulfilledWeightKg: number;
    fulfilledPallets: { palletId: string; displayId: string; weight: number }[];
    linkedMixingTaskId?: string;
}

export interface DispatchOrder {
    id: string;
    recipient: string;
    status: 'planned' | 'in_fulfillment' | 'completed' | 'cancelled';
    createdAt: string;
    createdBy: string;
    items: DispatchOrderItem[];
    sourceWarehouse?: 'Centrala' | 'OSIP';
}

export interface SavedView {
    id: string;
    name: string;
    page: string;
    filters: any;
}

export interface CombinedSearchResult {
    id: string;
    displayId: string;
    name: string;
    isRaw: boolean;
    location: string | null;
    status: string;
    isBlocked: boolean;
    blockReason?: string;
    date: string;
    originalItem: RawMaterialLogEntry | FinishedGoodItem | PackagingMaterialLogEntry;
    expiryStatus: 'expired' | 'critical' | 'warning' | 'default';
}

export interface MixingTargetCompositionItem {
    id: string;
    productName: string;
    quantity: number;
}

export interface MixingTask {
    id: string;
    name: string;
    status: 'planned' | 'ongoing' | 'completed' | 'cancelled';
    createdAt: string;
    createdBy: string;
    targetComposition: MixingTargetCompositionItem[];
    consumedSourcePallets: {
        palletId: string;
        displayId: string;
        productName: string;
        consumedWeight: number;
    }[];
}

export interface MixingContextValue {
    mixingTasks: MixingTask[];
    handleAddMixingTask: (taskData: Omit<MixingTask, 'id' | 'status' | 'createdAt' | 'createdBy' | 'consumedSourcePallets'>) => { success: boolean, message: string, newTask?: MixingTask };
    handleUpdateMixingTask: (taskId: string, updates: Partial<MixingTask>) => { success: boolean, message: string };
    handleDeleteMixingTask: (taskId: string) => { success: boolean, message: string };
    handleConsumeForMixing: (taskId: string, palletId: string, weightToConsume: number) => { success: boolean, message: string };
    handleCompleteMixingTask: (taskId: string) => { success: boolean, message: string, newPallet?: FinishedGoodItem, updatedSourcePallets?: FinishedGoodItem[] };
    handleCancelMixingTask: (taskId: string) => { success: boolean, message: string };
}

export interface PsdContextValue {
    psdTasks: PsdTask[];
    handleSavePsdTask: (taskData: PsdTask) => { success: boolean; message: string; task: PsdTask };
    handleUpdatePsdTask: (taskId: string, action: { type: string; payload?: any }) => { success: boolean; message: string; newPallet?: any };
    handleDeletePsdTask: (id: string) => { success: boolean; message: string };
    handleConsumeForPsd: (taskId: string, batchId: string, pallet: RawMaterialLogEntry, weightToConsume: number) => { success: boolean; message: string; updatedPallet?: RawMaterialLogEntry };
    handleReturnPsdConsumption: (taskId: string, batchId: string, itemToReturn: PsdConsumedMaterial) => { success: boolean; message: string };
    handleAddLabSample: (taskId: string, sampleBagNumber: string, archiveLocation?: string) => { success: boolean; message: string; newSample?: any };
    handleArchiveLabSample: (runId: string, sampleBagNumber: string, archiveLocation: string) => { success: boolean; message: string; };
    handleClearSuggestedTransfer: (runId: string) => void;
    handleUpdatePsdBatchConfirmationStatus: (taskId: string, batchId: string, step: 'nirs' | 'sampling', status: 'ok' | 'nok' | 'pending') => { success: boolean, message: string };
    handleAddProductionEvent: (taskId: string, event: Omit<ProductionEvent, 'id' | 'timestamp' | 'user'>) => { success: boolean, message: string };
    handleDeleteProductionEvent: (taskId: string, eventId: string) => { success: boolean, message: string };
}

export interface LogisticsContextValue {
    internalTransferOrders: InternalTransferOrder[];
    setInternalTransferOrders: React.Dispatch<React.SetStateAction<InternalTransferOrder[]>>;
    handleCreateInternalTransfer: (items: InternalTransferItem[], sourceWarehouse: string, destinationWarehouse: string) => { success: boolean; message: string };
    handleDispatchInternalTransfer: (orderId: string, palletIds: string[]) => { success: boolean; message: string };
    handleReceiveInternalTransfer: (orderId: string) => { success: boolean; message: string };
    handleCancelInternalTransfer: (orderId: string) => { success: boolean; message: string };
    dispatchOrders: DispatchOrder[];
    handleAddDispatchOrder: (orderData: Omit<DispatchOrder, 'id' | 'createdAt' | 'createdBy' | 'status'>) => { success: boolean; message: string };
    handleUpdateDispatchOrder: (orderId: string, updates: Partial<DispatchOrder>) => { success: boolean; message: string };
    handleDeleteDispatchOrder: (orderId: string) => { success: boolean; message: string };
    handleAssignPalletsToDispatchItem: (orderId: string, itemId: string, palletIds: string[]) => { success: boolean; message: string };
    handleFulfillDispatchItem: (orderId: string, palletId: string) => { action: 'FULFILLED' | 'SPLIT_SUGGESTED'; success: boolean; message: string; splitDetails?: any };
    handleFulfillTransferItem: (orderId: string, palletId: string) => { success: boolean; message: string };
    // FIX: Renamed from handleFulfillDispatchOrder to handleCompleteDispatchOrder to match implementation and component usage.
    handleCompleteDispatchOrder: (orderId: string) => { success: boolean; message: string };
}

export interface QueuedAction {
    id: string;
    type: string;
    payload: any;
    timestamp: number;
    status: 'pending' | 'synced' | 'failed';
    error?: string;
    source: 'Magazyn' | 'Produkcja';
}

export interface ChecklistItem {
    id: string;
    label: string;
    status: 'pending' | 'completed';
}

export interface OcrScannerModalProps {
    isOpen: boolean;
    onClose: () => void;
    onScan: (id: string) => void;
    rawMaterialsLogList: RawMaterialLogEntry[];
}

export interface AppNotification {
    id: string;
    type: 'receiving' | 'expiry' | 'new_order';
    title: string;
    body: string;
    timestamp: string;
    relatedItem?: RawMaterialLogEntry | FinishedGoodItem | ProductionRun | PsdTask | DispatchOrder | MixingTask;
    isRead: boolean;
    isUrgent: boolean;
}

export interface WarehouseCapacityModalProps {
    isOpen: boolean;
    onClose: () => void;
    capacityItems: CapacityItem[];
    summaryItems: SummaryItem[];
}

export interface CapacityItem {
    label: string;
    occupied: number;
    total?: number;
    colorClass: string;
}

export interface SummaryItem {
    label: string;
    value: string | number;
    icon: ReactNode;
    onClick?: () => void;
}

export interface WarehouseNavGroup {
    id: string;
    label: string;
    isGroup: true;
    warehouseIds: string[];
    defaultOpen?: boolean;
}

export interface WarehouseNavItem {
    id: string;
    isGroup: false;
}

export type WarehouseNavLayoutItem = WarehouseNavGroup | WarehouseNavItem;

export interface LabSample {
    id: string;
    sampleBagNumber: string;
    batchNumber: number;
    collectedAt: string;
    collectedBy: string;
    archiveLocation?: string;
}

export interface SplitProposalDetails {
    originalRunData: Partial<ProductionRun>;
    parts: {
        batchSize: number;
        date: string;
        productionTimeMinutes: number;
    }[];
}

export interface ColumnDef<T> {
    key: keyof T | string;
    label: string;
    headerClassName?: string;
    cellClassName?: string;
    render?: (item: T) => ReactNode;
}

export interface ExpiringPalletInfo {
    pallet: any;
    daysLeft: number;
    // FIX: Narrowed status type to exclude 'default', resolving type predicate assignability error in WarehouseContext.
    status: 'expired' | 'critical' | 'warning';
}

export interface ProductionRunTemplate {
    id: string;
    recipeId: string;
    recipeName: string;
    targetBatchSizeKg: number;
    shelfLifeMonths: number;
    notes?: string;
}

export interface AnalysisRangeHistoryEntry {
    id: string;
    timestamp: string;
    user: string;
    action: string;
    rangeId: string;
    rangeName: string;
    changeDetails: string;
}
