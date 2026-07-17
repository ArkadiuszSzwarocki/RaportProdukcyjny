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

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
        alert("Zablokowano otwieranie nowego okna. Zezwól na wyskakujące okienka (pop-ups) w przeglądarce.");
        return;
    }

    const searchStr = document.getElementById("searchInput")?.value || "";
    const locStr = document.getElementById("locationSearchInput")?.value || "";
    let filterInfo = "";
    if (searchStr) filterInfo += `Szukano: "${searchStr}" `;
    if (locStr) filterInfo += `Lokalizacja: "${locStr}"`;
    if (!filterInfo) filterInfo = "Wszystkie pozycje (brak filtrów)";

    let html = `
    <html>
    <head>
        <title>Wydruk Listy Magazynowej</title>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; font-size: 13px; }
            h2 { text-align: center; margin-bottom: 5px; }
            .info { text-align: center; margin-bottom: 20px; font-size: 12px; color: #555; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { border: 1px solid #000; padding: 6px 8px; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            .checkbox-col { width: 40px; text-align: center; }
            .checkbox-box { width: 20px; height: 20px; border: 2px solid #000; margin: 0 auto; display: inline-block; }
            .right { text-align: right; }
            .center { text-align: center; }
            @media print {
                @page { margin: 1cm; size: A4 portrait; }
                button { display: none; }
            }
        </style>
    </head>
    <body>
        <h2>Lista Kontrolna Magazynu</h2>
        <div class="info">Data wydruku: ${new Date().toLocaleString()} | ${filterInfo} | Liczba pozycji: ${currentFilteredItems.length}</div>
        
        <table>
            <thead>
                <tr>
                    <th class="checkbox-col">OK</th>
                    <th>Lokalizacja</th>
                    <th>Nr Palety</th>
                    <th>Nazwa Produktu</th>
                    <th class="right">Ilość/Waga</th>
                    <th>Data Ważności</th>
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
                <td class="checkbox-col"><div class="checkbox-box"></div></td>
                <td class="center"><strong>${item.location || '-'}</strong></td>
                <td>${item.displayId || '-'}</td>
                <td>${item.productName || '-'}</td>
                <td class="right">${item.amount} ${item.unit || ''}</td>
                <td class="center">${item.date_exp !== '-' ? item.date_exp : (item.date_prod || '-')}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
        <div style="margin-top: 30px; display: flex; justify-content: space-between;">
            <div>Podpis magazyniera: .......................................</div>
            <button onclick="window.print()" style="padding: 10px 20px; font-size: 16px; cursor: pointer;">🖨️ Drukuj Teraz</button>
        </div>
        <script>
            // Automatycznie wywołaj drukowanie po załadowaniu
            window.onload = function() { window.print(); }
        </script>
    </body>
    </html>
    `;

    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
}
