// ---- PALLET OPERATIONS ----
function promptMoveLocation() {
    if(!currentPallet.id) return;
    if(currentPallet.is_blocked) {
        if(typeof AppDialog !== 'undefined' && AppDialog.alert) {
            AppDialog.alert('Ta paleta jest zablokowana (znajduje się na liście do przesunięcia lub została zablokowana). Przesunięcie jest niemożliwe!');
        } else {
            alert('Ta paleta jest zablokowana (znajduje się na liście do przesunięcia lub została zablokowana). Przesunięcie jest niemożliwe!');
        }
        return;
    }
    
    // Generowanie podpowiedzi tylko raz
    const datalist = document.getElementById('locationSuggestions');
    if (datalist && datalist.children.length === 0) {
        let options = '';
        for(let r=1; r<=10; r++) {
            let rStr = r.toString().padStart(2,'0');
            let maxCols = (r===5) ? 4 : 10;
            let maxRows = (r===5) ? 4 : 3;
            for(let row=1; row<=maxRows; row++) {
                for(let col=1; col<=maxCols; col++) {
                    options += `<option value="R${rStr}${col.toString().padStart(2,'0')}${row.toString().padStart(2,'0')}"></option>`;
                }
            }
        }
        options += '<option value="MP01"></option><option value="MS01"></option><option value="MGW01"></option>';
        options += '<option value="MDM01"></option><option value="MOP01"></option><option value="MGW02"></option>';
        options += '<option value="OSIP"></option><option value="BF_MS01"></option><option value="BF_MP01"></option>';
        options += '<option value="KO01"></option><option value="PSD"></option><option value="PSD01"></option>';
        options += '<option value="RAMPA"></option><option value="MIX01"></option><option value="W_TRANZYCIE_OSIP"></option>';
        datalist.innerHTML = options;
    }

    const input = document.getElementById('newLocationInput');
    const errEl = document.getElementById('moveLocationError');
    const amtInput = document.getElementById('moveAmountInput');
    const currentQtyText = document.getElementById('moveCurrentQtyText');
    const splitNotice = document.getElementById('moveSplitNotice');
    const splitNoticeText = document.getElementById('moveSplitNoticeText');

    const totalQty = parseFloat(currentPallet.amount || 0);

    if(input) {
        input.value = ''; // okno ma być puste
        if(errEl) errEl.style.display = 'none';
    }

    if(currentQtyText) {
        currentQtyText.textContent = totalQty.toFixed(2);
    }

    const updateSplitNotice = () => {
        if(!amtInput || !splitNotice) return;
        const val = parseFloat(amtInput.value);
        if(!isNaN(val) && val > 0 && val < totalQty) {
            const remaining = (totalQty - val).toFixed(2);
            if(splitNoticeText) {
                splitNoticeText.textContent = `Częściowe przesunięcie (podział): ${val.toFixed(2)} kg zostanie przeniesione na nową paletę z nowym kodem SSCC i pełną historią matki. Na obecnej palecie pozostanie ${remaining} kg.`;
            }
            splitNotice.style.display = 'block';
        } else {
            splitNotice.style.display = 'none';
        }
    };

    if(amtInput) {
        amtInput.value = totalQty > 0 ? totalQty : '';
        amtInput.max = totalQty;
        amtInput.oninput = updateSplitNotice;
        updateSplitNotice();
    }
    
    const modal = document.getElementById('moveLocationModal');
    if(modal) modal.style.display = 'flex';
}

function closeMoveLocationModal() {
    const modal = document.getElementById('moveLocationModal');
    if(modal) modal.style.display = 'none';
}

