// ---- REPORTS & PRINT ----
function openReportsModal() { document.getElementById('reportsModal').style.display = 'flex'; }
function closeReportsModal() { document.getElementById('reportsModal').style.display = 'none'; }

function printInventorySheet(items, linia) {
    const sortedItems = [...items].sort((a, b) => (a.productName || '').localeCompare(b.productName || ''));
    let printArea = document.getElementById('customPrintArea');
    if (!printArea) {
        printArea = document.createElement('div');
        printArea.id = 'customPrintArea';
        document.body.appendChild(printArea);
    }
    
    let style = document.getElementById('customPrintStyles');
    if (!style) {
        style = document.createElement('style');
        style.id = 'customPrintStyles';
        document.head.appendChild(style);
    }
    style.innerHTML = `
        @media print {
            body > *:not(#customPrintArea) { display: none !important; }
            #customPrintArea { display: block !important; }
            @page { margin: 0.6cm; size: A4 portrait; }
            body { background: white !important; margin: 0 !important; padding: 0 !important; }
            .checkbox-box { width: 16px; height: 16px; border: 2px solid #000; margin: 0 auto; display: inline-block; }
            .print-qr-code { width: 44px; height: 44px; margin: 0 auto; display: flex; align-items: center; justify-content: center; overflow: hidden; }
            .print-qr-code canvas { display: none !important; }
            .print-qr-code img { width: 44px !important; height: 44px !important; display: block !important; margin: 0 auto; }
        }
        #customPrintArea { display: none; }
    `;

    let html = `
        <div style="font-family: 'Segoe UI', sans-serif; padding: 15px; color: black; background: white;">
            <h1 style="text-align: center; font-size: 18px; border-bottom: 2px solid #000; padding-bottom: 8px; margin-bottom: 12px;">
                ARKUSZ INWENTARYZACJI RĘCZNEJ - MAGAZYN CENTRALNY
            </h1>
            <div style="display: flex; justify-content: space-between; margin-bottom: 15px; font-size: 12px;">
                <span>Data wydruku: ${new Date().toLocaleString()}</span>
                <span>Hala: ${linia}</span>
                <span>Magazynier: ........................................</span>
            </div>
            <table style="width: 100%; border-collapse: collapse; table-layout: fixed;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #000; padding: 4px; text-align: center; width: 30px; font-size: 11px;">Lp.</th>
                        <th style="border: 1px solid #000; padding: 4px; text-align: center; width: 52px; font-size: 11px;">Kod QR</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; width: 140px; font-size: 11px;">Nr SSCC / Palety</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; font-size: 11px;">Nazwa Produktu</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; width: 105px; font-size: 11px;">Data Prod. / Ważn.</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; width: 85px; font-size: 11px;">Partia</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: right; width: 65px; font-size: 11px;">System</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; width: 75px; font-size: 11px; text-align: center;">FAKT.</th>
                    </tr>
                </thead>
                <tbody>
    `;

    sortedItems.forEach((it, index) => {
        const ssccVal = it.nr_palety || it.displayId || String(it.id || '');
        html += `
            <tr>
                <td style="border: 1px solid #000; padding: 3px; text-align: center; font-size: 11px; font-weight: bold; vertical-align: middle;">${index + 1}</td>
                <td style="border: 1px solid #000; padding: 2px; text-align: center; vertical-align: middle;">
                    <div id="inv_qr_${index}" class="print-qr-code"></div>
                </td>
                <td style="border: 1px solid #000; padding: 4px 6px; font-family: monospace; font-weight: bold; font-size: 11px; word-break: break-all; vertical-align: middle;">${ssccVal}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; font-size: 11px; vertical-align: middle;">${it.productName || '-'}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; font-size: 10px; vertical-align: middle;">${it.date_prod || '-'} / ${it.date_exp || '-'}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; font-size: 10px; vertical-align: middle;">${it.batch || '-'}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; text-align: right; font-size: 11px; vertical-align: middle;">${(it.amount || 0).toFixed(1)}</td>
                <td style="border: 1px solid #000; padding: 4px 6px;"></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
            <div style="margin-top: 25px; font-size: 11px;">
                Podpis osoby odpowiedzialnej: ................................................................
            </div>
        </div>
    `;

    printArea.innerHTML = html;

    // Render QR codes
    sortedItems.forEach((it, index) => {
        const ssccVal = it.nr_palety || it.displayId || String(it.id || '');
        const qrEl = document.getElementById(`inv_qr_${index}`);
        if (!qrEl) return;
        if (typeof QRCode !== 'undefined') {
            try {
                qrEl.innerHTML = '';
                new QRCode(qrEl, {
                    text: ssccVal,
                    width: 44,
                    height: 44,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.M
                });
                const canvas = qrEl.querySelector('canvas');
                if (canvas) canvas.remove();
            } catch (e) {
                qrEl.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=44x44&data=${encodeURIComponent(ssccVal)}" width="44" height="44" alt="QR">`;
            }
        } else {
            qrEl.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=44x44&data=${encodeURIComponent(ssccVal)}" width="44" height="44" alt="QR">`;
        }
    });

    setTimeout(() => {
        window.print();
    }, 250);
}

function printFilteredPallets() {
    if (typeof currentFilteredItems === 'undefined' || !currentFilteredItems || currentFilteredItems.length === 0) {
        alert("Brak wyników do wydruku. Najpierw wyszukaj palety.");
        return;
    }

    const searchStr = document.getElementById("searchInput")?.value || "";
    let locStr = "";
    if (typeof selectedLocations !== 'undefined' && selectedLocations.length > 0) {
        if (selectedLocations.length < 5) {
            locStr = selectedLocations.join(", ");
        } else {
            locStr = selectedLocations.length + " wybranych lokalizacji";
        }
    }
    
    let filterInfo = "";
    if (searchStr) filterInfo += `Szukano: "${searchStr}" `;
    if (locStr) filterInfo += `Lokalizacje: "${locStr}"`;
    if (!filterInfo) filterInfo = "Wszystkie pozycje (brak filtrów)";

    // Inject print area if not exists
    let printArea = document.getElementById('customPrintArea');
    if (!printArea) {
        printArea = document.createElement('div');
        printArea.id = 'customPrintArea';
        document.body.appendChild(printArea);
    }
    
    // Inject print styles if not exists
    let style = document.getElementById('customPrintStyles');
    if (!style) {
        style = document.createElement('style');
        style.id = 'customPrintStyles';
        document.head.appendChild(style);
    }
    style.innerHTML = `
        @media print {
            body > *:not(#customPrintArea) { display: none !important; }
            #customPrintArea { display: block !important; }
            @page { margin: 0.6cm; size: A4 portrait; }
            body { background: white !important; margin: 0 !important; padding: 0 !important; }
            .checkbox-box { width: 16px; height: 16px; border: 2px solid #000; margin: 0 auto; display: inline-block; }
            .print-qr-code { width: 44px; height: 44px; margin: 0 auto; display: flex; align-items: center; justify-content: center; overflow: hidden; }
            .print-qr-code canvas { display: none !important; }
            .print-qr-code img { width: 44px !important; height: 44px !important; display: block !important; margin: 0 auto; }
        }
        #customPrintArea { display: none; }
    `;

    let html = `
        <div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 15px; font-size: 11px; color: black; background: white;">
            <h2 style="text-align: center; margin-bottom: 4px; font-size: 16px;">Lista Kontrolna Magazynu (Kody SSCC)</h2>
            <div style="text-align: center; margin-bottom: 12px; font-size: 11px; color: #555;">Data wydruku: ${new Date().toLocaleString()} | ${filterInfo} | Liczba pozycji: ${currentFilteredItems.length}</div>
            
            <table style="width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 8px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #000; padding: 4px; text-align: center; background-color: #f2f2f2; font-weight: bold; width: 32px;">OK</th>
                        <th style="border: 1px solid #000; padding: 4px; text-align: center; background-color: #f2f2f2; font-weight: bold; width: 54px;">Kod QR</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; background-color: #f2f2f2; font-weight: bold; width: 145px;">Nr SSCC / Palety</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: left; background-color: #f2f2f2; font-weight: bold;">Nazwa Produktu</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: right; background-color: #f2f2f2; font-weight: bold; width: 75px;">Ilość/Waga</th>
                        <th style="border: 1px solid #000; padding: 4px 6px; text-align: center; background-color: #f2f2f2; font-weight: bold; width: 95px;">Ważność / Partia</th>
                    </tr>
                </thead>
                <tbody>
    `;

    // Sort by product name then displayId
    const sortedItems = [...currentFilteredItems].sort((a, b) => {
        const prodA = a.productName || '';
        const prodB = b.productName || '';
        if (prodA !== prodB) return prodA.localeCompare(prodB);
        return (a.displayId || '').localeCompare(b.displayId || '');
    });

    sortedItems.forEach((item, index) => {
        const ssccVal = item.nr_palety || item.displayId || String(item.id || '');
        const dateExp = item.date_exp && item.date_exp !== '-' ? item.date_exp : (item.date_prod || '-');
        const batchInfo = item.batch && item.batch !== '-' ? `<br><small style="color:#555;">P: ${item.batch}</small>` : '';

        html += `
            <tr>
                <td style="border: 1px solid #000; padding: 2px; text-align: center; vertical-align: middle;"><div class="checkbox-box"></div></td>
                <td style="border: 1px solid #000; padding: 2px; text-align: center; vertical-align: middle;">
                    <div id="print_qr_${index}" class="print-qr-code"></div>
                </td>
                <td style="border: 1px solid #000; padding: 4px 6px; text-align: left; font-family: monospace; font-weight: bold; font-size: 11px; word-break: break-all; vertical-align: middle;">${ssccVal}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; text-align: left; font-size: 11px; vertical-align: middle;">${item.productName || '-'}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; text-align: right; font-weight: bold; font-size: 11px; vertical-align: middle;">${item.amount} ${item.unit || ''}</td>
                <td style="border: 1px solid #000; padding: 4px 6px; text-align: center; font-size: 10px; vertical-align: middle;">${dateExp}${batchInfo}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
            <div style="margin-top: 20px; display: flex; justify-content: space-between; font-size: 11px;">
                <div>Podpis magazyniera: .......................................</div>
            </div>
        </div>
    `;

    printArea.innerHTML = html;

    // Render QR codes
    sortedItems.forEach((item, index) => {
        const ssccVal = item.nr_palety || item.displayId || String(item.id || '');
        const qrEl = document.getElementById(`print_qr_${index}`);
        if (!qrEl) return;
        
        if (typeof QRCode !== 'undefined') {
            try {
                qrEl.innerHTML = '';
                new QRCode(qrEl, {
                    text: ssccVal,
                    width: 44,
                    height: 44,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.M
                });
                const canvas = qrEl.querySelector('canvas');
                if (canvas) canvas.remove();
            } catch (e) {
                qrEl.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=44x44&data=${encodeURIComponent(ssccVal)}" width="44" height="44" alt="QR">`;
            }
        } else {
            qrEl.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=44x44&data=${encodeURIComponent(ssccVal)}" width="44" height="44" alt="QR">`;
        }
    });

    // Call print after rendering
    setTimeout(() => {
        window.print();
    }, 250);
}
