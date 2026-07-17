import React, { useState, useEffect, useRef, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { View, WarehouseNavGroup, WarehouseInfo } from '../types';
import { WAREHOUSE_RACK_PREFIX_MAP, DEFAULT_WAREHOUSE_NAV_LAYOUT } from '../constants';
import ChevronDownIcon from './icons/ChevronDownIcon';
import { useAppContext } from './contexts/AppContext';

import AllWarehousesViewPage from './AllWarehousesViewPage';
import AllWarehousesListPage from './AllWarehousesListPage';
import { MS01SourceWarehousePage } from './MS01SourceWarehousePage';
import BufferMS01ViewPage from './BufferMS01ViewPage';
import BufferMP01ViewPage from './BufferMP01ViewPage';
import { SubWarehouseViewPage } from './SubWarehouseViewPage';
import { MDM01ViewPage } from './MDM01ViewPage';
import PsdWarehousePage from './PsdWarehousePage';
import MGW01ReceivingPage from './MGW01_ReceivingPage';
import { MGW01Page } from './MGW01Page';
import { MGW02Page } from './MGW02Page';
import { MOP01ViewPage } from './MOP01ViewPage';
import KO01ViewPage from './KO01ViewPage';
import PendingLabelsPage from './PendingLabelsPage';
import LocationDetailPage from './LocationDetailPage';
import OsipWarehousePage from './OsipWarehousePage';

const NavGroup: React.FC<{
    group: WarehouseNavGroup;
    isOpen: boolean;
    setOpenDropdown: React.Dispatch<React.SetStateAction<string | null>>;
    handleSetView: (view: View, params?: any) => void;
    activeViewForHighlight: View;
    checkPermission: (permission: any) => boolean;
    combinedInfos: WarehouseInfo[];
}> = ({ group, isOpen, setOpenDropdown, handleSetView, activeViewForHighlight, checkPermission, combinedInfos }) => {
    const buttonRef = useRef<HTMLButtonElement>(null);
    const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});

    const warehousesInGroup = useMemo(() =>
        group.warehouseIds.map(whId => combinedInfos.find(w => w.id === whId))
        .filter(Boolean)
        .filter(wh => !wh!.permission || checkPermission(wh!.permission)) as WarehouseInfo[],
    [group.warehouseIds, checkPermission, combinedInfos]);
    
    const handleToggle = () => {
        if (!isOpen && buttonRef.current) {
            const rect = buttonRef.current.getBoundingClientRect();
            setDropdownStyle({
                position: 'fixed',
                top: `${rect.bottom + 4}px`,
                left: `${rect.left}px`,
                minWidth: `${rect.width}px`,
                zIndex: 50,
            });
        }
        setOpenDropdown(isOpen ? null : group.id);
    };

    if (warehousesInGroup.length === 0) return null;

    return (
        <div>
            <button ref={buttonRef} onClick={handleToggle} className={`px-4 py-2 text-sm font-medium rounded-md transition-colors flex items-center gap-1 whitespace-nowrap ${group.warehouseIds.some(id => combinedInfos.find(w => w.id === id)?.view === activeViewForHighlight) ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-secondary-700'}`}>
                {group.label} <ChevronDownIcon className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && ReactDOM.createPortal(
                <div style={dropdownStyle} className="w-auto bg-white dark:bg-secondary-800 rounded-md shadow-lg border dark:border-secondary-600 py-1 z-50">
                    <ul>
                        {warehousesInGroup.map(wh => (
                            <li key={wh.id}>
                                <button onClick={() => { setOpenDropdown(null); if(wh.isLocationDetailLink) handleSetView(View.LocationDetail, { locationId: wh.id, locationName: wh.label, returnView: View.WarehouseDashboard }); else handleSetView(wh.view); }} className={`w-full text-left px-4 py-2 text-sm ${activeViewForHighlight === wh.view ? 'bg-primary-500 text-white' : 'hover:bg-gray-100 dark:hover:bg-secondary-700 text-gray-800 dark:text-gray-200'}`}>
                                    {wh.label}
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>, document.body
            )}
        </div>
    );
};

const WarehouseDashboardPage: React.FC = () => {
    const { currentView, handleSetView, viewParams, warehouseNavLayout, checkPermission, currentUser, combinedWarehouseInfos } = useAppContext();
    const [openDropdown, setOpenDropdown] = useState<string | null>(null);

    useEffect(() => {
        if (currentView === View.WarehouseDashboard && currentUser?.subRole === 'OSIP') {
            handleSetView(View.OsipWarehouse);
        }
    }, [currentView, currentUser, handleSetView]);

    const renderView = () => {
        switch (currentView) {
            case View.LocationDetail: return <LocationDetailPage />;
            case View.SourceWarehouseMS01: return <MS01SourceWarehousePage />;
            case View.BufferMS01View: return <BufferMS01ViewPage />;
            case View.BufferMP01View: return <BufferMP01ViewPage />;
            case View.SubWarehouseMP01: return <SubWarehouseViewPage />;
            case View.MDM01View: return <MDM01ViewPage />;
            case View.PSD_WAREHOUSE: return <PsdWarehousePage />;
            case View.MGW01_Receiving: return <MGW01ReceivingPage />;
            case View.MGW01: return <MGW01Page />;
            case View.MGW02: return <MGW02Page />;
            case View.MOP01View: return <MOP01ViewPage />;
            case View.KO01View: return <KO01ViewPage />;
            case View.PendingLabels: return <PendingLabelsPage />;
            case View.OsipWarehouse: return <OsipWarehousePage />;
            case View.AllWarehousesView: return <AllWarehousesListPage onNavigate={handleSetView} />;
            default: return <AllWarehousesViewPage onNavigate={handleSetView} />;
        }
    };

    const activeViewForHighlight = useMemo(() => {
        if (currentView === View.LocationDetail && viewParams?.returnView) return viewParams.returnView;
        if (combinedWarehouseInfos.some((w: any) => w.view === currentView)) return currentView;
        return View.AllWarehousesView;
    }, [currentView, viewParams, combinedWarehouseInfos]);

    return (
        <div className="h-full flex flex-col bg-slate-100 dark:bg-secondary-900">
            <nav className="relative z-10 flex-shrink-0 bg-white dark:bg-secondary-800 shadow-md border-b dark:border-secondary-700 flex items-center gap-2 p-2 overflow-x-auto scrollbar-hide">
                {(warehouseNavLayout || DEFAULT_WAREHOUSE_NAV_LAYOUT).map((item: any) => (
                    item.isGroup 
                        ? <NavGroup key={item.id} group={item} isOpen={openDropdown === item.id} setOpenDropdown={setOpenDropdown} handleSetView={handleSetView} activeViewForHighlight={activeViewForHighlight} checkPermission={checkPermission} combinedInfos={combinedWarehouseInfos} />
                        : (() => {
                            const whInfo = combinedWarehouseInfos.find((w: any) => w.id === item.id);
                            if (!whInfo || (whInfo.permission && !checkPermission(whInfo.permission))) return null;
                            return (
                                <button key={item.id} onClick={() => handleSetView(whInfo.view)} className={`px-4 py-2 text-sm font-medium rounded-md transition-colors whitespace-nowrap ${activeViewForHighlight === whInfo.view ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-secondary-700'}`}>
                                    {whInfo.label}
                                </button>
                            );
                        })()
                ))}
            </nav>
            <main className="flex-grow overflow-auto p-4 md:p-6 scrollbar-hide">{renderView()}</main>
        </div>
    );
};

export default WarehouseDashboardPage;