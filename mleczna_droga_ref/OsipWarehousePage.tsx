
import React, { useMemo, useState } from 'react';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { useUIContext } from './contexts/UIContext';
import { RawMaterialLogEntry, ColumnDef, FinishedGoodItem } from '../types';
import { OSIP_WAREHOUSE_ID } from '../constants';
import StandardListView from './StandardListView';
import PalletTile from './PalletTile';
import WarehouseIcon from './icons/WarehouseIcon';
import Button from './Button';
import TruckIcon from './icons/TruckIcon';
import { useAppContext } from './contexts/AppContext'; 
import Input from './Input';
import SearchIcon from './icons/SearchIcon';
import TableCellsIcon from './icons/TableCellsIcon';
import LayoutGridIcon from './icons/LayoutGridIcon';
import OsipLayoutView from './OsipLayoutView';
import CubeIcon from './icons/CubeIcon';
import BeakerIcon from './icons/BeakerIcon';

const OsipWarehousePage: React.FC = () => {
    const { rawMaterialsLogList, finishedGoodsList } = useWarehouseContext();
    const { modalHandlers } = useUIContext();
    const { reservedForTransferPalletIds } = useAppContext(); 
    
    const [searchTerm, setSearchTerm] = useState('');
    const [viewMode, setViewMode] = useState<'list' | 'layout'>('list');
    const [itemTypeTab, setItemTypeTab] = useState<'raw' | 'fg'>('raw');

    const itemsInLocation = useMemo(() => {
        if (itemTypeTab === 'raw') {
            return (rawMaterialsLogList || []).filter(item => item.currentLocation === OSIP_WAREHOUSE_ID);
        } else {
            return (finishedGoodsList || []).filter(item => item.currentLocation === OSIP_WAREHOUSE_ID);
        }
    }, [rawMaterialsLogList, finishedGoodsList, itemTypeTab]);

    const filteredItems = useMemo(() => {
        if (!searchTerm.trim()) return itemsInLocation;
        const lowerSearch = searchTerm.toLowerCase();
        return itemsInLocation.filter((item: any) => {
            const displayId = itemTypeTab === 'raw' 
                ? item.palletData.nrPalety 
                : (item.displayId || item.id);
            const productName = itemTypeTab === 'raw'
                ? item.palletData.nazwa
                : item.productName;
            
            return displayId.toLowerCase().includes(lowerSearch) ||
                   productName.toLowerCase().includes(lowerSearch);
        });
    }, [itemsInLocation, searchTerm, itemTypeTab]);

    const handleCreateTransfer = () => {
        modalHandlers.openCreateInternalTransferModal();
    };

    const columns = useMemo((): ColumnDef<any>[] => {
        const baseCols: ColumnDef<any>[] = [
            { 
                key: 'displayId', 
                label: 'ID Palety',
                render: (item) => itemTypeTab === 'raw' ? item.palletData.nrPalety : (item.displayId || item.id)
            },
            { 
                key: 'productName', 
                label: 'Produkt',
                render: (item) => itemTypeTab === 'raw' ? item.palletData.nazwa : item.productName
            },
            { 
                key: 'weight', 
                label: 'Waga (kg)',
                render: (item) => itemTypeTab === 'raw' ? item.palletData.currentWeight.toFixed(2) : item.quantityKg.toFixed(2)
            },
            { 
                key: 'date', 
                label: 'Ważność',
                render: (item) => itemTypeTab === 'raw' ? item.palletData.dataPrzydatnosci : item.expiryDate
            },
            {
                key: 'status',
                label: 'Status',
                render: (item) => {
                    const isReserved = reservedForTransferPalletIds.has(item.id);
                    if (isReserved) {
                        return (
                            <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200">
                                Zarezerwowane
                            </span>
                        );
                    }
                    return null;
                },
            },
        ];
        return baseCols;
    }, [itemTypeTab, reservedForTransferPalletIds]);
    
    return (
        <div className="bg-white dark:bg-secondary-800 shadow-xl rounded-lg h-full flex flex-col">
            <header className="p-4 md:px-6 py-3 flex-shrink-0 border-b dark:border-secondary-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex flex-col">
                    <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300 whitespace-nowrap">
                        Magazyn Zewnętrzny ({OSIP_WAREHOUSE_ID})
                    </h2>
                    <div className="flex mt-2 bg-gray-100 dark:bg-secondary-700 p-1 rounded-lg w-fit">
                        <button 
                            onClick={() => setItemTypeTab('raw')}
                            className={`px-3 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1.5 ${itemTypeTab === 'raw' ? 'bg-white dark:bg-secondary-600 shadow text-purple-700 dark:text-purple-300' : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}
                        >
                            <BeakerIcon className="h-3.5 w-3.5" />
                            Surowce
                        </button>
                        <button 
                            onClick={() => setItemTypeTab('fg')}
                            className={`px-3 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1.5 ${itemTypeTab === 'fg' ? 'bg-white dark:bg-secondary-600 shadow text-green-700 dark:text-green-300' : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}
                        >
                            <CubeIcon className="h-3.5 w-3.5" />
                            Wyrób Gotowy
                        </button>
                    </div>
                </div>
                
                <div className="flex items-center gap-2 w-full sm:w-auto">
                    <div className="flex-grow sm:max-w-xs">
                        <Input
                            label=""
                            id="osip-search"
                            placeholder="Szukaj palet..."
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            icon={<SearchIcon className="h-5 w-5 text-gray-400" />}
                        />
                    </div>
                    
                    <div className="flex items-center bg-slate-200 dark:bg-secondary-700 p-1 rounded-lg">
                        <button 
                            onClick={() => setViewMode('list')} 
                            className={`p-2 rounded-md transition-all ${viewMode === 'list' ? 'bg-white dark:bg-secondary-600 shadow text-primary-600' : 'text-gray-500 hover:text-gray-700'}`}
                        >
                            <TableCellsIcon className="h-5 w-5" />
                        </button>
                        <button 
                            onClick={() => setViewMode('layout')} 
                            className={`p-2 rounded-md transition-all ${viewMode === 'layout' ? 'bg-white dark:bg-secondary-600 shadow text-primary-600' : 'text-gray-500 hover:text-gray-700'}`}
                        >
                            <LayoutGridIcon className="h-5 w-5" />
                        </button>
                    </div>

                    <Button 
                        onClick={handleCreateTransfer}
                        leftIcon={<TruckIcon className="h-5 w-5"/>}
                    >
                        Transfer
                    </Button>
                </div>
            </header>

            <div className="flex-grow overflow-auto scrollbar-hide">
                {filteredItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center text-gray-500 dark:text-gray-400 p-8">
                        <WarehouseIcon className="h-16 w-16 text-gray-300 dark:text-gray-600 mb-4" />
                        <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">
                            {searchTerm ? "Brak wyników wyszukiwania" : `Brak ${itemTypeTab === 'raw' ? 'surowców' : 'wyrobów gotowych'} w OSiP`}
                        </h3>
                    </div>
                ) : (
                    viewMode === 'list' ? (
                        <StandardListView
                            items={filteredItems}
                            columns={columns}
                            onRowClick={(item) => itemTypeTab === 'raw' ? modalHandlers.openPalletDetailModal(item) : modalHandlers.openFinishedGoodDetailModal(item)}
                            renderMobileCard={(item) => (
                                <PalletTile 
                                    item={item} 
                                    onClick={() => itemTypeTab === 'raw' ? modalHandlers.openPalletDetailModal(item) : modalHandlers.openFinishedGoodDetailModal(item)} 
                                />
                            )}
                            groupBy={null}
                            sortConfig={{ key: itemTypeTab === 'raw' ? 'palletData.dataPrzydatnosci' : 'expiryDate', direction: 'ascending' }}
                            requestSort={() => {}}
                            noResultsMessage={null}
                        />
                    ) : (
                        <OsipLayoutView pallets={filteredItems} />
                    )
                )}
            </div>
        </div>
    );
};

export default OsipWarehousePage;
