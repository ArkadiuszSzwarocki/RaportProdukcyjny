
import React, { useState, useMemo, useEffect } from 'react';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { WarehouseNavLayoutItem, WarehouseNavGroup, WarehouseNavItem, WarehouseInfo } from '../types';
import Button from './Button';
import Input from './Input';
import Select from './Select';
import Alert from './Alert';
import ViewColumnsIcon from './icons/ViewColumnsIcon';
import PlusIcon from './icons/PlusIcon';
import TrashIcon from './icons/TrashIcon';
import EditIcon from './icons/EditIcon';
import CheckCircleIcon from './icons/CheckCircleIcon';

const WarehouseCard: React.FC<{
    warehouse: any;
    currentGroupId: string;
    groupOptions: { value: string; label: string }[];
    onMove: (warehouseId: string, newGroupId: string) => void;
}> = ({ warehouse, currentGroupId, groupOptions, onMove }) => {
    return (
        <div className="flex items-center justify-between p-2 bg-white dark:bg-secondary-700 rounded border border-slate-200 dark:border-secondary-600">
            <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{warehouse.label}</span>
            <div className="w-48">
                <Select
                    label=""
                    id={`select-${warehouse.id}`}
                    options={groupOptions}
                    value={currentGroupId}
                    onChange={(e) => onMove(warehouse.id, e.target.value)}
                    className="text-xs py-1"
                    error={undefined}
                />
            </div>
        </div>
    );
};

