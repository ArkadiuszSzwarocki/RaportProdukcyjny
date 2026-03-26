
import React, { createContext, useContext, PropsWithChildren, useState, useCallback, useEffect } from 'react';
import { API_BASE_URL } from '../../constants';
import { ProductionRun, FinishedGoodItem, Recipe, ProductionRunTemplate, Permission, AdjustmentOrder, PsdBatch, AgroConsumedMaterial, SplitProposalDetails, ProductionEvent } from '../../types';
import { INITIAL_PRODUCTION_RUNS, INITIAL_FINISHED_GOODS } from '../../src/initialData';
import { SAMPLE_RECIPES, STATION_RAW_MATERIAL_MAPPING_DEFAULT, AGRO_LINE_PRODUCTION_RATE_KG_PER_MINUTE } from '../../constants';
import { useAuth } from './AuthContext';
import { getBlockInfo, generate18DigitId } from '../../src/utils';
import { logger } from '../../utils/logger';

const generateSplitFinishedGoodPalletId = (): string => {
    const prefix = 'WGSPL';
    const d = new Date();
    const year = d.getFullYear().toString().slice(-2);
    const month = (d.getMonth() + 1).toString().padStart(2, '0');
    const day = d.getDate().toString().padStart(2, '0');
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');
    const seconds = d.getSeconds().toString().padStart(2, '0');
    const ms = d.getMilliseconds().toString().padStart(3, '0');
    const randomDigit = Math.floor(Math.random() * 10);
    return `${prefix}${year}${month}${day}${hours}${minutes}${seconds}${ms}${randomDigit}`;
};

const generateDateId = (prefix: 'WGAGR' | 'WGPSD' | 'WGSPL'): string => {
    const d = new Date();
    d.setMilliseconds(d.getMilliseconds() - Math.floor(Math.random() * 1000000));
    const year = d.getFullYear().toString().slice(-2);
    const month = (d.getMonth() + 1).toString().padStart(2, '0');
    const day = d.getDate().toString().padStart(2, '0');
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');
    const seconds = d.getSeconds().toString().padStart(2, '0');
    const ms = d.getMilliseconds().toString().padStart(3, '0');
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    return `${prefix}${year}${month}${day}${hours}${minutes}${seconds}${ms}${random}`;
};

