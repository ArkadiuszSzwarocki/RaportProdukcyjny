import React from 'react';
import { WarehouseCapacityModalProps, CapacityItem, SummaryItem } from '../types';
import Button from './Button';
import XCircleIcon from './icons/XCircleIcon';
import ChartBarIcon from './icons/ChartBarIcon';

const CapacityBar: React.FC<CapacityItem> = ({ label, occupied, total, colorClass }) => {
    const percentage = total && total > 0 ? (occupied / total) * 100 : 0;

    return (
        <div>
            <div className="flex justify-between items-baseline mb-1">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
                <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                    {occupied} {total ? `/ ${total}` : ''}
                </span>
            </div>
            {total !== undefined && (
                 <div className="w-full bg-gray-200 dark:bg-secondary-600 rounded-full h-4 overflow-hidden">
                    <div 
                        className={`${colorClass} h-4 rounded-full text-center text-white text-xs font-bold transition-all duration-500 flex items-center justify-center`}
                        style={{ width: `${Math.min(percentage, 100)}%` }}
                    >
                       {percentage > 15 ? `${percentage.toFixed(0)}%` : ''}
                    </div>
                </div>
            )}
        </div>
    );
};

const StatItem: React.FC<SummaryItem> = ({ label, value, icon, onClick }) => {
    const commonClasses = "flex items-center p-3 bg-slate-100 dark:bg-secondary-700 rounded-lg";
    const interactiveClasses = "transition-colors hover:bg-slate-200 dark:hover:bg-secondary-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2";

    const content = (
        <>
            <div className="flex-shrink-0 mr-3 text-primary-600 dark:text-primary-300">{icon}</div>
            <div className="flex-grow">
                <p className="text-sm text-gray-600 dark:text-gray-400">{label}</p>
            </div>
            <p className="text-xl font-bold text-gray-800 dark:text-gray-200">{value}</p>
        </>
    );

    if (onClick) {
        return (
            <button type="button" onClick={onClick} className={`${commonClasses} ${interactiveClasses} w-full text-left`}>
                {content}
            </button>
        );
    }

    return <div className={commonClasses}>{content}</div>;
};


const WarehouseCapacityModal: React.FC<WarehouseCapacityModalProps> = ({ isOpen, onClose, capacityItems, summaryItems }) => {
    if (!isOpen) return null;

    return (
        <div 
            className="fixed inset-0 bg-gray-800 bg-opacity-75 flex items-center justify-center p-4 z-[150]"
            onClick={onClose}
        >
            <div 
                className="bg-white dark:bg-secondary-800 rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] flex flex-col"
                onClick={e => e.stopPropagation()}
            >
                <header className="flex justify-between items-center pb-3 border-b dark:border-secondary-600 mb-4">
                    <h2 className="text-xl font-semibold text-primary-700 dark:text-primary-300 flex items-center gap-2">
                        <ChartBarIcon className="h-6 w-6" />
                        Statystyki Magazynowe
                    </h2>
                    <Button onClick={onClose} variant="secondary" className="p-1.5 -mr-1.5" title="Zamknij">
                        <XCircleIcon className="h-6 w-6" />
                    </Button>
                </header>
                
                <div className="flex-grow overflow-y-auto pr-2 space-y-6">
                    <section>
                        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Zapełnienie Magazynów</h3>
                        <div className="space-y-4">
                            {(capacityItems || []).map(item => <CapacityBar key={item.label} {...item} />)}
                        </div>
                    </section>
                    <section>
                        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Podsumowanie Stanów</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {(summaryItems || []).map(item => <StatItem key={item.label} {...item} />)}
                        </div>
                    </section>
                </div>

                {/* FIX: The reported 'Cannot find name 'div'' error was likely a cascading issue from an invalid type import from 'types.ts'. Fixing the type definition should resolve the error in this file without any code changes here. */}
                <div className="pt-4 border-t dark:border-secondary-700 mt-auto flex justify-end">
                    <Button onClick={onClose} variant="primary">Zamknij</Button>
                </div>
            </div>
        </div>
    );
};

export default WarehouseCapacityModal;
