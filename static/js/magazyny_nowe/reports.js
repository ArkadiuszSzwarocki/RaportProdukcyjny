// ---- REPORTS & PRINT ----
function openReportsModal() { document.getElementById('reportsModal').style.display = 'flex'; }
function closeReportsModal() { document.getElementById('reportsModal').style.display = 'none'; }

function printInventorySheet(items, linia) {
    const sortedItems = items.sort((a, b) => a.location.localeCompare(b.location));
    const printArea = document.getElementById('printArea');
    if(!printArea) return;
    
    let html = `
        <div style="font-family: 'Segoe UI', sans-serif; padding: 20px;">
            <h1 style="text-align: center; font-size: 20px; border-bottom: 2px solid #000; padding-bottom: 10px;">
                ARKUSZ INWENTARYZACJI RĘCZNEJ - MAGAZYN CENTRALNY
            </h1>
            <div style="display: flex; justify-content: space-between; margin: 20px 0; font-size: 14px;">
                <span>Data wydruku: ${new Date().toLocaleString()}</span>
                <span>Hala: ${linia}</span>
                <span>Magazynier: ........................................</span>
            </div>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #000; padding: 8px; text-align: center; width: 40px;">Lp.</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Lokalizacja</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Nazwa Produktu</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Data Prod. / Ważność</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: left;">Partia (Batch)</th>
                        <th style="border: 1px solid #000; padding: 8px; text-align: right;">System (kg/szt)</th>
                        <th style="border: 1px solid #000; padding: 8px; width: 100px;">STAN FAKTYCZNY</th>
                    </tr>
                </thead>
                <tbody>
    `;

    sortedItems.forEach((it, index) => {
        html += `
            <tr>
                <td style="border: 1px solid #000; padding: 6px; text-align: center; font-size: 12px; font-weight: bold;">${index + 1}</td>
                <td style="border: 1px solid #000; padding: 6px; font-family: monospace; font-weight: bold; font-size: 13px;">${it.location}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 12px;">${it.productName}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${it.date_prod} / ${it.date_exp}</td>
                <td style="border: 1px solid #000; padding: 6px; font-size: 11px;">${it.batch}</td>
                <td style="border: 1px solid #000; padding: 6px; text-align: right; font-size: 12px;">${it.amount.toFixed(1)}</td>
                <td style="border: 1px solid #000; padding: 6px;"></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
            <div style="margin-top: 30px; font-size: 12px;">
                Podpis osoby odpowiedzialnej: ................................................................
            </div>
        </div>
    `;

    printArea.innerHTML = html;
    window.print();
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
    if (!document.getElementById('customPrintStyles')) {
        const style = document.createElement('style');
        style.id = 'customPrintStyles';
        style.innerHTML = `
            @media print {
                body > *:not(#customPrintArea) { display: none !important; }
                #customPrintArea { display: block !important; }
                @page { margin: 1cm; size: A4 portrait; }
                body { background: white !important; margin: 0 !important; padding: 0 !important; }
                .checkbox-box { width: 20px; height: 20px; border: 2px solid #000; margin: 0 auto; display: inline-block; }
            }
            #customPrintArea { display: none; }
        `;
        document.head.appendChild(style);
    }

    let html = `
        <div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; font-size: 13px; color: black; background: white;">
            <h2 style="text-align: center; margin-bottom: 5px;">Lista Kontrolna Magazynu</h2>
            <div style="text-align: center; margin-bottom: 20px; font-size: 12px; color: #555;">Data wydruku: ${new Date().toLocaleString()} | ${filterInfo} | Liczba pozycji: ${currentFilteredItems.length}</div>
            
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: center; background-color: #f2f2f2; font-weight: bold; width: 40px;">OK</th>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: left; background-color: #f2f2f2; font-weight: bold;">Lokalizacja</th>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: left; background-color: #f2f2f2; font-weight: bold;">Nr Palety</th>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: left; background-color: #f2f2f2; font-weight: bold;">Nazwa Produktu</th>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: right; background-color: #f2f2f2; font-weight: bold;">Ilość/Waga</th>
                        <th style="border: 1px solid #000; padding: 6px 8px; text-align: center; background-color: #f2f2f2; font-weight: bold;">Data Ważności</th>
                    </tr>
                </thead>
                <tbody>
    `;

    // Sort by location first, then by name
    const sortedItems = [...currentFilteredItems].sort((a, b) => {
        const locA = a.location || '';
        const locB = b.location || '';
        if (locA !== locB) return locA.localeCompare(locB);
        return (a.productName || '').localeCompare(b.productName || '');
    });

    sortedItems.forEach(item => {
        html += `
            <tr>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: center;"><div class="checkbox-box"></div></td>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: center;"><strong>${item.location || '-'}</strong></td>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: left;">${item.displayId || '-'}</td>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: left;">${item.productName || '-'}</td>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: right;">${item.amount} ${item.unit || ''}</td>
                <td style="border: 1px solid #000; padding: 6px 8px; text-align: center;">${item.date_exp !== '-' ? item.date_exp : (item.date_prod || '-')}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
            <div style="margin-top: 30px; display: flex; justify-content: space-between; font-size: 14px;">
                <div>Podpis magazyniera: .......................................</div>
            </div>
        </div>
    `;

    printArea.innerHTML = html;
    
    // Call print
    setTimeout(() => {
        window.print();
    }, 100);
}
