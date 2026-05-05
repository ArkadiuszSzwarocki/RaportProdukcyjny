
import React, { useMemo, useState } from 'react';
import { RawMaterialLogEntry, Document } from '../types';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { useUIContext } from './contexts/UIContext';
import PalletTile from './PalletTile';
import Input from './Input';
import Button from './Button';
import SearchIcon from './icons/SearchIcon';
import ArrowPathIcon from './icons/ArrowPathIcon';
import WarehouseIcon from './icons/WarehouseIcon';
import { useSortableData } from '../src/useSortableData';
import SortableHeader from './SortableHeader';
import { formatDate, getBlockInfo, getActionLabel } from '../src/utils';
import LockClosedIcon from './icons/LockClosedIcon';
import CheckCircleIcon from './icons/CheckCircleIcon';
import { SOURCE_WAREHOUSE_ID_MS01 } from '../constants';
import ClipboardListIcon from './icons/ClipboardListIcon';
import DocumentTextIcon from './icons/DocumentTextIcon';

export const MS01SourceWarehousePage: React.FC = () => {
    const { rawMaterialsLogList, refreshRawMaterials } = useWarehouseContext();
    const { modalHandlers } = useUIContext();
    const [searchTerm, setSearchTerm] = useState('');
    const [isRefreshing, setIsRefreshing] = useState(false);

    const handleRefresh = async () => {
        setIsRefreshing(true);
        try {
            await refreshRawMaterials();
        } finally {
            setIsRefreshing(false);
        }
    };

    const itemsInLocation = useMemo(() =>
        (rawMaterialsLogList || []).filter(item => item.currentLocation === SOURCE_WAREHOUSE_ID_MS01),
        [rawMaterialsLogList]
    );

    const filteredItems = useMemo(() => {
        if (!searchTerm.trim()) return itemsInLocation;
        const lowerSearch = searchTerm.toLowerCase();
        return itemsInLocation.filter(item =>
            item.palletData.nrPalety.toLowerCase().includes(lowerSearch) ||
            item.palletData.nazwa.toLowerCase().includes(lowerSearch)
        );
    }, [itemsInLocation, searchTerm]);

    const { items: sortedItems, requestSort, sortConfig } = useSortableData(filteredItems, { key: 'palletData.dataPrzydatnosci', direction: 'ascending' });

    const handleItemClick = (item: RawMaterialLogEntry) => {
        modalHandlers.openPalletDetailModal(item);
    };

    const getNotesText = (item: RawMaterialLogEntry): string => {
        const notes: string[] = [];
        if (item.palletData.labAnalysisNotes) notes.push(`Notatki główne:\n${item.palletData.labAnalysisNotes}`);
        const historyNotes = (item.locationHistory || [])
            .filter(h => h.notes && (h.action.includes('lab') || h.action.includes('block') || h.action.includes('note')))
            .map(h => `[${formatDate(h.movedAt, true)} / ${h.movedBy} / ${getActionLabel(h.action)}]:\n${h.notes}`);
        notes.push(...[...historyNotes].reverse());
        return [...new Set(notes)].join('\n\n---\n\n');
    };

    return (
        <div className="bg-white dark:bg-secondary-800 shadow-xl rounded-lg h-full flex flex-col">
            <header className="p-4 md:px-6 py-3 flex-shrink-0 border-b dark:border-secondary-700">
                <div className="flex flex-col gap-3 mb-3">
                    <h2 className="text-xl md:text-2xl font-semibold text-primary-700 dark:text-primary-300 break-words">
                        Magazyn Główny ({SOURCE_WAREHOUSE_ID_MS01})
                    </h2>
                </div>
                <div className="flex gap-2 items-center flex-wrap">
                    <Button
                        onClick={handleRefresh}
                        disabled={isRefreshing}
                        variant="secondary"
                        className="h-10 px-4 whitespace-nowrap"
                        leftIcon={<ArrowPathIcon className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />}
                    >
                        {isRefreshing ? 'Odświeżanie...' : 'Odśwież'}
                    </Button>
                    <div className="flex-grow min-w-xs max-w-xs">
                        <Input label="" id="ms01-pallets-search" placeholder="Szukaj palet..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} icon={<SearchIcon className="h-5 w-5 text-gray-400" />} />
                    </div>
                </div>
            </header>
            <div className="flex-grow overflow-auto scrollbar-hide p-4">
                {sortedItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center text-gray-500 dark:text-gray-400">
                        <WarehouseIcon className="h-16 w-16 text-gray-300 dark:text-gray-600 mb-4" />
                        <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Magazyn {SOURCE_WAREHOUSE_ID_MS01} jest pusty</h3>
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:hidden">
                            {sortedItems.map((item) => (
                                <PalletTile key={item.id} item={item} onClick={() => handleItemClick(item)} />
                            ))}
                        </div>
                        <table className="min-w-full text-sm hidden md:table table-fixed">
                            <thead className="bg-gray-100 dark:bg-secondary-700">
                                <tr>
                                    <SortableHeader columnKey="palletData.nrPalety" sortConfig={sortConfig} requestSort={requestSort} thClassName="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-300 w-[20%]">ID Palety</SortableHeader>
                                    <SortableHeader columnKey="palletData.nazwa" sortConfig={sortConfig} requestSort={requestSort} thClassName="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-300 w-[30%]">Produkt</SortableHeader>
                                    <SortableHeader columnKey="currentLocation" sortConfig={sortConfig} requestSort={requestSort} thClassName="px-3 py-2 text-center font-medium text-gray-500 dark:text-gray-300 w-[15%]">Lok.</SortableHeader>
                                    <SortableHeader columnKey="palletData.currentWeight" sortConfig={sortConfig} requestSort={requestSort} thClassName="px-3 py-2 text-right font-medium text-gray-500 dark:text-gray-300 w-[10%]">Waga</SortableHeader>
                                    <SortableHeader columnKey="palletData.dataPrzydatnosci" sortConfig={sortConfig} requestSort={requestSort} thClassName="px-3 py-2 text-center font-medium text-gray-500 dark:text-gray-300 w-[10%]">Ważność</SortableHeader>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-300 w-[15%]">Status</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-secondary-800 divide-y divide-gray-200 dark:divide-secondary-700">
                                {sortedItems.map((item) => {
                                    const { isBlocked, reason } = getBlockInfo(item);
                                    const notes = getNotesText(item);
                                    const docs = item.palletData.documents || [];
                                    return (
                                        <tr key={item.id} onClick={() => handleItemClick(item)} className="hover:bg-gray-50 dark:hover:bg-secondary-700/50 cursor-pointer">
                                            <td className="px-3 py-2 whitespace-normal break-all font-mono text-xs">
                                                <div className="flex items-center gap-2">
                                                    {isBlocked ? <LockClosedIcon className="h-4 w-4 text-red-500 flex-shrink-0" title={reason || 'Zablokowana'} /> : <CheckCircleIcon className="h-4 w-4 text-green-500 flex-shrink-0" title="Dostępna" />}
                                                    {item.palletData.nrPalety}
                                                    {notes && <button onClick={(e) => { e.stopPropagation(); modalHandlers.openTextDisplayModal(`Notatki dla ${item.palletData.nrPalety}`, notes); }} className="text-gray-400 hover:text-primary-500"><ClipboardListIcon className="h-4 w-4"/></button>}
                                                    {docs.length > 0 && <button onClick={(e) => { e.stopPropagation(); modalHandlers.openDocumentListModal(`Dokumenty dla ${item.palletData.nrPalety}`, docs); }} className="text-gray-400 hover:text-primary-500"><DocumentTextIcon className="h-4 w-4"/></button>}
                                                </div>
                                            </td>
                                            <td className="px-3 py-2 font-medium">{item.palletData.nazwa}</td>
                                            <td className="px-3 py-2 font-mono text-xs text-center">{item.currentLocation}</td>
                                            <td className="px-3 py-2 text-right font-mono">{item.palletData.currentWeight.toFixed(0)} kg</td>
                                            <td className="px-3 py-2 text-center">{formatDate(item.palletData.dataPrzydatnosci)}</td>
                                            <td className="px-3 py-2">{isBlocked ? <span className="text-red-600 font-semibold truncate block">{reason}</span> : 'Dostępna'}</td>
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