function submitMoveLocation() {
    if(!currentPallet.id) return;
    if(currentPallet.is_blocked) {
        alert('Ta paleta jest zablokowana (znajduje się na liście do przesunięcia)!');
        return;
    }
    const input = document.getElementById('newLocationInput');
    const amtInput = document.getElementById('moveAmountInput');
    const errEl = document.getElementById('moveLocationError');
    const btnSubmit = document.getElementById('btnSubmitMove');
    let newLoc = input ? input.value.trim().toUpperCase() : '';
    
    if(!newLoc) {
        if(errEl) {
            errEl.textContent = 'Lokalizacja nie może być pusta!';
            errEl.style.display = 'block';
        }
        return;
    }

    const totalQty = parseFloat(currentPallet.amount || 0);
    let amountToMove = totalQty;
    if(amtInput && amtInput.value !== '') {
        amountToMove = parseFloat(amtInput.value);
        if(isNaN(amountToMove) || amountToMove <= 0) {
            if(errEl) {
                errEl.textContent = 'Podaj poprawną ilość do przeniesienia (większą od 0)!';
                errEl.style.display = 'block';
            }
            return;
        }
        if(totalQty > 0 && amountToMove > totalQty) {
            if(errEl) {
                errEl.textContent = `Ilość do przeniesienia (${amountToMove} kg) nie może przekraczać dostępnej masy palety (${totalQty} kg)!`;
                errEl.style.display = 'block';
            }
            return;
        }
    }

    if(errEl) errEl.style.display = 'none';
    if(btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'Przenoszenie...';
    }

    fetch('/warehouse-v2/api/pallet/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            location: newLoc,
            linia: currentPallet.linia || 'PSD',
            amount: amountToMove
        })
    }).then(r => r.json()).then(data => {
        if(btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Przenieś';
        }
        if(data.success) {
            const isSplit = (data.split_info && data.split_info.is_split) || (totalQty > 0 && amountToMove < totalQty);
            const newSSCC = data.split_info && data.split_info.new_sscc;
            const movedQty = (data.split_info && data.split_info.moved_qty) || amountToMove;
            const remainingQty = data.split_info && data.split_info.remaining_qty;

            if (isSplit && newSSCC) {
                showToast(`✅ Odcięto ${movedQty} kg na nową paletę (SSCC: ${newSSCC}). Pozostało: ${remainingQty} kg. Otwieram nową etykietę...`, 'success');
                window.open(`/agro/scanner/label/${encodeURIComponent(newSSCC)}?linia=${encodeURIComponent(currentPallet.linia || 'PSD')}&autoprint=1`, '_blank');
            } else if (isSplit) {
                showToast(`Pomyślnie odcięto ${amountToMove} kg na nową paletę na lokalizację: ${newLoc}`, 'success');
            } else {
                showToast(`Przeniesiono pomyślnie na: ${newLoc}`, 'success');
            }
            const targetId = currentPallet.id;
            const targetType = currentPallet.type;
            const targetDisplayId = currentPallet.displayId;

            closeMoveLocationModal();
            closePalletModal();

            if(isSplit) {
                // Przy podziale odświeżamy dane z serwera, bo zmieniły się wagi i powstała nowa paleta
                if (typeof loadWarehouseData === 'function') {
                    loadWarehouseData();
                } else {
                    location.reload();
                }
            } else {
                allWarehouseItems.forEach(x => {
                    if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                        x.location = newLoc;
                    }
                });
                if (typeof currentFilteredItems !== 'undefined') {
                    currentFilteredItems.forEach(x => {
                        if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                            x.location = newLoc;
                        }
                    });
                }
                if (typeof filterTable === 'function') {
                    filterTable();
                }
            }
        } else {
            if(errEl) {
                errEl.textContent = "Błąd: " + (data.error || data.message || "Nieznany błąd zapisu");
                errEl.style.display = 'block';
            } else {
                AppDialog.alert("Błąd: " + (data.error || data.message));
            }
        }
    }).catch(e => {
        if(btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = 'Przenieś';
        }
        if(errEl) {
            errEl.textContent = "Błąd połączenia z serwerem.";
            errEl.style.display = 'block';
        }
    });
}

async function promptRename() {
    if(!currentPallet.id) return;
    const targetId = currentPallet.id;
    const targetType = currentPallet.type;
    const targetDisplayId = currentPallet.displayId;

    let newName = await AppDialog.prompt(`Zmień nazwę produktu dla palety ${currentPallet.displayId}:`, currentPallet.productName);
    if(newName && newName.trim() !== '' && newName.trim() !== currentPallet.productName) {
        const trimmedName = newName.trim();
        fetch('/warehouse-v2/api/pallet/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: targetId,
                type: targetType,
                name: trimmedName,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                showToast("Nazwa zaktualizowana pomyślnie.", 'success');
                allWarehouseItems.forEach(x => {
                    if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                        x.productName = trimmedName;
                    }
                });
                if (typeof currentFilteredItems !== 'undefined') {
                    currentFilteredItems.forEach(x => {
                        if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                            x.productName = trimmedName;
                        }
                    });
                }
                closePalletModal();
                if (typeof filterTable === 'function') {
                    filterTable();
                }
            } else {
                AppDialog.alert("Błąd: " + (data.error || data.message));
            }
        }).catch(err => {
            AppDialog.alert("Błąd połączenia z serwerem: " + err);
        });
    }
}

