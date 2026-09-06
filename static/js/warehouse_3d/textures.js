/**
 * Warehouse 3D - Procedural Canvas Texture Generators & Caches
 */

const sackTextureCache = new Map();
const bigBagTextureCache = new Map();
const beamLabelTextureCache = new Map();
const palletBadgeTextureCache = new Map();

function getPalletStatusBadgeTexture(isFifo, fifoRank, isExpired, isExpiringSoon, daysToExp) {
    const key = `${isFifo ? 1 : 0}_${fifoRank || 0}_${isExpired ? 1 : 0}_${isExpiringSoon ? 1 : 0}_${daysToExp !== null && daysToExp !== undefined ? daysToExp : 'none'}`;
    if (palletBadgeTextureCache.has(key)) {
        return palletBadgeTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 300;
    canvas.height = 90;
    const ctx = canvas.getContext('2d');

    let bgGrad;
    let borderColor = '#f59e0b';
    let titleText = '⚡ FIFO #1';
    let subText = 'Wydaj w 1. kolejności';

    if (isExpired) {
        bgGrad = ctx.createLinearGradient(0, 0, 300, 90);
        bgGrad.addColorStop(0, '#7f1d1d');
        bgGrad.addColorStop(1, '#ef4444');
        borderColor = '#fca5a5';
        titleText = '⚠️ PRZETERMINOWANA';
        subText = (daysToExp !== null && daysToExp !== undefined) ? `${Math.abs(daysToExp)} dni po terminie` : 'Po terminie ważności';
    } else if (isExpiringSoon) {
        bgGrad = ctx.createLinearGradient(0, 0, 300, 90);
        bgGrad.addColorStop(0, '#78350f');
        bgGrad.addColorStop(1, '#f59e0b');
        borderColor = '#fef08a';
        titleText = isFifo ? '⚡ FIFO #1 • ⌛ TERMIN' : '⌛ KRÓTKI TERMIN';
        subText = (daysToExp !== null && daysToExp !== undefined) ? `Pozostało: ${daysToExp} dni` : 'Zbliża się termin';
    } else if (isFifo) {
        bgGrad = ctx.createLinearGradient(0, 0, 300, 90);
        bgGrad.addColorStop(0, '#92400e');
        bgGrad.addColorStop(1, '#f59e0b');
        borderColor = '#fef08a';
        titleText = '⚡ PRIORYTET FIFO';
        subText = 'Pierwsza do wydania';
    } else {
        bgGrad = ctx.createLinearGradient(0, 0, 300, 90);
        bgGrad.addColorStop(0, '#0f172a');
        bgGrad.addColorStop(1, '#1e293b');
        borderColor = '#38bdf8';
        titleText = `Kolejka FIFO: #${fifoRank || '-'}`;
        subText = (daysToExp !== null && daysToExp !== undefined) ? `Ważność: ${daysToExp} dni` : 'Dostępna';
    }

    ctx.fillStyle = bgGrad;
    ctx.beginPath();
    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(4, 4, 292, 82, 16);
    } else {
        ctx.rect(4, 4, 292, 82);
    }
    ctx.fill();

    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 4;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = '900 22px "Outfit", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(titleText, 150, 32);

    ctx.fillStyle = isExpired ? '#fecaca' : '#fef08a';
    ctx.font = 'bold 15px monospace';
    ctx.fillText(subText, 150, 64);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    palletBadgeTextureCache.set(key, texture);
    return texture;
}

function getBeamSlotLabelTexture(slotCode, colNum, lvlNum) {
    const key = `${slotCode}_${colNum}_${lvlNum}`;
    if (beamLabelTextureCache.has(key)) {
        return beamLabelTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 72;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#fef08a';
    ctx.fillRect(0, 0, 256, 72);

    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, 252, 68);

    ctx.fillStyle = '#0f172a';
    ctx.fillRect(4, 4, 248, 24);

    ctx.fillStyle = '#38bdf8';
    ctx.font = '900 13px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const lvlText = lvlNum === 0 ? 'P0 (POSADZKA)' : `POZIOM ${lvlNum}`;
    ctx.fillText(`GNIAZDO ${colNum} • ${lvlText}`, 128, 16);

    ctx.fillStyle = '#0f172a';
    ctx.font = '900 24px "JetBrains Mono", monospace';
    ctx.fillText(slotCode, 128, 48);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    beamLabelTextureCache.set(key, texture);
    return texture;
}

