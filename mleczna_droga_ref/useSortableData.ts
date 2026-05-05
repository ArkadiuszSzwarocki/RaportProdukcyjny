import { useState, useMemo } from 'react';
import { SortConfig } from '../types';

type Direction = 'ascending' | 'descending';

const getNestedValue = <T extends object>(obj: T, path: string): any => {
    return path.split('.').reduce((o: any, k: string) => (o ? o[k] : null), obj);
};

export const useSortableData = <T extends object>(items: T[], config: SortConfig<T> | null = null) => {
    const [sortConfig, setSortConfig] = useState(config);

    const sortedItems = useMemo(() => {
        if (!items) return [];
        let sortableItems = [...items];
        if (sortConfig !== null) {
            sortableItems.sort((a, b) => {
                const key = sortConfig.key as string;
                let valA = getNestedValue(a, key);
                let valB = getNestedValue(b, key);
                
                if (Array.isArray(valA) && Array.isArray(valB)) {
                    valA = valA.length;
                    valB = valB.length;
                }

                if (valA === null || valA === undefined) return 1;
                if (valB === null || valB === undefined) return -1;

                if (typeof valA === 'number' && typeof valB === 'number') {
                    if (valA < valB) return sortConfig.direction === 'ascending' ? -1 : 1;
                    if (valA > valB) return sortConfig.direction === 'ascending' ? 1 : -1;
                    return 0;
                }
                
                // Check if values are date-like strings
                const dateA = new Date(valA);
                const dateB = new Date(valB);
                if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) {
                    if (dateA.getTime() < dateB.getTime()) return sortConfig.direction === 'ascending' ? -1 : 1;
                    if (dateA.getTime() > dateB.getTime()) return sortConfig.direction === 'ascending' ? 1 : -1;
                    return 0;
                }

                // Fallback to string comparison
                return String(valA).localeCompare(String(valB), 'pl', { sensitivity: 'base' }) * (sortConfig.direction === 'ascending' ? 1 : -1);
            });
        }
        return sortableItems;
    }, [items, sortConfig]);

    const requestSort = (key: keyof T | string) => {
        let direction: Direction = 'ascending';
        if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    return { items: sortedItems, requestSort, sortConfig };
};