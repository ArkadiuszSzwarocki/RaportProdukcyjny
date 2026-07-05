// utils.js


function generateWZ() {
        const now = new Date();
        const dd = String(now.getDate()).padStart(2, '0');
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const rrrr = now.getFullYear();
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        return `${dd}${mm}${rrrr}${hh}${min}${ss}`;
    }



function getItemUnit(item) {
        if (!item || !item.packageForm) {
            return '';
        }
        return item.packageForm === 'packaging' ? 'szt' : 'kg';
    }

function getItemQuantity(item) {
        if (!item) {
            return '';
        }
        const unit = getItemUnit(item);
        let raw = '';
        if (unit === 'szt') {
            raw = item.unitsPerPallet;
        } else if (unit === 'kg') {
            raw = item.netWeight;
        } else {
            raw = item.netWeight || item.unitsPerPallet;
        }
        return (raw === null || raw === undefined || raw === '') ? '' : raw;
    }

function setItemQuantity(index, value) {
        const normalized = String(value ?? '').trim().replace(',', '.');
        if (normalized === '') {
            items[index].netWeight = '';
            items[index].unitsPerPallet = '';
            return;
        }

        const parsed = parseFloat(normalized);
        if (Number.isNaN(parsed)) {
            return;
        }

        if (getItemUnit(items[index]) === 'szt') {
            items[index].unitsPerPallet = parsed;
            items[index].netWeight = '';
        } else {
            items[index].netWeight = parsed;
            items[index].unitsPerPallet = '';
        }
    }

function getDefaultSourceSpot() {
        return '';
    }

function buildEmptyItem(suffix = '') {
        return {
            id: 'MANUAL_' + Date.now() + (suffix ? '_' + suffix : ''),
            productName: '',
            netWeight: '',
            unitsPerPallet: '',
            packageForm: '',
            sourceSpot: getDefaultSourceSpot(),
            nr_palety: '',
            nr_partii: '',
            data_produkcji: '',
            data_przydatnosci: '',
            accepted: false,
            is_manual: true
        };
    }

function isFilled(value) {
        return String(value ?? '').trim() !== '';
    }

function isPositiveNumber(value) {
        const parsed = parseFloat(String(value ?? '').replace(',', '.'));
        return !Number.isNaN(parsed) && parsed > 0;
    }

function isItemComplete(item) {
        const bypassLookup = isWarehouseLookupBypassed();
        return (
            isFilled(item && item.productName)
            && (bypassLookup || isFilled(item && item.sourceSpot))
            && isFilled(getItemUnit(item))
            && isPositiveNumber(getItemQuantity(item))
        );
    }

function normalizeLocation(value) {
        return String(value || '').trim().toUpperCase().replace(/[\s\-_]/g, '');
    }

function isSameLocation(left, right) {
        const l = normalizeLocation(left);
        const r = normalizeLocation(right);
        return l !== '' && r !== '' && l === r;
    }

function isRouteConflictLocation(sourceLoc, targetLoc) {
        const source = normalizeLocation(sourceLoc);
        const target = normalizeLocation(targetLoc);
        if (source === '' || target === '') {
            return false;
        }

        if (source === target) {
            return true;
        }

        // Treat prefix variants as the same route family, e.g. BF_MS01 / BF_MS01_x.
        return source.startsWith(target) || target.startsWith(source);
    }

function isKnownSourceLocation(value) {
        const loc = normalizeLocation(value);
        if (!loc) {
            return false;
        }

        if (KNOWN_SOURCE_LOCATIONS_SET.has(loc)) {
            return true;
        }

        const rackMatch = loc.match(/^R0([1-7])(\d{2})(\d{2})$/);
        if (rackMatch) {
            return true;
        }

        const osipMatch = loc.match(/^OS(\d{2})$/);
        if (osipMatch) {
            const nr = parseInt(osipMatch[1], 10);
            return nr >= 1 && nr <= 77;
        }

        const bbMatch = loc.match(/^BB(\d{2})$/);
        if (bbMatch) {
            const nr = parseInt(bbMatch[1], 10);
            return nr >= 1 && nr <= 24;
        }

        const mzSimple = loc.match(/^MZ(\d{2})$/);
        if (mzSimple) {
            const nr = parseInt(mzSimple[1], 10);
            return nr >= 1 && nr <= 6;
        }

        // Magazyn Dodatków (MD / MDO)
        if (loc.startsWith('MD') || loc.startsWith('MDO')) {
            return true;
        }

        return loc === 'MZ05-01' || loc === 'MZ06-01';
    }