export interface ProductionContextValue {
    productionRunsList: ProductionRun[];
    setProductionRunsList: React.Dispatch<React.SetStateAction<ProductionRun[]>>;
    finishedGoodsList: FinishedGoodItem[];
    setFinishedGoodsList: React.Dispatch<React.SetStateAction<FinishedGoodItem[]>>;
    recipes: Recipe[];
    stationRawMaterialMapping: Record<string, string>;
    handleUpdateStationMappings: (mappings: Record<string, string>) => void;
    handleAssignPalletToProductionStation: (palletId: string, stationId: string) => { success: boolean, message: string };
    getDailyCapacity: (date: string, excludeRunId?: string) => { 
        productionMinutes: number; 
        breakMinutes: number;      
        totalUsedMinutes: number;  
        totalMinutes: number;      
        remainingMinutes: number;  
    };
    handleAddOrUpdateAgroRun: (runData: Partial<ProductionRun>) => { success: boolean; message: string; splitProposal?: SplitProposalDetails };
    handleConfirmSplitRun: (details: SplitProposalDetails) => { success: boolean, message: string };
    handleDeletePlannedProductionRun: (runId: string) => { success: boolean, message: string };
    handleStartProductionRun: (runId: string) => { success: boolean, message: string };
    handlePauseProductionRun: (runId: string, reason: string) => { success: boolean, message: string };
    handleResumeProductionRun: (runId: string) => { success: boolean, message: string };
    handleCompleteProductionRun: (runId: string, finalWeight: number) => { success: boolean, message: string };
    handleEndAgroBatch: (runId: string, batchId: string, callback: (result: { success: boolean, message: string }) => void) => void;
    handleStartNextAgroBatch: (runId: string) => { success: boolean, message: string };
    handleRegisterFgForAgro: (runId: string, weight: number) => { success: boolean, message: string, newPallet?: FinishedGoodItem };
    handleReturnRemainderToProduction: (runId: string, batchId: string, weight: number) => { success: boolean, message: string, newPallet?: FinishedGoodItem };
    handleMoveFinishedGood: (palletId: string, targetLocation: string, user: any) => { success: boolean, message: string };
    handleConfirmFinishedGoodLabeling: (itemId: string, user: any) => Promise<{ success: boolean, message: string }>;
    productionRunTemplates: ProductionRunTemplate[];
    handleDeleteTemplate: (templateId: string) => void;
    handleSplitPallet: (sourcePalletId: string, newWeights: number[]) => { 
        success: boolean; 
        message: string; 
        newPallets?: FinishedGoodItem[]; 
        updatedSourcePallet?: FinishedGoodItem; 
    };
    handleAddLabSample: (taskId: string, sampleBagNumber: string, archiveLocation?: string) => { success: boolean; message: string; newSample?: any };
    handleArchiveLabSample: (runId: string, sampleBagNumber: string, archiveLocation: string) => { success: boolean; message: string; };
    handleClearSuggestedTransfer: (runId: string) => void;
    handleUpdateBatchConfirmationStatus: (runId: string, batchId: string, step: 'nirs' | 'sampling', status: 'ok' | 'nok' | 'pending') => { success: boolean, message: string };
    handleConsumeAgroAdjustment: (runId: string, batchId: string, order: AdjustmentOrder) => { success: boolean, message: string };
    handleConsumeAdjustmentForPsd: (taskId: string, batchId: string, order: AdjustmentOrder) => { success: boolean; message: string };
    handleMarkAgroIngredientWeighingFinished: (runId: string, batchId: string, productName: string) => { success: boolean, message: string };
    handleAddRecipe: (recipe: Omit<Recipe, 'id'>) => { success: boolean, message: string };
    handleEditRecipe: (id: string, updates: Partial<Recipe>) => { success: boolean, message: string };
    handleAddProductionEvent: (runId: string, event: Omit<ProductionEvent, 'id' | 'timestamp' | 'user'>) => { success: boolean, message: string };
    handleDeleteProductionEvent: (runId: string, eventId: string) => { success: boolean, message: string };
}

export const ProductionContext = createContext<ProductionContextValue | undefined>(undefined);

export const useProductionContext = (): ProductionContextValue => {
    const context = useContext(ProductionContext);
    if (!context) throw new Error('useProductionContext must be used within a ProductionProvider');
    return context;
};

