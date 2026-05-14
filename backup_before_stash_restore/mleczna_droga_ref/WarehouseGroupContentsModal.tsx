import React, { useState, useMemo } from 'react';
import { WarehouseNavGroup, RawMaterialLogEntry, FinishedGoodItem } from '../types';
import { useAppContext } from './contexts/AppContext';
import Button from './Button';
import XCircleIcon from './icons/XCircleIcon';
import { useSortableData } from '../src/useSortableData';
import SortableHeader from './SortableHeader';
import { WAREHOUSE_RACK_PREFIX_MAP } from '../constants';
import { formatDate, getBlockInfo, getFinishedGoodStatusLabel } from '../src/utils';
import ClipboardIcon from './icons/ClipboardIcon';
import CheckCircleIcon from './icons/CheckCircleIcon';
import LockClosedIcon from './icons/LockClosedIcon';

interface WarehouseGroupContentsModalProps {
    isOpen: boolean;
    onClose: () => void;
    group: WarehouseNavGroup | null;
}

type ListItem = {
  isRaw: boolean;
  id: string;
  displayId: string;
  productName: string;
  location: string;
  date: string;
  isBlocked: boolean;
  blockReason?: string;
  originalItem: RawMaterialLogEntry | FinishedGoodItem;
  // FIX: Added 'type' property to ListItem to match its usage in the component.
  type: 'Surowiec' | 'Wyrób Gotowy';
};

