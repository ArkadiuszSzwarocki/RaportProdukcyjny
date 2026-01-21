
import React, { useState, useMemo } from 'react';
import { MixingTask, FinishedGoodItem, View } from '../types';
import Button from './Button';
import Alert from './Alert';
import MixerIcon from './icons/MixerIcon';
import ConsumePartialPalletModal from './ConsumePartialPalletModal';
import { useMixingContext } from './contexts/MixingContext';
import { useProductionContext } from './contexts/ProductionContext';
import Input from './Input';
import QrCodeIcon from './icons/QrCodeIcon';
import { getBlockInfo, formatDate } from '../src/utils';
import { useAppContext } from './contexts/AppContext';
import { useUIContext } from './contexts/UIContext';
import ConfirmationModal from './ConfirmationModal';
import PlayIcon from './icons/PlayIcon';

export const MixingWorkerPage: React.FC = () => {
    const { mixingTasks, handleConsumeForMixing, handleCompleteMixingTask, handleUpdateMixingTask, handleCancelMixingTask } = useMixingContext();
    const { finishedGoodsList } = useProductionContext();
    const { findPalletByUniversalId, handleSetView } = useAppContext();
    const { modalHandlers, showToast } = useUIContext();

    const [palletToConsume, setPalletToConsume] = useState<FinishedGoodItem | null>(null);
    const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info', message: string } | null>(null);
    const [scannedValue, setScannedValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isClosing, setIsClosing] = useState(false);
    const [isCancelConfirmOpen, setIsCancelConfirmOpen] = useState(false);


    const activeTask = useMemo(() => 
        (mixingTasks || []).find(task => task.status === 'ongoing'), 
    [mixingTasks]);
    
    const plannedTasks = useMemo(() => 
        (mixingTasks || []).filter(task => task.status === 'planned').sort((a,b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()), 
    [mixingTasks]);

    const handleStartTask = (taskToStart: MixingTask) => {
        const isAnyTaskOngoing = mixingTasks.some(t => t.status === 'ongoing');
        if (isAnyTaskOngoing) {
            showToast('Inne zlecenie jest już w toku. Zakończ je przed rozpoczęciem nowego.', 'error');
            return;
        }
        handleUpdateMixingTask(taskToStart.id, { status: 'ongoing' });
        showToast(`Rozpoczęto zlecenie ${taskToStart.name}`, 'success');
    };

    const compositionStatus = useMemo(() => {
        if (!activeTask) return [];
        return activeTask.targetComposition.map(target => {
            const consumed = (activeTask.consumedSourcePallets || [])
                .filter(c => c.productName === target.productName)
                .reduce((sum, c) => sum + c.consumedWeight, 0);
            return {
                ...target,
                consumed,
                progress: target.quantity > 0 ? (consumed / target.quantity) * 100 : 0,
            };
        });
    }, [activeTask]);

    const fefoSuggestions = useMemo(() => {
        if (!activeTask) return [];

        const allConsumedPalletIds = new Set((activeTask.consumedSourcePallets || []).map(p => p.palletId));
        
        const suggestions = activeTask.targetComposition
            .filter(item => {
                const status = compositionStatus.find(cs => cs.id === item.id);
                return (status?.consumed || 0) < item.quantity;
            })
            .map(item => {
                const availablePallets = (finishedGoodsList || [])
                    .filter(p => 
                        p.productName === item.productName && 
                        p.status === 'available' && 
                        !getBlockInfo(p).isBlocked &&
                        !allConsumedPalletIds.has(p.id)
                    )
                    .sort((a, b) => new Date(a.expiryDate).getTime() - new Date(b.expiryDate).getTime());
                
                let remainingNeeded = item.quantity - (compositionStatus.find(cs => cs.id === item.id)?.consumed || 0);
                const suggestedPallets = [];
                
                for (const pallet of availablePallets) {
                    if (remainingNeeded <= 0) break;
                    suggestedPallets.push(pallet);
                    remainingNeeded -= pallet.quantityKg;
                }

                return {
                    itemId: item.id,
                    productName: item.productName,
                    suggestions: suggestedPallets,
                };
            })
            .filter(s => s.suggestions.length > 0);
        return suggestions;
    }, [activeTask, finishedGoodsList, compositionStatus]);

    const handleScanSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const palletId = scannedValue.trim();
        if (!activeTask || !palletId || isLoading) return;
        
        setIsLoading(true);
        setFeedback(null);
        
        setTimeout(() => {
            const palletResult = findPalletByUniversalId(palletId);
            
            if (!palletResult || palletResult.type !== 'fg') {
                setFeedback({ type: 'error', message: `Nie znaleziono palety wyrobu gotowego o ID ${palletId}.` });
            } else {
                const pallet = palletResult.item as FinishedGoodItem;
                if (pallet.status !== 'available' || getBlockInfo(pallet).isBlocked) {
                    setFeedback({ type: 'error', message: `Paleta ${palletId} jest zablokowana lub niedostępna.` });
                } else if (!compositionStatus.some(c => c.productName === pallet.productName && c.consumed < c.quantity)) {
                    setFeedback({ type: 'error', message: `Produkt "${pallet.productName}" nie jest wymagany lub został już w pełni pobrany.` });
                } else {
                    setPalletToConsume(pallet);
                }
            }
            
            setScannedValue('');
            setIsLoading(false);
        }, 300);
    };

    const handleConfirmConsumption = (weightToConsume: number) => {
        if (!activeTask || !palletToConsume) return;
        
        const result = handleConsumeForMixing(activeTask.id, palletToConsume.id, weightToConsume);
        setFeedback({ type: result.success ? 'success' : 'error', message: result.message });
        setPalletToConsume(null);
        if(result.success) {
            setTimeout(() => setFeedback(null), 8089);
        }
    };
    
    // --- NEW WORKFLOW FUNCTIONS ---

    const handleConfirmCancel = () => {
        if (!activeTask) return;
        const result = handleCancelMixingTask(activeTask.id);
        showToast(result.message, result.success ? 'success' : 'error');
        if (result.success) {
            handleSetView(View.MIXING_WORKER);
        }
        setIsCancelConfirmOpen(false);
    };

    const handleInitiateClose = () => {
        setIsClosing(true);
    };

    const handleCompleteAndPrintFinal = (newPallet: FinishedGoodItem) => {
        modalHandlers.openNetworkPrintModal({
            type: 'finished_good',
            data: newPallet,
            onSuccess: () => {
                showToast('Zlecenie miksowania zostało pomyślnie zakończone.', 'success');
                handleSetView(View.MIXING_WORKER);
            }
        });
    };

    const handlePrintSourceAndFinal = () => {
        if (!activeTask) return;
        const result = handleCompleteMixingTask(activeTask.id);
        setIsClosing(false);

        if (result.success) {
            if (result.updatedSourcePallets && result.updatedSourcePallets.length > 0) {
                modalHandlers.openNetworkPrintModal({
                    type: 'finished_good_batch',
                    data: result.updatedSourcePallets,
                    onSuccess: () => {
                        if (result.newPallet) {
                            handleCompleteAndPrintFinal(result.newPallet);
                        } else {
                            showToast('Zlecenie miksowania zakończone (brak nowej palety).', 'info');
                            handleSetView(View.MIXING_WORKER);
                        }
                    }
                });
            } else if (result.newPallet) {
                handleCompleteAndPrintFinal(result.newPallet);
            }
        } else {
            setFeedback({ type: 'error', message: result.message });
        }
    };

    const handleSkipSourceAndPrintFinal = () => {
        if (!activeTask) return;
        const result = handleCompleteMixingTask(activeTask.id);
        setIsClosing(false);

        if (result.success && result.newPallet) {
            handleCompleteAndPrintFinal(result.newPallet);
        } else {
            setFeedback({ type: 'error', message: result.message || 'Wystąpił nieoczekiwany błąd.' });
        }
    };
    
    if (!activeTask) {
        return (
            <div className="p-4 md:p-6">
                <header className="flex items-center mb-6">
                    <MixerIcon className="h-8 w-8 text-primary-600 dark:text-primary-400 mr-3" />
                    <div>
                        <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300">Zlecenia Oczekujące na Realizację</h2>
                    </div>
                </header>
                {plannedTasks.length === 0 ? (
                    <div className="text-center py-10 bg-white dark:bg-secondary-800 rounded-lg shadow-md">
                        <MixerIcon className="h-16 w-16 text-gray-300 dark:text-gray-500 mx-auto mb-4"/>
                        <p className="text-gray-500 dark:text-gray-400">Brak zaplanowanych zleceń do realizacji.</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {plannedTasks.map(task => (
                            <div key={task.id} className="p-4 bg-white dark:bg-secondary-800 rounded-lg shadow-md flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                                <div>
                                    <p className="font-semibold text-primary-700 dark:text-primary-300">{task.name}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 font-mono">{task.id}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">Utworzono: {formatDate(task.createdAt, true)}</p>
                                </div>
                                <Button onClick={() => handleStartTask(task)} leftIcon={<PlayIcon className="h-5 w-5"/>} className="w-full sm:w-auto">
                                    Rozpocznij Zlecenie
                                </Button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        );
    }

    return (
        <>
            <div className="p-4 md:p-6 space-y-6">
                <header className="flex flex-col sm:flex-row justify-between sm:items-start gap-4">
                    <div>
                        <h2 className="text-2xl font-bold text-primary-700 dark:text-primary-300">{activeTask.name}</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{activeTask.id}</p>
                    </div>
                    <div className="flex gap-2">
                        <Button onClick={() => setIsCancelConfirmOpen(true)} variant="danger">
                            Anuluj Zlecenie
                        </Button>
                        <Button onClick={handleInitiateClose}>
                            Zakończ Zlecenie
                        </Button>
                    </div>
                </header>

                {feedback && <Alert type={feedback.type} message={feedback.message} />}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <section className="p-4 bg-white dark:bg-secondary-800 rounded-lg shadow-md">
                        <h3 className="text-lg font-semibold mb-3">Postęp Kompozycji</h3>
                        <div className="space-y-3">
                            {compositionStatus.map(item => (
                                <div key={item.id}>
                                    <div className="flex justify-between text-sm mb-1">
                                        <span className="font-medium text-gray-800 dark:text-gray-200">{item.productName}</span>
                                        <span>{item.consumed.toFixed(2)} / {item.quantity.toFixed(2)} kg</span>
                                    </div>
                                    <div className="w-full bg-gray-200 dark:bg-secondary-700 rounded-full h-2.5">
                                        <div className="bg-primary-600 h-2.5 rounded-full" style={{ width: `${Math.min(item.progress, 100)}%` }}></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                    
                    <section className="p-4 bg-white dark:bg-secondary-800 rounded-lg shadow-md space-y-4">
                        <div>
                            <h3 className="text-lg font-semibold mb-3">Skanuj Paletę do Zużycia</h3>
                            <form onSubmit={handleScanSubmit}>
                                <Input
                                    label="Zeskanuj kod QR palety"
                                    id="mixing-scan-input"
                                    value={scannedValue}
                                    onChange={e => setScannedValue(e.target.value)}
                                    icon={<QrCodeIcon className="h-5 w-5 text-gray-400" />}
                                    autoFocus
                                    disabled={isLoading}
                                />
                                <Button type="submit" className="w-full mt-3" disabled={isLoading || !scannedValue}>
                                    {isLoading ? 'Przetwarzanie...' : 'Zatwierdź'}
                                </Button>
                            </form>
                        </div>
                        
                        {fefoSuggestions.length > 0 && (
                            <div>
                                <h3 className="text-lg font-semibold mb-2">Sugestia FEFO</h3>
                                {fefoSuggestions.map(s => (
                                    <div key={s.itemId} className="p-3 bg-blue-50 dark:bg-blue-900/40 rounded-lg border border-blue-200 dark:border-blue-700 mb-2">
                                        <p className="text-sm font-semibold text-blue-800 dark:text-blue-200 mb-2">Pobierz dla: {s.productName}</p>
                                        <div className="space-y-2">
                                            {s.suggestions.map((pallet, index) => (
                                                <div key={pallet.id} className={`p-2 rounded-md bg-white/50 dark:bg-black/20 ${index > 0 ? 'border-t border-blue-200 dark:border-blue-600' : ''}`}>
                                                    <p className="text-md font-mono text-gray-800 dark:text-gray-200">{pallet.displayId}</p>
                                                    <p className="text-xs">Ważność: {formatDate(pallet.expiryDate)} | Waga: {pallet.quantityKg} kg</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                </div>
            </div>

            {palletToConsume &&
                (() => {
                    const neededInfo = compositionStatus.find(c => c.productName === palletToConsume.productName);
                    const remainingNeeded = neededInfo ? neededInfo.quantity - neededInfo.consumed : 0;
                    return (
                        <ConsumePartialPalletModal
                            isOpen={!!palletToConsume}
                            onClose={() => setPalletToConsume(null)}
                            pallet={palletToConsume}
                            remainingNeededWeight={remainingNeeded}
                            onConfirm={handleConfirmConsumption}
                        />
                    );
                })()
            }
            <ConfirmationModal
                isOpen={isClosing}
                onClose={() => setIsClosing(false)}
                onConfirm={handlePrintSourceAndFinal}
                onCancel={handleSkipSourceAndPrintFinal}
                title="Zakończyć Zlecenie Miksowania?"
                message="Czy chcesz wydrukować zaktualizowane etykiety dla zużytych palet źródłowych przed wydrukiem etykiety finalnej?"
                confirmButtonText="Tak, drukuj etykiety źródłowe oraz etykietę finalną"
                cancelButtonText="Pomiń i drukuj tylko finalną"
            />
             <ConfirmationModal
                isOpen={isCancelConfirmOpen}
                onClose={() => setIsCancelConfirmOpen(false)}
                onConfirm={handleConfirmCancel}
                title="Anulować Zlecenie Miksowania?"
                message={`Czy na pewno chcesz anulować to zlecenie? Wszystkie pobrane surowce zostaną zwrócone na palety źródłowe.`}
                confirmButtonText="Tak, anuluj"
            />
        </>
    );
};

// FIX: Added missing default export to support lazy loading.
export default MixingWorkerPage;
