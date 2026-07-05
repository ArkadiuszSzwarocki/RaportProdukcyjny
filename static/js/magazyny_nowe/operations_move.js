// ---- PALLET OPERATIONS ----
function promptMoveLocation() {
    if(!currentPallet.id) return;
    
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
    if(input) {
        input.value = ''; // okno ma być puste
        if(errEl) errEl.style.display = 'none';
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
    const input = document.getElementById('newLocationInput');
    const errEl = document.getElementById('moveLocationError');
    let newLoc = input ? input.value.trim().toUpperCase() : '';
    
    if(!newLoc) {
        if(errEl) {
            errEl.textContent = 'Lokalizacja nie może być pusta!';
            errEl.style.display = 'block';
        }
        return;
    }

    if(errEl) errEl.style.display = 'none';

    fetch('/magazyny-nowe/api/pallet/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: currentPallet.id,
            type: currentPallet.type,
            location: newLoc,
            linia: currentPallet.linia || 'PSD'
        })
    }).then(r => r.json()).then(data => {
        if(data.success) {
            showToast("Przeniesiono pomyślnie.", 'success');
            closeMoveLocationModal();
            closePalletModal();
            setTimeout(() => window.location.reload(), 1000);
        } else {
            if(errEl) {
                errEl.textContent = "Błąd: " + (data.error || data.message || "Nieznany błąd zapisu");
                errEl.style.display = 'block';
            } else {
                AppDialog.alert("Błąd: " + (data.error || data.message));
            }
        }
    }).catch(e => {
        if(errEl) {
            errEl.textContent = "Błąd połączenia z serwerem.";
            errEl.style.display = 'block';
        }
    });
}

async function promptRename() {
    if(!currentPallet.id) return;
    let newName = await AppDialog.prompt(`Zmień nazwę produktu dla palety ${currentPallet.displayId}:`, currentPallet.productName);
    if(newName && newName !== currentPallet.productName) {
        fetch('/magazyny-nowe/api/pallet/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                name: newName,
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                AppDialog.alert("Nazwa zaktualizowana.").then(() => window.location.reload());
            } else {
                AppDialog.alert("Błąd: " + data.error);
            }
        });
    }
}

async function promptUpdateWeight() {
    if(!currentPallet.id) return;
    let newWeight = await AppDialog.prompt(`Podaj nową wagę/ilość dla palety ${currentPallet.displayId}:`, currentPallet.amount);
    if(newWeight !== null && newWeight !== currentPallet.amount) {
        fetch('/magazyny-nowe/api/pallet/update-weight', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                id: currentPallet.id,
                type: currentPallet.type,
                weight: parseFloat(newWeight),
                linia: currentPallet.linia
            })
        }).then(r => r.json()).then(data => {
            if(data.success) {
                AppDialog.alert(data.message || "Waga zaktualizowana.").then(() => window.location.reload());
            } else {
                AppDialog.alert("Błąd: " + data.error);
            }
        });
    }
}

async function promptDispatch() {
    if(!currentPallet.id) return;
    const ok = await AppDialog.confirm(`Czy na pewno chcesz WYDAĆ paletę ${currentPallet.displayId}?\n\nPaleta trafi do tabeli EXPEDITION (magazyn_archiwum) i zniknie z aktywnej listy.`);
    if(ok) {
        fetch('/magazyny-nowe/api/pallet/dispatch', {
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
        fetch('/magazyny-nowe/api/pallet/archive', {
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
        fetch('/magazyny-nowe/api/pallet/return-to-raw', {
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