const WarehouseGroupContentsModal: React.FC<WarehouseGroupContentsModalProps> = ({ isOpen, onClose, group }) => {
    const { rawMaterialsLogList, finishedGoodsList, modalHandlers } = useAppContext();
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const items = useMemo((): ListItem[] => {
        if (!group) return [];

        const groupWarehouseIds = new Set(group.warehouseIds);
        const groupPrefixes = group.warehouseIds.flatMap(whId => WAREHOUSE_RACK_PREFIX_MAP[whId] || []);

        const allItems = [
            ...(rawMaterialsLogList || []).map(p => ({ ...p, isRaw: true, originalItem: p })),
            ...(finishedGoodsList || []).map(p => ({ ...p, isRaw: false, originalItem: p }))
        ];

        return allItems.filter(p => {
            if (!p.currentLocation) return false;
            if (groupWarehouseIds.has(p.currentLocation)) return true;
            for (const prefix of groupPrefixes) {
                if (p.currentLocation.startsWith(prefix)) return true;
            }
            return false;
        }).map(p => {
            const isRaw = p.isRaw;
            const blockInfo = getBlockInfo(p.originalItem);
            return {
                isRaw,
                id: p.id,
                displayId: isRaw ? (p as RawMaterialLogEntry).palletData.nrPalety : ((p as FinishedGoodItem).finishedGoodPalletId || p.id),
                productName: isRaw ? (p as RawMaterialLogEntry).palletData.nazwa : (p as FinishedGoodItem).productName,
                location: p.currentLocation || 'Brak',
                date: isRaw ? (p as RawMaterialLogEntry).palletData.dataPrzydatnosci : (p as FinishedGoodItem).expiryDate,
                isBlocked: blockInfo.isBlocked,
                blockReason: blockInfo.reason || undefined,
                originalItem: p.originalItem,
                // FIX: Added 'type' property to the returned object to match the updated ListItem type.
                type: isRaw ? 'Surowiec' : 'Wyrób Gotowy',
            };
        });
    }, [group, rawMaterialsLogList, finishedGoodsList]);

    const { items: sortedItems, requestSort, sortConfig } = useSortableData(items, { key: 'location', direction: 'ascending' });

    const handleRowClick = (item: ListItem) => {
        if (item.isRaw) {
            modalHandlers.openPalletDetailModal(item.originalItem as RawMaterialLogEntry);
        } else {
            modalHandlers.openFinishedGoodDetailModal(item.originalItem as FinishedGoodItem);
        }
    };

    if (!isOpen || !group) return null;

    return (
        <div className="fixed inset-0 bg-gray-800 bg-opacity-75 flex items-center justify-center p-4 z-[150]" onClick={onClose}>
            <div className="bg-white dark:bg-secondary-800 rounded-lg shadow-xl p-6 w-full max-w-6xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center pb-3 border-b dark:border-secondary-600 mb-4">
                    <h2 className="text-xl font-semibold text-primary-700 dark:text-primary-300">Zawartość Grupy: {group.label} ({items.length})</h2>
                    <Button onClick={onClose} variant="secondary" className="p-1.5 -mr-1.5"><XCircleIcon className="h-6 w-6"/></Button>
                </div>
                <div className="flex-grow overflow-auto pr-2 scrollbar-hide">
                    {sortedItems.length === 0 ? (
                        <p className="text-center text-gray-500 dark:text-gray-400 p-8">Brak palet w tej grupie magazynów.</p>
                    ) : (
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-secondary-700 text-sm">
                            <thead className="bg-gray-100 dark:bg-secondary-700 sticky top-0">
                                <tr>
                                    <SortableHeader columnKey="displayId" sortConfig={sortConfig} requestSort={requestSort}>ID Palety</SortableHeader>
                                    <SortableHeader columnKey="productName" sortConfig={sortConfig} requestSort={requestSort}>Produkt</SortableHeader>
                                    <SortableHeader columnKey="location" sortConfig={sortConfig} requestSort={requestSort}>Lokalizacja</SortableHeader>
                                    <SortableHeader columnKey="type" sortConfig={sortConfig} requestSort={requestSort}>Typ</SortableHeader>
                                    <SortableHeader columnKey="date" sortConfig={sortConfig} requestSort={requestSort}>Data Ważności</SortableHeader>
                                    <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-300">Status</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-secondary-800 divide-y divide-gray-200 dark:divide-secondary-700">
                                {sortedItems.map(item => (
                                    <tr key={item.id} onClick={() => handleRowClick(item)} className="hover:bg-gray-50 dark:hover:bg-secondary-700/50 cursor-pointer">
                                        <td className="px-3 py-2 whitespace-nowrap">
                                            <div className="flex items-center gap-2 group">
                                                <span className="font-mono text-primary-600 dark:text-primary-400">{item.displayId}</span>
                                                <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(item.displayId); setCopiedId(item.displayId); setTimeout(() => setCopiedId(null), 2000); }} title={copiedId === item.displayId ? "Skopiowano!" : "Kopiuj ID"} className="p-1 rounded-full opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity">
                                                    {copiedId === item.displayId ? <CheckCircleIcon className="h-4 w-4 text-green-500" /> : <ClipboardIcon className="h-4 w-4 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" />}
                                                </button>
                                            </div>
                                        </td>
                                        <td className="px-3 py-2">{item.productName}</td>
                                        <td className="px-3 py-2 font-mono">{item.location}</td>
                                        <td className="px-3 py-2"><span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${item.isRaw ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200' : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'}`}>{item.type}</span></td>
                                        <td className="px-3 py-2">{formatDate(item.date)}</td>
                                        <td className="px-3 py-2">
                                            {item.isBlocked ? (
                                                <div className="flex items-center text-red-600 dark:text-red-400" title={item.blockReason}><LockClosedIcon className="h-4 w-4 mr-1"/> Zablokowana</div>
                                            ) : (
                                                <div className="flex items-center text-green-600 dark:text-green-400"><CheckCircleIcon className="h-4 w-4 mr-1"/> Dostępna</div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
                 <footer className="px-6 py-3 bg-gray-50 dark:bg-secondary-900/50 border-t dark:border-secondary-700 flex justify-end">
                    <Button onClick={onClose}>Zamknij</Button>
                </footer>
            </div>
        </div>
    );
};

export default WarehouseGroupContentsModal;
