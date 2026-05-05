
import React, { useState, useMemo } from 'react';
import { useWarehouseContext } from './contexts/WarehouseContext';
import { LocationDefinition } from '../types';
import { useSortableData } from '../src/useSortableData';
import SortableHeader from './SortableHeader';
import Button from './Button';
import Input from './Input';
import Select from './Select';
import Alert from './Alert';
import MapIcon from './icons/MapIcon';
import SearchIcon from './icons/SearchIcon';
import PlusIcon from './icons/PlusIcon';
import EditIcon from './icons/EditIcon';
import TrashIcon from './icons/TrashIcon';
import ConfirmationModal from './ConfirmationModal';
import AddEditLocationModal from './AddEditLocationModal';
import LockClosedIcon from './icons/LockClosedIcon';
import CheckCircleIcon from './icons/CheckCircleIcon';

const getTypeBadge = (type: string) => {
    switch (type) {
        case 'warehouse': return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200 border border-blue-200 dark:border-blue-800">Magazyn</span>;
        case 'zone': return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200 border border-indigo-200 dark:border-indigo-800">Strefa</span>;
        case 'rack': return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200 border border-purple-200 dark:border-purple-800">Regał</span>;
        case 'shelf': return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200 border border-orange-200 dark:border-orange-800">Półka</span>;
        case 'bin': return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200 border border-green-200 dark:border-green-800">Gniazdo</span>;
        default: return <span className="px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">{type}</span>;
    }
};

const WarehouseLayoutInfoPage: React.FC = () => {
    const { allManageableLocations, handleAddLocation, handleUpdateLocation, handleDeleteLocation } = useWarehouseContext();
    
    const [searchTerm, setSearchTerm] = useState('');
    const [typeFilter, setTypeFilter] = useState('all');
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [editingLocation, setEditingLocation] = useState<LocationDefinition | null>(null);
    const [locationToDelete, setLocationToDelete] = useState<LocationDefinition | null>(null);
    const [feedback, setFeedback] = useState<{ type: 'success' | 'error', message: string } | null>(null);

    const filteredLocations = useMemo(() => {
        return (allManageableLocations || []).filter(loc => {
            const matchesSearch = 
                loc.id.toLowerCase().includes(searchTerm.toLowerCase()) || 
                loc.name.toLowerCase().includes(searchTerm.toLowerCase());
            const matchesType = typeFilter === 'all' || loc.type === typeFilter;
            return matchesSearch && matchesType;
        });
    }, [allManageableLocations, searchTerm, typeFilter]);

    const { items: sortedLocations, requestSort, sortConfig } = useSortableData(filteredLocations, { key: 'id', direction: 'ascending' });

    const handleSave = (location: LocationDefinition): { success: boolean; message: string } => {
        let result;
        if (editingLocation) {
            result = handleUpdateLocation(editingLocation.id, location);
        } else {
            result = handleAddLocation(location);
        }
        setFeedback({ type: result.success ? 'success' : 'error', message: result.message });
        if (result.success) {
            setEditingLocation(null);
            setIsAddModalOpen(false);
        }
        return result;
    };

    const handleEdit = (loc: LocationDefinition) => {
        setEditingLocation(loc);
        setIsAddModalOpen(true);
    };

    const confirmDelete = () => {
        if (locationToDelete) {
            const result = handleDeleteLocation(locationToDelete.id);
            setFeedback({ type: result.success ? 'success' : 'error', message: result.message });
            setLocationToDelete(null);
        }
    };

    return (
        <div className="p-4 md:p-6 bg-white dark:bg-secondary-800 shadow-xl rounded-lg h-full flex flex-col">
            <header className="flex-shrink-0 flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 border-b dark:border-secondary-600 pb-3 gap-3">
                <div className="flex items-center">
                    <MapIcon className="h-8 w-8 text-primary-600 dark:text-primary-400 mr-3" />
                    <h2 className="text-2xl font-semibold text-primary-700 dark:text-primary-300">Zarządzanie Lokalizacjami</h2>
                </div>
                <div className="flex gap-2">
                    <Input 
                        label="" 
                        placeholder="Szukaj lokalizacji..." 
                        value={searchTerm} 
                        onChange={e => setSearchTerm(e.target.value)}
                        icon={<SearchIcon className="h-4 w-4" />}
                        className="text-sm"
                    />
                    <Button onClick={() => { setEditingLocation(null); setIsAddModalOpen(true); }} leftIcon={<PlusIcon className="h-5 w-5"/>}>Dodaj</Button>
                </div>
            </header>

            {feedback && <div className="mb-4"><Alert type={feedback.type} message={feedback.message} /></div>}

            <div className="flex-grow overflow-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-secondary-700 text-sm">
                    <thead className="bg-gray-100 dark:bg-secondary-700 sticky top-0 z-10">
                        <tr>
                            <SortableHeader columnKey="id" sortConfig={sortConfig} requestSort={requestSort}>ID Lokalizacji</SortableHeader>
                            <SortableHeader columnKey="name" sortConfig={sortConfig} requestSort={requestSort}>Nazwa Wyświetlana</SortableHeader>
                            <SortableHeader columnKey="type" sortConfig={sortConfig} requestSort={requestSort}>Typ</SortableHeader>
                            <SortableHeader columnKey="capacity" sortConfig={sortConfig} requestSort={requestSort} className="justify-end">Pojemność</SortableHeader>
                            <th className="px-4 py-3 text-right font-medium text-gray-500 dark:text-gray-300">Akcje</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-secondary-700 bg-white dark:bg-secondary-800">
                        {sortedLocations.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-10 text-center text-gray-500 italic">Brak zdefiniowanych lokalizacji.</td>
                            </tr>
                        ) : (
                            sortedLocations.map(loc => (
                                <tr key={loc.id} className="hover:bg-gray-50 dark:hover:bg-secondary-700/50 transition-colors">
                                    <td className="px-4 py-3 font-mono font-bold text-primary-600 dark:text-primary-400">{loc.id}</td>
                                    <td className="px-4 py-3 font-medium text-gray-800 dark:text-gray-200">{loc.name}</td>
                                    <td className="px-4 py-3">{getTypeBadge(loc.type)}</td>
                                    <td className="px-4 py-3 text-right font-mono">{loc.capacity} palet</td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex justify-end gap-2">
                                            <Button onClick={() => handleEdit(loc)} variant="secondary" className="p-1.5"><EditIcon className="h-4 w-4"/></Button>
                                            <Button onClick={() => setLocationToDelete(loc)} variant="danger" className="p-1.5"><TrashIcon className="h-4 w-4"/></Button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {isAddModalOpen && (
                <AddEditLocationModal 
                    isOpen={isAddModalOpen} 
                    onClose={() => setIsAddModalOpen(false)} 
                    onSave={handleSave} 
                    locationToEdit={editingLocation} 
                />
            )}

            {locationToDelete && (
                <ConfirmationModal 
                    isOpen={!!locationToDelete} 
                    onClose={() => setLocationToDelete(null)} 
                    onConfirm={confirmDelete} 
                    title="Usuń lokalizację" 
                    message={<span>Czy na pewno chcesz usunąć lokalizację <strong>{locationToDelete.id}</strong>? Tej operacji nie można cofnąć.</span>} 
                    confirmButtonText="Tak, usuń" 
                />
            )}
        </div>
    );
};

export default WarehouseLayoutInfoPage;
