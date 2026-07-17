import React, { useMemo, useState } from 'react';
import { RawMaterialLogEntry, FinishedGoodItem, View } from '../types';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { useProductionContext } from './contexts/ProductionContext';
import { ALL_MANAGEABLE_WAREHOUSES } from '../constants';
import WarehouseIcon from './icons/WarehouseIcon';
import Button from './Button';
import WarehouseCapacityModal from './WarehouseCapacityModal';

const AllWarehousesViewPage: React.FC<{ onNavigate: (view: View, params?: any) => void }> = ({ onNavigate }) => {
    const { rawMaterialsLogList } = useWarehouseContext();
    const { finishedGoodsList } = useProductionContext();
    const [isCapacityModalOpen, setIsCapacityModalOpen] = useState(false);

    const stats = useMemo(() => ({
        totalPallets: (rawMaterialsLogList?.length || 0) + (finishedGoodsList?.length || 0),
        totalWeight: (rawMaterialsLogList || []).reduce((s, p) => s + p.palletData.currentWeight, 0) + (finishedGoodsList || []).reduce((s, p) => s + p.quantityKg, 0)
    }), [rawMaterialsLogList, finishedGoodsList]);

    return (
        <div className="bg-slate-50 dark:bg-secondary-900/50 p-4 md:p-6 h-full overflow-auto">
             <header className="flex justify-between items-center mb-6 border-b dark:border-secondary-700 pb-4">
                <div className="flex items-center gap-3">
                    <WarehouseIcon className="h-8 w-8 text-primary-600" />
                    <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300">Przegląd Magazynów</h2>
                </div>
                <Button onClick={() => setIsCapacityModalOpen(true)}>Statystyki Pojemności</Button>
            </header>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {ALL_MANAGEABLE_WAREHOUSES.filter(w => w.id !== 'all' && !w.isLocationDetailLink).map(wh => (
                    <div key={wh.id} onClick={() => onNavigate(wh.view)} className="p-4 bg-white dark:bg-secondary-800 rounded-lg shadow cursor-pointer hover:shadow-md transition-shadow">
                        <p className="font-bold text-primary-700 dark:text-primary-300">{wh.label}</p>
                        <p className="text-2xl font-bold mt-2">{(rawMaterialsLogList || []).filter(p => p.currentLocation === wh.id).length + (finishedGoodsList || []).filter(p => p.currentLocation === wh.id).length}</p>
                    </div>
                ))}
            </div>
            <WarehouseCapacityModal isOpen={isCapacityModalOpen} onClose={() => setIsCapacityModalOpen(false)} capacityItems={[]} summaryItems={[]} />
        </div>
    );
};

export default AllWarehousesViewPage;