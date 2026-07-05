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