function drawCanvasWrappedText(ctx, text, x, y, maxWidth, lineHeight, maxLines = 2) {
    const words = (text || '').trim().split(/\s+/);
    let line = '';
    let currentY = y;
    let linesDrawn = 0;

    for (let n = 0; n < words.length; n++) {
        const testLine = line + words[n] + ' ';
        const metrics = ctx.measureText(testLine);
        if (metrics.width > maxWidth && n > 0) {
            if (linesDrawn === maxLines - 1 && n < words.length - 1) {
                let trunc = line;
                while (trunc.length > 0 && ctx.measureText(trunc + '...').width > maxWidth) {
                    trunc = trunc.slice(0, -1);
                }
                ctx.fillText(trunc + '...', x, currentY);
                return;
            }
            ctx.fillText(line, x, currentY);
            line = words[n] + ' ';
            currentY += lineHeight;
            linesDrawn++;
            if (linesDrawn >= maxLines) return;
        } else {
            line = testLine;
        }
    }
    ctx.fillText(line, x, currentY);
}

function generateSackCanvasTexture(isRotated, productName, batch, weightText) {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    const cleanProd = (productName || 'NAWÓZ AGRO').toUpperCase();
    const cleanBatch = (batch || 'PL-2026-AGRO').toUpperCase();
    const cleanWeight = (weightText || '25.0 kg');

    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, 512, 512);

    for (let i = 0; i < 2200; i++) {
        ctx.fillStyle = (Math.random() > 0.5) ? 'rgba(0,0,0,0.025)' : 'rgba(255,255,255,0.08)';
        ctx.fillRect(Math.random() * 512, Math.random() * 512, 2, 2);
    }

    ctx.fillStyle = '#047857';
    if (!isRotated) {
        ctx.fillRect(0, 0, 22, 512);
        ctx.fillRect(490, 0, 22, 512);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 3;
        ctx.setLineDash([8, 6]);
        ctx.beginPath();
        ctx.moveTo(11, 0); ctx.lineTo(11, 512);
        ctx.moveTo(501, 0); ctx.lineTo(501, 512);
        ctx.stroke();
    } else {
        ctx.fillRect(0, 0, 512, 22);
        ctx.fillRect(0, 490, 512, 22);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 3;
        ctx.setLineDash([8, 6]);
        ctx.beginPath();
        ctx.moveTo(0, 11); ctx.lineTo(512, 11);
        ctx.moveTo(0, 501); ctx.lineTo(512, 501);
        ctx.stroke();
    }
    ctx.setLineDash([]);

    if (!isRotated) {
        ctx.fillStyle = '#065f46';
        ctx.fillRect(36, 36, 440, 76);

        ctx.fillStyle = '#ffffff';
        ctx.font = '900 26px "Outfit", sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('AGRONETZWERK', 56, 78);
        ctx.fillStyle = '#34d399';
        ctx.font = 'bold 11px monospace';
        ctx.fillText('AGRO PREMIUM CROP NUTRITION • STANDARD 25KG', 56, 98);

        ctx.fillStyle = '#0f172a';
        ctx.font = '900 24px sans-serif';
        drawCanvasWrappedText(ctx, cleanProd, 56, 160, 400, 28, 2);

        ctx.fillStyle = '#f1f5f9';
        ctx.fillRect(38, 228, 436, 136);
        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(38, 228, 436, 136);

        ctx.fillStyle = '#0f172a';
        ctx.font = 'bold 15px monospace';
        ctx.fillText(`PARTIA / LOT: ${cleanBatch}`, 56, 264);
        ctx.fillStyle = '#334155';
        ctx.font = '13px monospace';
        ctx.fillText(`MASA NETTO: ${cleanWeight} ■ EN 197-1 CE`, 56, 294);
        ctx.fillText('ISO 9001:2015 ■ KOD PL-WMS CARGO', 56, 324);

        ctx.fillStyle = '#0f172a';
        for (let bx = 56; bx < 300; bx += 4) {
            const bw = (Math.sin(bx * 7) > 0) ? 2.5 : 1.2;
            ctx.fillRect(bx, 386, bw, 42);
        }
    } else {
        ctx.save();
        ctx.translate(256, 256);
        ctx.rotate(Math.PI / 2);

        ctx.fillStyle = '#065f46';
        ctx.fillRect(-220, -220, 440, 76);

        ctx.fillStyle = '#ffffff';
        ctx.font = '900 26px "Outfit", sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('AGRONETZWERK', -200, -178);
        ctx.fillStyle = '#34d399';
        ctx.font = 'bold 11px monospace';
        ctx.fillText('AGRO PREMIUM CROP NUTRITION • STANDARD 25KG', -200, -158);

        ctx.fillStyle = '#0f172a';
        ctx.font = '900 24px sans-serif';
        drawCanvasWrappedText(ctx, cleanProd, -200, -96, 400, 28, 2);

        ctx.fillStyle = '#f1f5f9';
        ctx.fillRect(-220, -28, 440, 136);
        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(-220, -28, 440, 136);

        ctx.fillStyle = '#0f172a';
        ctx.font = 'bold 15px monospace';
        ctx.fillText(`PARTIA / LOT: ${cleanBatch}`, -200, 8);
        ctx.fillStyle = '#334155';
        ctx.font = '13px monospace';
        ctx.fillText(`MASA NETTO: ${cleanWeight} ■ EN 197-1`, -200, 38);
        ctx.fillText('ISO 9001:2015 ■ KOD PL-WMS CARGO', -200, 68);

        ctx.fillStyle = '#0f172a';
        for (let bx = -200; bx < 40; bx += 4) {
            const bw = (Math.sin(bx * 7) > 0) ? 2.5 : 1.2;
            ctx.fillRect(bx, 130, bw, 42);
        }
        ctx.restore();
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.anisotropy = 4;
    return tex;
}

