// ---- SORTING LOGIC ----
function sortTable(n) {
    const table = document.getElementById("magazynyTable");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;
    
    const rows = Array.from(tbody.querySelectorAll("tr"));
    if (rows.length <= 1) return;

    const ths = table.querySelectorAll("thead th");
    const th = ths[n];
    let dir = th.getAttribute("data-dir") === "asc" ? "desc" : "asc";
    
    ths.forEach(t => t.setAttribute("data-dir", ""));
    th.setAttribute("data-dir", dir);

    rows.sort((rowA, rowB) => {
        let tdA = rowA.getElementsByTagName("td")[n];
        let tdB = rowB.getElementsByTagName("td")[n];
        
        if (!tdA || !tdB) return 0;
        
        let valA = tdA.textContent.trim();
        let valB = tdB.textContent.trim();
        
        if (n === 3) { // Ilość column index shifted
            let numA = parseFloat(valA.replace(/[^0-9.-]+/g,""));
            let numB = parseFloat(valB.replace(/[^0-9.-]+/g,""));
            if (!isNaN(numA) && !isNaN(numB)) {
                return dir === "asc" ? numA - numB : numB - numA;
            }
        }

        if (n === 4) { // Lokalizacja
            const locA = parseLocationCode(valA);
            const locB = parseLocationCode(valB);

            if (locA && locB) {
                if (locA.rackNo !== locB.rackNo) {
                    return dir === "asc" ? locA.rackNo - locB.rackNo : locB.rackNo - locA.rackNo;
                }
                if (locA.rowNo !== locB.rowNo) {
                    return dir === "asc" ? locA.rowNo - locB.rowNo : locB.rowNo - locA.rowNo;
                }
                if (locA.placeNo !== locB.placeNo) {
                    return dir === "asc" ? locA.placeNo - locB.placeNo : locB.placeNo - locA.placeNo;
                }
            } else if (locA && !locB) {
                return dir === "asc" ? -1 : 1;
            } else if (!locA && locB) {
                return dir === "asc" ? 1 : -1;
            }
        }
        return dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
    });

    const frag = document.createDocumentFragment();
    rows.forEach(r => frag.appendChild(r));
    tbody.appendChild(frag);
}


