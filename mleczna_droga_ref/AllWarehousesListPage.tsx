import React, { useMemo, useState } from 'react';
import { RawMaterialLogEntry, FinishedGoodItem, PackagingMaterialLogEntry } from '../types';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { useProductionContext } from './contexts/ProductionContext';
import { useUIContext } from './contexts/UIContext';
import Input from './Input';
import SearchIcon from './icons/SearchIcon';
import WarehouseIcon from './icons/WarehouseIcon';
import { useSortableData } from '../src/useSortableData';
import SortableHeader from './SortableHeader';
import { formatDate, getBlockInfo } from '../src/utils';
import LockClosedIcon from './icons/LockClosedIcon';
import CheckCircleIcon from './icons/CheckCircleIcon';
import PalletTile from './PalletTile';

type CombinedItem = { 
    id: string;
    isRaw: boolean;
    isPackaging: boolean;
    displayId: string;
    productName: string;
    location: string;
    date: string;
    type: 'Surowiec' | 'Wyrób Gotowy' | 'Opakowanie';
    originalItem: RawMaterialLogEntry | FinishedGoodItem | PackagingMaterialLogEntry;
};

const AllWarehousesListPage: React.FC<{ onNavigate: (view: any) => void }> = ({ onNavigate }) => {
    const { rawMaterialsLogList, packagingMaterialsLog } = useWarehouseContext();
    const { finishedGoodsList } = useProductionContext();
    const { modalHandlers } = useUIContext();
    const [searchTerm, setSearchTerm] = useState('');

    const combinedItems = useMemo((): CombinedItem[] => {
        const raw = (rawMaterialsLogList || [])
            .map(item => ({
                id: item.id,
                isRaw: true,
                isPackaging: false,
                displayId: item.palletData.nrPalety,
                productName: item.palletData.nazwa,
                location: item.currentLocation || 'Brak',
                date: item.palletData.dataPrzydatnosci,
                type: 'Surowiec' as const,
                originalItem: item,
            }));

        const fg = (finishedGoodsList || [])
            .map(item => ({
                id: item.id,
                isRaw: false,
                isPackaging: false,
                displayId: item.finishedGoodPalletId || item.id,
                productName: item.productName,
                location: item.currentLocation || 'Brak',
                date: item.expiryDate,
                type: 'Wyrób Gotowy' as const,
                originalItem: item,
            }));
            
        const pkg = (packagingMaterialsLog || [])
            .map(item => ({
                id: item.id,
                isRaw: false,
                isPackaging: true,
                displayId: item.id,
                productName: item.productName,
                location: item.currentLocation || 'Brak',
                date: item.dateAdded,
                type: 'Opakowanie' as const,
                originalItem: item,
            }));

        return [...raw, ...fg, ...pkg];
    }, [rawMaterialsLogList, finishedGoodsList, packagingMaterialsLog]);

    const filteredItems = useMemo(() => {
        if (!searchTerm.trim()) return combinedItems;
        const lowerSearch = searchTerm.toLowerCase();
        return combinedItems.filter(item =>
            item.displayId.toLowerCase().includes(lowerSearch) ||
            item.productName.toLowerCase().includes(lowerSearch) ||
            item.location.toLowerCase().includes(lowerSearch)
        );
    }, [combinedItems, searchTerm]);

    const { items: sortedItems, requestSort, sortConfig } = useSortableData(filteredItems, { key: 'location', direction: 'ascending' });

    const handleRowClick = (item: CombinedItem) => {
        if (item.isPackaging) {
            modalHandlers.openPackagingMaterialDetailModal(item.originalItem as PackagingMaterialLogEntry);
        } else if (item.isRaw) {
            modalHandlers.openPalletDetailModal(item.originalItem as RawMaterialLogEntry);
        } else {
            modalHandlers.openFinishedGoodDetailModal(item.originalItem as FinishedGoodItem);
        }
    };

    return (
        <div className="bg-white dark:bg-secondary-800 shadow-xl rounded-lg h-full flex flex-col">
            <header className="p-4 md:px-6 py-3 flex-shrink-0 border-b dark:border-secondary-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300 whitespace-nowrap">
                    Wszystkie Magazyny - Lista Palet
                </h2>
                <div className="w-full sm:w-auto sm:max-w-xs">
                    <Input
                        label=""
                        id="all-pallets-search"
                        placeholder="Szukaj palet..."
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        icon={<SearchIcon className="h-5 w-5 text-gray-400" />}
                    />
                </div>
            </header>
            <div className="flex-grow overflow-auto scrollbar-hide p-4">
                {sortedItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center text-gray-500 dark:text-gray-400">
                        <WarehouseIcon className="h-16 w-16 text-gray-300 dark:text-gray-600 mb-4" />
                        <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Magazyny są puste</h3>
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:hidden">
                            {sortedItems.map((item) => (
                                <PalletTile key={item.id} item={item.originalItem as any} onClick={() => handleRowClick(item)} />
                            ))}
                        </div>
                        <table className="min-w-full text-sm hidden md:table">
                            <thead className="bg-gray-100 dark:bg-secondary-700">
                                <tr>
                                    <SortableHeader columnKey="displayId" sortConfig={sortConfig} requestSort={requestSort}>ID Palety</SortableHeader>
                                    <SortableHeader columnKey="productName" sortConfig={sortConfig} requestSort={requestSort}>Produkt</SortableHeader>
                                    <SortableHeader columnKey="location" sortConfig={sortConfig} requestSort={requestSort}>Lokalizacja</SortableHeader>
                                    <SortableHeader columnKey="type" sortConfig={sortConfig} requestSort={requestSort}>Typ</SortableHeader>
                                    <SortableHeader columnKey="date" sortConfig={sortConfig} requestSort={requestSort}>Data / Ważność</SortableHeader>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-300">Status</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-secondary-800 divide-y divide-gray-200 dark:divide-secondary-700">
                                {sortedItems.map((item) => {
                                    const { isBlocked, reason } = getBlockInfo(item.originalItem);
                                    return (
                                        <tr key={item.id} onClick={() => handleRowClick(item)} className="hover:bg-gray-50 dark:hover:bg-secondary-700/50 cursor-pointer">
                                            <td className="px-3 py-2 whitespace-nowrap font-mono flex items-center gap-2">
                                                {isBlocked 
                                                    ? <LockClosedIcon className="h-4 w-4 text-red-500 flex-shrink-0" title={reason || 'Zablokowana'} /> 
                                                    : <CheckCircleIcon className="h-4 w-4 text-green-500 flex-shrink-0" title="Dostępna" />
                                                }
                                                {item.displayId}
                                            </td>
                                            <td className="px-3 py-2">{item.productName}</td>
                                            <td className="px-3 py-2 font-mono">{item.location}</td>
                                            <td className="px-3 py-2">
                                                <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${item.isRaw ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200' : (item.isPackaging ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200' : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200')}`}>
                                                    {item.type}
                                                </span>
                                            </td>
                                            <td className="px-3 py-2 whitespace-nowrap">{formatDate(item.date)}</td>
                                            <td className="px-3 py-2 whitespace-nowrap">{isBlocked ? <span className="text-red-600 font-semibold">{reason}</span> : 'Dostępna'}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </>
                )}
            </div>
        </div>
    );
};

export default AllWarehousesListPage;