function generateBigBagCanvasTexture(productName, batch, weightText) {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    const cleanProd = (productName || 'SUROWIEC / MATERIAŁ SYPKI').toUpperCase();
    const cleanBatch = (batch || 'PL-2026-BB-WMS').toUpperCase();
    const cleanWeight = (weightText || '1000 kg');

    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, 512, 512);

    ctx.fillStyle = 'rgba(0,0,0,0.04)';
    for (let y = 0; y < 512; y += 3) ctx.fillRect(0, y, 512, 1);
    for (let x = 0; x < 512; x += 3) ctx.fillRect(x, 0, 1, 512);

    ctx.fillStyle = '#ea580c';
    ctx.fillRect(0, 0, 32, 512);
    ctx.fillRect(480, 0, 32, 512);
    ctx.fillStyle = '#fb923c';
    ctx.fillRect(30, 0, 4, 512);
    ctx.fillRect(478, 0, 4, 512);

    ctx.fillStyle = '#0f172a';
    ctx.fillRect(48, 42, 416, 68);
    ctx.fillStyle = '#ffffff';
    ctx.font = '900 24px "Outfit", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('AGRONETZWERK', 256, 80);
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 10px monospace';
    ctx.fillText('INDUSTRIAL BULK CARGO • FIBC 4-LOOP CONTAINER', 256, 98);

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(58, 130, 396, 250);
    ctx.strokeStyle = '#0284c7';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(58, 130, 396, 250);

    ctx.fillStyle = '#0284c7';
    ctx.fillRect(58, 130, 396, 32);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('SPECYFIKACJA MATERIAŁU / RAW MATERIAL SPEC', 72, 151);

    ctx.fillStyle = '#0f172a';
    ctx.font = '900 20px sans-serif';
    drawCanvasWrappedText(ctx, cleanProd, 72, 192, 368, 24, 2);

    ctx.fillStyle = '#334155';
    ctx.font = 'bold 12px monospace';
    ctx.fillText(`SWL: ${cleanWeight} (Safe Working Load)`, 72, 252);
    ctx.fillText('SF: 5:1 (Współczynnik bezpieczeństwa)', 72, 276);
    ctx.fillText('NORM: EN ISO 21898:2004 ■ UN 13H2', 72, 300);
    ctx.fillText(`PARTIA / LOT: ${cleanBatch}`, 72, 324);

    ctx.fillStyle = '#0f172a';
    for (let bx = 72; bx < 330; bx += 4) {
        const bw = (Math.sin(bx * 11) > 0) ? 2.5 : 1.2;
        ctx.fillRect(bx, 342, bw, 22);
    }

    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(58, 400, 396, 36);
    ctx.fillStyle = '#000000';
    ctx.font = '900 11px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('⚠️ PODNOSIĆ ZA WSZYSTKIE 4 UCHWYTY PIONOWO', 256, 423);

    const tex = new THREE.CanvasTexture(canvas);
    tex.anisotropy = 4;
    return tex;
}

function getOrCreateSackTexture(productName, batch, isRotated, weightText) {
    const key = `${productName || 'AGRO'}_${batch || 'LOT'}_${weightText || '25'}_${isRotated ? 'R' : 'N'}`;
    if (sackTextureCache.has(key)) {
        return sackTextureCache.get(key);
    }
    const tex = generateSackCanvasTexture(isRotated, productName, batch, weightText);
    sackTextureCache.set(key, tex);
    return tex;
}

function getOrCreateBigBagTexture(productName, batch, weightText) {
    const key = `${productName || 'BB'}_${batch || 'LOT'}_${weightText || '1000'}`;
    if (bigBagTextureCache.has(key)) {
        return bigBagTextureCache.get(key);
    }
    const tex = generateBigBagCanvasTexture(productName, batch, weightText);
    bigBagTextureCache.set(key, tex);
    return tex;
}