function getUnknownSourceLocations() {
        if (isWarehouseLookupBypassed()) return [];
        const unique = new Set();
        items.forEach(item => {
            const source = normalizeLocation(item && item.sourceSpot);
            if (source && !isKnownSourceLocation(source)) {
                unique.add(source);
            }
        });
        return Array.from(unique);
    }

function getValidationBorderStyle(hasError) {
        if (hasError && formSubmitAttempted) {
            return 'border: 2px solid #dc2626; box-shadow: inset 0 0 0 1px rgba(220,38,38,0.08); background-color: #fff1f2;';
        }
        return 'border: 1px solid #e2e8f0;';
    }

function getItemValidationMap(item, targetLoc) {
        const sourceLoc = normalizeLocation(item && item.sourceSpot);
        const unit = getItemUnit(item);
        const quantity = getItemQuantity(item);

        const bypassLookup = isWarehouseLookupBypassed();

        const sourceInvalid =
            (!bypassLookup && !isFilled(sourceLoc))
            || (!bypassLookup && isFilled(sourceLoc) && !isKnownSourceLocation(sourceLoc))
            || isRouteConflictLocation(sourceLoc, targetLoc);

        return {
            productName: !isFilled(item && item.productName),
            sourceSpot: sourceInvalid,
            quantity: !isPositiveNumber(quantity),
            unit: !isFilled(unit),
            nr_partii: false,
            data_produkcji: false,
            data_przydatnosci: false,
        };
    }

function getCurrentTargetLocation() {
        const targetInput = document.getElementById('lokalizacja_do');
        return normalizeLocation(targetInput ? targetInput.value : '');
    }

function isWarehouseLookupBypassed() {
        const bypassInput = document.getElementById('skip_warehouse_lookup');
        return !!(bypassInput && bypassInput.checked);
    }

function getItemCopyMarkerKey(item, index) {
        const rawId = item && item.id;
        if (rawId !== undefined && rawId !== null && String(rawId).trim() !== '') {
            return String(rawId);
        }
        return `idx_${index}`;
    }

