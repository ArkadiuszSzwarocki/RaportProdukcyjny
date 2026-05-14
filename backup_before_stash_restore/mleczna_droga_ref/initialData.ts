
import { User, RawMaterialLogEntry, FinishedGoodItem, Delivery, ProductionRun, PsdTask, MixingTask, DispatchOrder, AdjustmentOrder, PackagingMaterialLogEntry, UserRole, Permission } from './types';

// ZACHOWUJEMY UŻYTKOWNIKÓW
export const INITIAL_USERS: User[] = [
  { id: 'u-1', username: 'admin', password: 'password', role: 'admin' as UserRole, subRole: 'AGRO', pin: '1234', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-2', username: 'planista', password: 'password', role: 'planista' as UserRole, subRole: 'AGRO', pin: '1111', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-3', username: 'magazynier', password: 'password', role: 'magazynier' as UserRole, subRole: 'AGRO', pin: '2222', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-4', username: 'kierownik', password: 'password', role: 'kierownik magazynu' as UserRole, subRole: 'AGRO', pin: '3333', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-5', username: 'lab', password: 'password', role: 'lab' as UserRole, subRole: 'AGRO', pin: '4444', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-6', username: 'operator_psd', password: 'password', role: 'operator_psd' as UserRole, subRole: 'AGRO', pin: '5555', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-8', username: 'operator_agro', password: 'password', role: 'operator_agro' as UserRole, subRole: 'AGRO', pin: '6666', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-7', username: 'user', password: 'password', role: 'user' as UserRole, subRole: 'AGRO', pin: '0000', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-9', username: 'operator_procesu_1', password: 'password', role: 'operator_procesu' as UserRole, subRole: 'AGRO', pin: '7777', passwordLastChanged: new Date().toISOString(), permissions: [] },
  { id: 'u-10', username: 'operator_procesu_2', password: 'password', role: 'operator_procesu' as UserRole, subRole: 'AGRO', pin: '8888', passwordLastChanged: new Date().toISOString(), permissions: [] },
];

// CZYSZCZENIE DANYCH TRANSAKCYJNYCH I KATALOGÓW
export const INITIAL_RAW_MATERIALS: RawMaterialLogEntry[] = [];
export const INITIAL_FINISHED_GOODS: FinishedGoodItem[] = [];
export const INITIAL_DELIVERIES: Delivery[] = [];
export const INITIAL_PRODUCTION_RUNS: ProductionRun[] = [];
export const INITIAL_PSD_TASKS: PsdTask[] = [];
export const INITIAL_MIXING_TASKS: MixingTask[] = [];
export const INITIAL_DISPATCH_ORDERS: DispatchOrder[] = [];
export const INITIAL_ADJUSTMENT_ORDERS: AdjustmentOrder[] = [];
export const INITIAL_PACKAGING_MATERIALS: PackagingMaterialLogEntry[] = [];
export const INITIAL_PRODUCTS: {name: string, type: string}[] = [];