const shelfItemTextureCache = new Map();
const shelfMultiBadgeTextureCache = new Map();

function getShelfItemCardboardTexture(productName, batch, amountText, nrPalety, accentColor = '#0284c7') {
    const key = `${productName || 'ITEM'}_${batch || 'LOT'}_${amountText || '0'}_${nrPalety || 'OPK'}_${accentColor}`;
    if (shelfItemTextureCache.has(key)) {
        return shelfItemTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    // 1. Realistic kraft cardboard base
    ctx.fillStyle = '#bfa175';
    ctx.fillRect(0, 0, 512, 512);

    // Subtle cardboard fiber noise
    for (let i = 0; i < 2400; i++) {
        ctx.fillStyle = (Math.random() > 0.5) ? 'rgba(0,0,0,0.035)' : 'rgba(255,255,255,0.05)';
        ctx.fillRect(Math.random() * 512, Math.random() * 512, 2, 2);
    }

    // Corrugated edge shadows and folding crease
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.fillRect(0, 0, 512, 12);
    ctx.fillRect(0, 500, 512, 12);
    ctx.fillRect(0, 0, 12, 512);
    ctx.fillRect(500, 0, 12, 512);

    // Packing tape horizontal band
    ctx.fillStyle = 'rgba(180, 125, 60, 0.45)';
    ctx.fillRect(0, 240, 512, 32);

    // 2. High-contrast Warehouse Assortment Label (White adhesive label)
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(36, 44, 440, 424);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 3;
    ctx.strokeRect(36, 44, 440, 424);

    // Accent header strip
    ctx.fillStyle = accentColor;
    ctx.fillRect(36, 44, 440, 54);

    ctx.fillStyle = '#ffffff';
    ctx.font = '900 22px "Outfit", sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('PÓŁKA REGALOWA • ASORTYMENT', 54, 78);

    // Product Title
    const cleanProd = (productName || 'ASORTYMENT').toUpperCase();
    ctx.fillStyle = '#0f172a';
    ctx.font = '900 28px "Outfit", sans-serif';
    drawCanvasWrappedText(ctx, cleanProd, 54, 136, 400, 32, 2);

    // Divider
    ctx.fillStyle = '#e2e8f0';
    ctx.fillRect(54, 196, 404, 3);

    // Product Details Box
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(54, 212, 404, 144);
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(54, 212, 404, 144);

    ctx.fillStyle = '#0f172a';
    ctx.font = 'bold 20px monospace';
    ctx.fillText(`STAN: ${amountText || '1 szt'}`, 70, 246);

    ctx.fillStyle = '#334155';
    ctx.font = 'bold 16px monospace';
    ctx.fillText(`PARTIA / LOT: ${batch || '-'}`, 70, 280);

    ctx.fillStyle = '#475569';
    ctx.font = '14px monospace';
    ctx.fillText(`KOD / SSCC: ${nrPalety || '-'}`, 70, 314);
    ctx.fillText('TYP: KOMPLETACJA / PÓŁKA', 70, 340);

    // Barcode at bottom
    ctx.fillStyle = '#0f172a';
    for (let bx = 70; bx < 420; bx += 5) {
        const bw = (Math.sin(bx * 13) > 0) ? 3.2 : 1.5;
        ctx.fillRect(bx, 376, bw, 46);
    }
    ctx.fillStyle = '#64748b';
    ctx.font = '12px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`*${nrPalety || 'ITEM'}*`, 256, 442);

    const tex = new THREE.CanvasTexture(canvas);
    tex.anisotropy = 4;
    shelfItemTextureCache.set(key, tex);
    return tex;
}

function getShelfMultiItemBadgeTexture(count) {
    const key = `multi_${count}`;
    if (shelfMultiBadgeTextureCache.has(key)) {
        return shelfMultiBadgeTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 280;
    canvas.height = 70;
    const ctx = canvas.getContext('2d');

    const bgGrad = ctx.createLinearGradient(0, 0, 280, 70);
    bgGrad.addColorStop(0, '#0369a1');
    bgGrad.addColorStop(1, '#0284c7');
    ctx.fillStyle = bgGrad;

    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(4, 4, 272, 62, 14);
    } else {
        ctx.rect(4, 4, 272, 62);
    }
    ctx.fill();

    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 3.5;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = '900 24px "Outfit", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`📦 ${count} POZYCJE NA PÓŁCE`, 140, 26);

    ctx.fillStyle = '#fef08a';
    ctx.font = 'bold 13px monospace';
    ctx.fillText('Wieloasortymentowa', 140, 50);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    shelfMultiBadgeTextureCache.set(key, texture);
    return texture;
}