const WarehouseGroupSettingsPage: React.FC = () => {
    const { warehouseNavLayout, setWarehouseNavLayout, combinedWarehouseInfos } = useWarehouseContext();
    const [draftLayout, setDraftLayout] = useState<any[]>(() => JSON.parse(JSON.stringify(warehouseNavLayout)));
    const [feedback, setFeedback] = useState<{ type: 'success' | 'error', message: string } | null>(null);
    const [editingGroup, setEditingGroup] = useState<{ id: string; name: string } | null>(null);
    const [newGroupName, setNewGroupName] = useState('');

    useEffect(() => {
        if (feedback) {
            const timer = setTimeout(() => setFeedback(null), 4000);
            return () => clearTimeout(timer);
        }
    }, [feedback]);

    const handleMoveWarehouse = (warehouseId: string, newGroupId: string) => {
        setDraftLayout(prevLayout => {
            const warehouseInfo = combinedWarehouseInfos.find(wh => wh.id === warehouseId);
            if (!warehouseInfo) return prevLayout;

            const layoutWithoutMovedItem = prevLayout
                .map(item => {
                    if (item.isGroup) {
                        return { ...item, warehouseIds: item.warehouseIds.filter((id: string) => id !== warehouseId) };
                    }
                    if (!item.isGroup && item.id === warehouseId) {
                        return null;
                    }
                    return item;
                })
                .filter((item): item is any => item !== null);
            
            if (newGroupId === '__STANDALONE__') {
                return [...layoutWithoutMovedItem, { ...warehouseInfo, isGroup: false }];
            } else {
                return layoutWithoutMovedItem.map(item => {
                    if (item.isGroup && item.id === newGroupId) {
                        const newIds = new Set([...item.warehouseIds, warehouseId]);
                        return { ...item, warehouseIds: Array.from(newIds) };
                    }
                    return item;
                });
            }
        });
    };
    
    const handleAddGroup = () => {
        if (!newGroupName.trim()) {
            setFeedback({ type: 'error', message: 'Nazwa grupy nie może być pusta.' });
            return;
        }
        setDraftLayout(prev => [
            ...prev,
            { id: `group-${Date.now()}`, label: newGroupName.trim(), isGroup: true, warehouseIds: [] }
        ]);
        setNewGroupName('');
    };

    const handleUpdateGroupName = () => {
        if (!editingGroup || !editingGroup.name.trim()) return;
        setDraftLayout(prev => prev.map(item => 
            item.id === editingGroup.id ? { ...item, label: editingGroup.name.trim() } : item
        ));
        setEditingGroup(null);
    };
    
    const handleDeleteGroup = (groupId: string) => {
        setDraftLayout(prev => prev.filter(item => item.id !== groupId));
    };

    const handleSaveChanges = () => {
        const finalLayout = draftLayout.filter(item => !item.isGroup || item.warehouseIds.length > 0);
        setWarehouseNavLayout(finalLayout);
        setFeedback({ type: 'success', message: 'Układ nawigacji został pomyślnie zaktualizowany.' });
    };

    const groups = draftLayout.filter(item => item.isGroup) as any[];
    
    const allAssignedWarehouseIds = useMemo(() => {
        const ids = new Set<string>();
        draftLayout.forEach(item => {
            if (item.isGroup) {
                item.warehouseIds.forEach((id: string) => ids.add(id));
            } else {
                ids.add(item.id);
            }
        });
        return ids;
    }, [draftLayout]);
    
    const unassignedWarehouses = useMemo(() => combinedWarehouseInfos.filter(
        wh => !allAssignedWarehouseIds.has(wh.id) && wh.id !== 'all'
    ), [allAssignedWarehouseIds, combinedWarehouseInfos]);

    const groupOptions = useMemo(() => [
        { value: '__STANDALONE__', label: 'Poza Grupą' },
        ...groups.map(g => ({ value: g.id, label: g.label }))
    ], [groups]);

    return (
        <div className="p-4 md:p-6 bg-white dark:bg-secondary-800 shadow-xl rounded-lg">
            <header className="flex items-center mb-6 border-b dark:border-secondary-600 pb-4">
                <ViewColumnsIcon className="h-8 w-8 text-primary-600 dark:text-primary-400 mr-3" />
                <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300">Grupowanie Magazynów w Menu</h2>
            </header>

            {feedback && <div className="mb-4"><Alert type={feedback.type} message={feedback.message} /></div>}

            <div className="p-4 border dark:border-secondary-700 rounded-lg bg-slate-50 dark:bg-secondary-900 mb-6">
                <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2">Utwórz Nową Grupę Menu</h3>
                <div className="flex flex-col sm:flex-row items-end gap-2">
                    <Input label="Nazwa nowej grupy" id="new-group-name" value={newGroupName} onChange={e => setNewGroupName(e.target.value)} />
                    <Button onClick={handleAddGroup} leftIcon={<PlusIcon className="h-5 w-5"/>}>Dodaj</Button>
                </div>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {groups.map(group => (
                    <div key={group.id} className="p-4 border dark:border-secondary-700 rounded-lg bg-white dark:bg-secondary-800 shadow-md flex flex-col">
                        <div className="flex justify-between items-center mb-3 border-b dark:border-secondary-600 pb-2">
                            {editingGroup?.id === group.id ? (
                                <div className="flex items-center gap-2 flex-grow">
                                    <Input label="" id={`edit-group-${group.id}`} value={editingGroup.name} onChange={e => setEditingGroup({ ...editingGroup, name: e.target.value })} />
                                    <Button onClick={handleUpdateGroupName} className="p-1.5"><CheckCircleIcon className="h-5 w-5"/></Button>
                                </div>
                            ) : (
                                <h3 className="text-lg font-semibold text-primary-700 dark:text-primary-300">{group.label}</h3>
                            )}
                            <div className="flex items-center gap-1">
                                <Button onClick={() => setEditingGroup({ id: group.id, name: group.label })} variant="secondary" className="p-1.5"><EditIcon className="h-4 w-4"/></Button>
                                <Button onClick={() => handleDeleteGroup(group.id)} variant="secondary" className="p-1.5 bg-red-100 dark:bg-red-900/40 text-red-600 hover:bg-red-200"><TrashIcon className="h-4 w-4"/></Button>
                            </div>
                        </div>
                        <div className="space-y-2 flex-grow">
                            {group.warehouseIds.length > 0 ? group.warehouseIds.map((whId: string) => {
                                const warehouse = combinedWarehouseInfos.find(w => w.id === whId);
                                return warehouse ? <WarehouseCard key={whId} warehouse={warehouse} currentGroupId={group.id} groupOptions={groupOptions} onMove={handleMoveWarehouse} /> : null;
                            }) : <p className="text-sm text-gray-500 dark:text-gray-400 italic text-center py-4">Ta grupa jest pusta.</p>}
                        </div>
                    </div>
                ))}

                <div className="p-4 border dark:border-secondary-700 rounded-lg bg-white dark:bg-secondary-800 shadow-md">
                    <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-3 border-b dark:border-secondary-600 pb-2">Magazyny Poza Grupą (Oczekujące)</h3>
                    <div className="space-y-2">
                        {draftLayout.filter(item => !item.isGroup).map(item => {
                             const warehouse = combinedWarehouseInfos.find(w => w.id === item.id);
                             return warehouse ? <WarehouseCard key={item.id} warehouse={warehouse} currentGroupId="__STANDALONE__" groupOptions={groupOptions} onMove={handleMoveWarehouse} /> : null;
                        })}
                         {unassignedWarehouses.map(wh => (
                            <WarehouseCard key={wh.id} warehouse={wh} currentGroupId="__STANDALONE__" groupOptions={groupOptions} onMove={handleMoveWarehouse} />
                        ))}
                        {draftLayout.filter(item => !item.isGroup).length === 0 && unassignedWarehouses.length === 0 && (
                             <p className="text-sm text-gray-500 dark:text-gray-400 italic text-center py-4">Wszystkie lokalizacje są przypisane.</p>
                        )}
                    </div>
                </div>
            </div>

            <div className="mt-8 pt-4 border-t dark:border-secondary-600 flex justify-end">
                <Button onClick={handleSaveChanges} variant="primary" className="text-lg px-6 py-2">Zatwierdź Układ Menu</Button>
            </div>
        </div>
    );
};

export default WarehouseGroupSettingsPage;