function getCopiedFromNumber(item, index) {
        const key = getItemCopyMarkerKey(item, index);
        const raw = copiedRowsInfoByItem[key];
        const parsed = parseInt(raw, 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

function setCopiedFromNumber(item, index, fromRowNumber) {
        const key = getItemCopyMarkerKey(item, index);
        copiedRowsInfoByItem[key] = parseInt(fromRowNumber, 10);
    }

function clearCopiedMarker(item, index) {
        const key = getItemCopyMarkerKey(item, index);
        if (Object.prototype.hasOwnProperty.call(copiedRowsInfoByItem, key)) {
            delete copiedRowsInfoByItem[key];
        }
    }

function isItemPalletSlotEmpty(item) {
        if (!item) {
            return false;
        }

        const hasBoundPallet = isFilled(item.sourcePalletId) || isFilled(item.sourcePalletNo);
        if (hasBoundPallet) {
            return false;
        }

        return !isFilled(item.productName)
            && !isFilled(getItemQuantity(item))
            && !isFilled(getItemUnit(item))
            && !isFilled(item.nr_partii)
            && !isFilled(item.data_produkcji)
            && !isFilled(item.data_przydatnosci);
    }

function canSaveTransfer() {
        if (READ_ONLY_MODE) {
            return false;
        }

        const targetInput = document.getElementById('lokalizacja_do');
        const targetLoc = targetInput ? targetInput.value : '';

        if (!isFilled(targetLoc)) {
            return false;
        }

        if (!Array.isArray(items) || items.length === 0) {
            return false;
        }

        const hasSourceTargetConflict = items.some(item => isRouteConflictLocation(item && item.sourceSpot, targetLoc));
        if (hasSourceTargetConflict) {
            return false;
        }

        if (getUnknownSourceLocations().length > 0) {
            return false;
        }

        return items.every(isItemComplete);
    }

function getSaveBlockers() {
        if (READ_ONLY_MODE) {
            return ['Status OCZEKUJE: formularz wydania jest tylko do podglądu.'];
        }

        const blockers = [];
        
        if (!Array.isArray(items) || items.length === 0) {
            blockers.push('Dodaj przynajmniej jedną paletę.');
            return blockers;
        }

        const targetInput = document.getElementById('lokalizacja_do');
        const targetLoc = targetInput ? targetInput.value : '';

        const conflictingItems = items.filter(item => isRouteConflictLocation(item && item.sourceSpot, targetLoc));
        if (conflictingItems.length > 0) {
            blockers.push(`Operacja niemożliwa: ${conflictingItems.length} palet ma lokalizację źródłową kolidującą z Dokąd (${normalizeLocation(targetLoc)}).`);
        }

        const unknownSourceLocations = getUnknownSourceLocations();
        if (unknownSourceLocations.length > 0) {
            const preview = unknownSourceLocations.slice(0, 3).join(', ');
            const suffix = unknownSourceLocations.length > 3 ? ', ...' : '';
            blockers.push(`Nieznane lokalizacje źródłowe: ${preview}${suffix}. Popraw lokalizacje przed zapisem.`);
        }

        const incompleteCount = items.filter(item => !isItemComplete(item)).length;
        if (incompleteCount > 0) {
            blockers.push(`Uzupełnij wszystkie pola w każdej palecie. Niekompletne: ${incompleteCount}.`);
        }

        return blockers;
    }

function normalizePalletKey(value) {
        return String(value || '').trim().toUpperCase();
    }

function getPalletReservationKeyFromItem(item) {
        if (!item) {
            return '';
        }

        const palletNo = normalizePalletKey(item.sourcePalletNo || item.nr_palety);
        if (palletNo) {
            return `NR:${palletNo}`;
        }

        const palletId = item.sourcePalletId;
        const scannedType = normalizePalletKey(item.scannedType || item.type);
        if (palletId !== undefined && palletId !== null && String(palletId).trim() !== '' && scannedType) {
            return `ID:${scannedType}:${String(palletId).trim()}`;
        }

        return '';
    }

function getPalletReservationKeyFromPallet(pal) {
        if (!pal) {
            return '';
        }

        const palletNo = normalizePalletKey(pal.nr_palety);
        if (palletNo) {
            return `NR:${palletNo}`;
        }

        const palletId = pal.id;
        const scannedType = normalizePalletKey(pal.type);
        if (palletId !== undefined && palletId !== null && String(palletId).trim() !== '' && scannedType) {
            return `ID:${scannedType}:${String(palletId).trim()}`;
        }

        return '';
    }

function createItemFromPallet(pal, idx = 0) {
        const scannedType = String(pal.type || '').toLowerCase();
        const rawQty = pal.stan_magazynowy;
        const parsedQty = parseFloat(String(rawQty ?? '').replace(',', '.'));
        const qty = Number.isNaN(parsedQty) ? '' : parsedQty;
        const isPackaging = scannedType === 'opakowanie';

        return {
            id: String(pal.id) + '_' + Date.now() + '_' + idx,
            sourcePalletId: pal.id,
            sourcePalletNo: pal.nr_palety || '',
            nr_palety: pal.nr_palety || '',
            productName: pal.nazwa || '',
            netWeight: isPackaging ? '' : qty,
            unitsPerPallet: isPackaging ? qty : '',
            packageForm: isPackaging ? 'packaging' : 'bags',
            sourceSpot: pal.lokalizacja || getDefaultSourceSpot(),
            nr_partii: pal.nr_partii || '',
            data_produkcji: pal.data_produkcji || '',
            data_przydatnosci: pal.data_przydatnosci || '',
            accepted: false,
            scannedType: pal.type || ''
        };
    }

function escapeAttr(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