async function promptUpdateWeight() {
    if(!currentPallet.id) return;
    const targetId = currentPallet.id;
    const targetType = currentPallet.type;
    const targetDisplayId = currentPallet.displayId;
    const targetLinia = currentPallet.linia;

    let newWeight = await AppDialog.prompt(`Podaj nową wagę/ilość dla palety ${targetDisplayId}:`, currentPallet.amount);
    if(newWeight !== null && newWeight !== undefined && String(newWeight).trim() !== '' && parseFloat(newWeight) !== parseFloat(currentPallet.amount)) {
        const parsedW = parseFloat(newWeight);
        if (isNaN(parsedW)) {
            AppDialog.alert("Podana wartość nie jest prawidłową liczbą.");
            return;
        }

        fetch('/warehouse-v2/api/pallet/update-weight', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: targetId,
                type: targetType,
                weight: parsedW,
                linia: targetLinia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                showToast(data.message || "Waga zaktualizowana.", 'success');
                if (parsedW <= 0) {
                    removePalletFromDOM(targetId, `Paleta ${targetDisplayId} zarchiwizowana ✓`);
                } else {
                    allWarehouseItems.forEach(x => {
                        if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                            x.amount = parsedW;
                        }
                    });
                    if (typeof currentFilteredItems !== 'undefined') {
                        currentFilteredItems.forEach(x => {
                            if ((String(x.id) === String(targetId) && x.type === targetType) || (x.displayId && x.displayId === targetDisplayId)) {
                                x.amount = parsedW;
                            }
                        });
                    }
                    closePalletModal();
                    if (typeof filterTable === 'function') {
                        filterTable();
                    }
                }
            } else {
                AppDialog.alert("Błąd: " + (data.error || data.message));
            }
        }).catch(err => {
            AppDialog.alert("Błąd połączenia z serwerem: " + err);
        });
    }
}

async function promptDispatch() {
    if(!currentPallet.id) return;
    const ok = await AppDialog.confirm(`Czy na pewno chcesz WYDAĆ paletę ${currentPallet.displayId}?\n\nPaleta trafi do tabeli EXPEDITION (magazyn_archiwum) i zniknie z aktywnej listy.`);
    if(ok) {
        fetch('/warehouse-v2/api/pallet/dispatch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                removePalletFromDOM(currentPallet.id, `Paleta ${currentPallet.displayId} wydana do EXPEDITION ✓`);
            } else {
                AppDialog.alert("Błąd: " + data.error);
            }
        });
    }
}

async function promptArchive() {
    if(!currentPallet.id) return;
    const ok = await AppDialog.confirm(`Czy na pewno chcesz zarchiwizować paletę ${currentPallet.displayId}? Ilość zostanie wyzerowana.`);
    if(ok) {
        fetch('/warehouse-v2/api/pallet/archive', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                removePalletFromDOM(currentPallet.id, `Paleta ${currentPallet.displayId} zarchiwizowana ✓`);
            } else {
                AppDialog.alert("Błąd: " + data.error);
            }
        });
    }
}

async function promptReturnToRaw() {
    if(!currentPallet.id) return;
    const ok = await AppDialog.confirm(`Czy na pewno chcesz zwrócić paletę ${currentPallet.displayId} (${currentPallet.productName}) jako SUROWIEC?\nPaleta zostanie wyzerowana w wyrobach gotowych i dodana do surowców na lokalizację OSIP.`);
    if(ok) {
        fetch('/warehouse-v2/api/pallet/return-to-raw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                removePalletFromDOM(currentPallet.id, data.message || 'Zwrócono pomyślnie ✓');
            } else {
                AppDialog.alert("Błąd: " + data.error);
            }
        });
    }
}

