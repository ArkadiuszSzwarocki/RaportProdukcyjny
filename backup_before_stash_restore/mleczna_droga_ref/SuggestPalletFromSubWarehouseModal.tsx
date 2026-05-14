import React, { useState } from 'react';
// FIX: Correct import path for types.ts to be relative
import { RawMaterialLogEntry } from '../types';
import Button from './Button';
import Alert from './Alert';
import XCircleIcon from './icons/XCircleIcon';
import CubeIcon from './icons/CubeIcon';
// FIX: Corrected import path for constants.ts to be relative
import { SUB_WAREHOUSE_ID } from '../constants';
// FIX: Corrected import path for WarehouseContext to be relative.
import { useWarehouseContext } from './contexts/WarehouseContext';

interface SuggestPalletFromSubWarehouseModalProps {
  isOpen: boolean;
  onClose: () => void;
  pallet: RawMaterialLogEntry;
}

const SuggestPalletFromSubWarehouseModal: React.FC<SuggestPalletFromSubWarehouseModalProps> = ({ isOpen, onClose, pallet }) => {
    const { handleUniversalMove } = useWarehouseContext();
    const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

    if (!isOpen || !pallet) return null;

    const handleConfirm = () => {
        const result = handleUniversalMove(pallet.id, 'raw', SUB_WAREHOUSE_ID);
        setFeedback({ type: result.success ? 'success' : 'error', message: result.message });
        if (result.success) {
            setTimeout(onClose, 1500);
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-75 flex items-center justify-center p-4 z-[160]">
            <div className="bg-white dark:bg-secondary-800 rounded-lg shadow-xl p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-semibold text-primary-700 dark:text-primary-300 flex items-center gap-2">
                        <CubeIcon className="h-6 w-6"/> Potwierdź Przesunięcie
                    </h2>
                    <Button onClick={onClose} variant="secondary" className="p-1.5"><XCircleIcon className="h-5 w-5"/></Button>
                </div>

                {feedback && <Alert type={feedback.type} message={feedback.message} />}
                
                <div className="text-sm">
                    <p>Czy na pewno chcesz przenieść paletę na produkcję (do strefy {SUB_WAREHOUSE_ID})?</p>
                    <div className="mt-3 p-3 bg-slate-100 dark:bg-secondary-700 rounded-md">
                        <p><strong>Produkt:</strong> {pallet.palletData.nazwa}</p>
                        <p><strong>ID Palety:</strong> <span className="font-mono">{pallet.palletData.nrPalety}</span></p>
                        <p><strong>Waga:</strong> {pallet.palletData.currentWeight} kg</p>
                    </div>
                </div>

                <div className="flex justify-end gap-3 pt-4 mt-4 border-t dark:border-secondary-700">
                    <Button onClick={onClose} variant="secondary">Anuluj</Button>
                    <Button onClick={handleConfirm}>Tak, przenieś</Button>
                </div>
            </div>
        </div>
    );
};

export default SuggestPalletFromSubWarehouseModal;