export const ProductionProvider: React.FC<PropsWithChildren> = ({ children }) => {
    const { currentUser } = useAuth();
    const [productionRunsList, setProductionRunsList] = useState<ProductionRun[]>(INITIAL_PRODUCTION_RUNS);
    const [finishedGoodsList, setFinishedGoodsList] = useState<FinishedGoodItem[]>(INITIAL_FINISHED_GOODS);
    const [recipes, setRecipes] = useState<Recipe[]>(SAMPLE_RECIPES);
    const [stationRawMaterialMapping, setStationRawMaterialMapping] = useState<Record<string, string>>(STATION_RAW_MATERIAL_MAPPING_DEFAULT);
    const [productionRunTemplates, setProductionRunTemplates] = useState<ProductionRunTemplate[]>([]);

    const fetchProductionRuns = useCallback(async () => {
        try {
            const token = localStorage.getItem('jwt_token');
            const response = await fetch(`${API_BASE_URL}/production-runs`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            if (response.ok) {
                const data = await response.json();
                setProductionRunsList(data);
                console.log('✅ Zlecenia produkcyjne załadowane:', data.length);
            }
        } catch (error) {
            console.error('❌ Błąd pobierania zleceń:', error);
        }
    }, []);

    useEffect(() => {
        fetchProductionRuns();
    }, [fetchProductionRuns]);

    const handleStartProductionRun = useCallback((runId: string) => {
        setProductionRunsList(prev => prev.map(r => {
            if (r.id === runId) {
                const now = new Date().toISOString();
                let updatedBatches = [...(r.batches || [])];
                
                if (updatedBatches.length === 0) {
                    const capacity = 2000;
                    const numBatches = Math.ceil(r.targetBatchSizeKg / capacity);
                    for (let i = 0; i < numBatches; i++) {
                        const targetWeight = (i === numBatches - 1) 
                            ? r.targetBatchSizeKg - (i * capacity) 
                            : capacity;
                        updatedBatches.push({
                            id: `${r.id}-B${i + 1}`,
                            batchNumber: i + 1,
                            targetWeight,
                            status: 'planned',
                            consumedPallets: [],
                            producedGoods: []
                        } as PsdBatch);
                    }
                }

                const firstPlannedIdx = updatedBatches.findIndex(b => b.status === 'planned');
                if (firstPlannedIdx !== -1) {
                    updatedBatches[firstPlannedIdx] = { 
                        ...updatedBatches[firstPlannedIdx], 
                        status: 'ongoing', 
                        startTime: now 
                    };
                }

                return { ...r, status: 'ongoing', startTime: now, batches: updatedBatches };
            }
            return r;
        }));
        return { success: true, message: 'Zlecenie rozpoczęte.' };
    }, [setProductionRunsList]);

    const handleStartNextAgroBatch = useCallback((runId: string) => {
        setProductionRunsList(prev =>
            prev.map(r => {
                if (r.id === runId && r.status === 'ongoing' && !r.batches.some(b => b.status === 'ongoing')) {
                    const nextBatchIndex = r.batches.findIndex(b => b.status === 'planned');
                    if (nextBatchIndex !== -1) {
                        const updatedBatches = [...r.batches];
                        updatedBatches[nextBatchIndex] = {
                            ...updatedBatches[nextBatchIndex],
                            status: 'ongoing',
                            startTime: new Date().toISOString(),
                        };
                        return { ...r, batches: updatedBatches };
                    }
                }
                return r;
            })
        );
        return { success: true, message: 'Rozpoczęto następną szarżę.' };
    }, [setProductionRunsList]);

    const handleEndAgroBatch = (runId: string, batchId: string, callback: any) => {
        setProductionRunsList(prev => {
            const runIndex = prev.findIndex(r => r.id === runId);
            if (runIndex === -1) {
                callback({ success: false, message: "Nie znaleziono zlecenia." });
                return prev;
            }
            const run = prev[runIndex];
            const batch = run.batches.find(b => b.id === batchId);
            if (!batch || batch.status !== 'ongoing') {
                callback({ success: false, message: "Brak aktywnej szarży." });
                return prev;
            }
            callback({ success: true, message: `Szarża #${batch.batchNumber} zakończona.` });
            const updatedRun = {
                ...run,
                batches: run.batches.map(b => b.id === batchId ? { ...b, status: 'completed' as const, endTime: new Date().toISOString() } : b)
            };
            const newRuns = [...prev];
            newRuns[runIndex] = updatedRun;
            return newRuns;
        });
    };

    const handleAddProductionEvent = useCallback((runId: string, eventData: Omit<ProductionEvent, 'id' | 'timestamp' | 'user'>) => {
        if (!currentUser) return { success: false, message: 'Brak aktywnej sesji użytkownika.' };
        const newEvent = { id: `evt-${Date.now()}`, timestamp: new Date().toISOString(), user: currentUser.username, ...eventData };
        setProductionRunsList(prev => prev.map(run => run.id === runId ? { ...run, events: [...(run.events || []), newEvent] } : run));
        return { success: true, message: 'Zdarzenie dodane do raportu.' };
    }, [currentUser, setProductionRunsList]);

    const handleDeleteProductionEvent = useCallback((runId: string, eventId: string) => {
        setProductionRunsList(prev => prev.map(run => {
            if (run.id === runId) {
                return {
                    ...run,
                    events: (run.events || []).filter(e => e.id !== eventId)
                };
            }
            return run;
        }));
        return { success: true, message: 'Wpis usunięty z raportu.' };
    }, [setProductionRunsList]);

    const handleUpdateBatchConfirmationStatus = (runId: string, batchId: string, step: any, status: any) => {
        setProductionRunsList(prev => prev.map(r => r.id === runId ? {
            ...r, batches: r.batches.map(b => b.id === batchId ? { ...b, confirmationStatus: { ...b.confirmationStatus, [step]: status } } : b)
        } : r));
        return { success: true, message: 'OK' };
    };

    const handleConsumeAgroAdjustment = (runId: string, batchId: string, order: AdjustmentOrder) => {
        let success = false;
        setProductionRunsList(prev => prev.map(run => {
            if (run.id === runId) {
                const newConsumedItems: AgroConsumedMaterial[] = order.materials.map(mat => ({
                    consumptionId: `cons-adj-${Date.now()}-${Math.random()}`,
                    isAnnulled: false,
                    productName: mat.productName,
                    actualConsumedQuantityKg: mat.pickedQuantityKg,
                    actualSourcePalletId: mat.sourcePalletId || `ADJ-BUCKET-${order.preparationLocation}`,
                    batchId: batchId,
                    isAdjustment: true,
                    adjustmentBucketId: order.preparationLocation
                }));

                const updatedBatches = run.batches.map(b => {
                    if (b.id === batchId) {
                        return {
                            ...b,
                            confirmationStatus: {
                                ...b.confirmationStatus,
                                nirs: 'pending' as const
                            }
                        };
                    }
                    return b;
                });

                success = true;
                return {
                    ...run,
                    batches: updatedBatches,
                    actualIngredientsUsed: [...(run.actualIngredientsUsed || []), ...newConsumedItems]
                };
            }
            return run;
        }));
        
        return { success, message: success ? 'Dosypka została odnotowana w rejestrze szarży. Wymagane ponowne badanie NIRS.' : 'Błąd zapisu.' };
    };

    const handleMarkAgroIngredientWeighingFinished = (runId: string, batchId: string, productName: string) => {
        setProductionRunsList(prev => prev.map(r => r.id === runId ? {
            ...r, batches: r.batches.map(b => b.id === batchId ? { ...b, weighingFinishedIngredients: [...(b.weighingFinishedIngredients || []), productName] } : b)
        } : r));
        return { success: true, message: 'OK' };
    };

    const handlePauseProductionRun = useCallback((runId: string, reason: string) => {
        setProductionRunsList(prev => prev.map(r => {
            if (r.id === runId && r.status === 'ongoing') {
                return {
                    ...r,
                    status: 'paused',
                    downtimes: [
                        ...(r.downtimes || []),
                        { type: 'manual_pause', startTime: new Date().toISOString(), endTime: '', durationMinutes: 0, description: reason }
                    ]
                };
            }
            return r;
        }));
        return { success: true, message: 'Produkcja wstrzymana.' };
    }, [setProductionRunsList]);

    const handleResumeProductionRun = useCallback((runId: string) => {
        setProductionRunsList(prev => prev.map(r => {
            if (r.id === runId && r.status === 'paused') {
                const downtimes = [...(r.downtimes || [])];
                const lastDowntime = downtimes[downtimes.length - 1];
                if (lastDowntime && lastDowntime.type === 'manual_pause' && !lastDowntime.endTime) {
                    lastDowntime.endTime = new Date().toISOString();
                    lastDowntime.durationMinutes = (new Date(lastDowntime.endTime).getTime() - new Date(lastDowntime.startTime).getTime()) / 60000;
                }
                return { ...r, status: 'ongoing', downtimes };
            }
            return r;
        }));
        return { success: true, message: 'Produkcja wznowiona.' };
    }, [setProductionRunsList]);

    const handleCompleteProductionRun = useCallback((runId: string, finalWeight: number) => {
        setProductionRunsList(prev => prev.map(r => {
            if (r.id === runId && (r.status === 'ongoing' || r.status === 'paused' || r.status === 'planned')) {
                const endTime = new Date().toISOString();
                return {
                    ...r,
                    status: 'completed',
                    endTime,
                    actualProducedQuantityKg: finalWeight !== undefined ? finalWeight : (r.actualProducedQuantityKg || 0)
                };
            }
            return r;
        }));
        return { success: true, message: 'Zlecenie zakończone.' };
    }, [setProductionRunsList]);

    const getDailyCapacity = (date: string) => ({ productionMinutes: 100, breakMinutes: 10, totalUsedMinutes: 110, totalMinutes: 480, remainingMinutes: 370 });

    const value: ProductionContextValue = {
        productionRunsList, setProductionRunsList,
        finishedGoodsList, setFinishedGoodsList,
        recipes, stationRawMaterialMapping, 
        handleUpdateStationMappings: (m) => setStationRawMaterialMapping(m),
        // Fixed syntax for method stubs in value object to satisfy interface.
        handleAssignPalletToProductionStation: () => ({ success: true, message: 'OK' }),
        getDailyCapacity,
        handleAddOrUpdateAgroRun: (runData: Partial<ProductionRun>) => {
            const run = {
                ...runData,
                createdBy: currentUser?.username || 'system',
                createdAt: runData.createdAt || new Date().toISOString(),
                status: runData.status || 'planned',
                batches: runData.batches || []
            };

            // Optymistyczna aktualizacja UI
            setProductionRunsList(prev => {
                const exists = prev.find(r => r.id === run.id);
                if (exists) {
                    return prev.map(r => r.id === run.id ? { ...r, ...run } as ProductionRun : r);
                }
                return [run as ProductionRun, ...prev];
            });

            // Zapis do bazy
            (async () => {
                try {
                    const token = localStorage.getItem('jwt_token');
                    const resp = await fetch(`${API_BASE_URL}/production-runs`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: JSON.stringify(run)
                    });
                    if (!resp.ok) {
                        console.error('❌ Błąd zapisu zlecenia:', await resp.text());
                        fetchProductionRuns(); // Revert on error
                    }
                } catch (err) {
                    console.error('❌ Błąd sieci przy zapisie zlecenia:', err);
                    fetchProductionRuns(); // Revert on error
                }
            })();

            return { success: true, message: 'Zlecenie zapisane.' };
        },
        handleConfirmSplitRun: () => ({ success: true, message: 'OK' }),
        handleDeletePlannedProductionRun: (runId: string) => {
            // Optymistyczna aktualizacja UI
            setProductionRunsList(prev => prev.filter(r => r.id !== runId));

            // Usuwanie z bazy
            (async () => {
                try {
                    const token = localStorage.getItem('jwt_token');
                    const resp = await fetch(`${API_BASE_URL}/production-runs/${runId}`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    if (!resp.ok) {
                        console.error('❌ Błąd usuwania zlecenia:', await resp.text());
                        fetchProductionRuns(); // Revert on error
                    }
                } catch (err) {
                    console.error('❌ Błąd sieci przy usuwaniu zlecenia:', err);
                    fetchProductionRuns(); // Revert on error
                }
            })();

            return { success: true, message: 'Zlecenie usunięte.' };
        },
        handleStartProductionRun,
        handlePauseProductionRun,
        handleResumeProductionRun,
        handleCompleteProductionRun,
        handleEndAgroBatch,
        handleStartNextAgroBatch,
        handleRegisterFgForAgro: (runId, weight) => ({ success: true, message: 'OK' }),
        handleReturnRemainderToProduction: (runId, batchId, weight) => ({ success: true, message: 'OK' }),
        handleMoveFinishedGood: (palletId, targetLocation, user) => ({ success: true, message: 'OK' }),
        handleConfirmFinishedGoodLabeling: async (itemId, user) => ({ success: true, message: 'OK' }),
        productionRunTemplates,
        handleDeleteTemplate: (id) => setProductionRunTemplates(p => p.filter(t => t.id !== id)),
        handleSplitPallet: (sourcePalletId, newWeights) => ({ success: true, message: 'OK' }),
        handleAddLabSample: (tid: any, s: any, a: any) => ({ success: true, message: 'OK', newSample: {} }),
        handleArchiveLabSample: () => ({ success: true, message: 'OK' }),
        handleClearSuggestedTransfer: (tid: any) => {},
        handleUpdateBatchConfirmationStatus,
        handleConsumeAgroAdjustment,
        handleConsumeAdjustmentForPsd: () => ({ success: true, message: 'OK' }),
        handleMarkAgroIngredientWeighingFinished,
        handleAddRecipe: () => ({ success: true, message: 'OK' }),
        handleEditRecipe: () => ({ success: true, message: 'OK' }),
        handleAddProductionEvent: (rid: any, e: any) => ({ success: true, message: 'OK' }),
        handleDeleteProductionEvent: (rid: any, eid: any) => ({ success: true, message: 'OK' })
    };

    return <ProductionContext.Provider value={value}>{children}</ProductionContext.Provider>
};
