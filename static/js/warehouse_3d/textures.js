/**
 * Warehouse 3D - Procedural Canvas Texture Generators & Caches
 */

const sackTextureCache = new Map();
const bigBagTextureCache = new Map();
const beamLabelTextureCache = new Map();
const palletBadgeTextureCache = new Map();

function getPalletStatusBadgeTexture(isFifo, fifoRank, isExpired, isExpiringSoon, daysToExp, isPickingTarget = false, orderRef = '') {
    const key = `${isFifo ? 1 : 0}_${fifoRank || 0}_${isExpired ? 1 : 0}_${isExpiringSoon ? 1 : 0}_${daysToExp !== null && daysToExp !== undefined ? daysToExp : 'none'}_${isPickingTarget ? 1 : 0}_${orderRef || ''}`;
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

    if (isPickingTarget) {
        bgGrad = ctx.createLinearGradient(0, 0, 300, 90);
        if (fifoRank === 1) {
            bgGrad.addColorStop(0, '#b45309');
            bgGrad.addColorStop(1, '#f59e0b');
            borderColor = '#fef08a';
            titleText = '⚡ DO POBRANIA #1 (FIFO)';
        } else {
            bgGrad.addColorStop(0, '#0369a1');
            bgGrad.addColorStop(1, '#0284c7');
            borderColor = '#38bdf8';
            titleText = `📦 DO POBRANIA #${fifoRank || '-'}`;
        }
        subText = orderRef ? `Zlecenie: ${orderRef.slice(-9)}` : 'Zlecenie kompletacji';
    } else if (isExpired) {
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

const qrCanvasCache = new Map();

/**
 * Generates or retrieves a cached canvas with a QR code for a given slot/location code.
 */
function getSlotQrCanvas(slotCode, size = 104) {
    if (!slotCode) return null;
    const cleanCode = String(slotCode).trim();
    const cacheKey = `${cleanCode}_${size}`;
    if (qrCanvasCache.has(cacheKey)) {
        return qrCanvasCache.get(cacheKey);
    }

    if (typeof QRCode === 'undefined') {
        console.warn('QRCode library not loaded yet');
        return null;
    }

    try {
        const tempDiv = document.createElement('div');
        new QRCode(tempDiv, {
            text: cleanCode,
            width: size,
            height: size,
            colorDark: '#000000',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.M
        });

        const qrCanvas = tempDiv.querySelector('canvas');
        if (qrCanvas) {
            qrCanvasCache.set(cacheKey, qrCanvas);
            return qrCanvas;
        }
    } catch (err) {
        console.error('Error generating QR code for slot:', cleanCode, err);
    }
    return null;
}

function getBeamSlotLabelTexture(slotCode, colNum, lvlNum) {
    const key = `${slotCode}_${colNum}_${lvlNum}`;
    if (beamLabelTextureCache.has(key)) {
        return beamLabelTextureCache.get(key);
    }

    // High resolution canvas (512x144) for crisp text & QR code in Three.js
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 144;
    const ctx = canvas.getContext('2d');

    // 1. Warehouse label background (Vibrant industrial yellow)
    ctx.fillStyle = '#fef08a';
    ctx.fillRect(0, 0, 512, 144);

    // 2. Crisp dark outer frame
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 6;
    ctx.strokeRect(3, 3, 506, 138);

    // 3. Left side: Location QR Code square container
    const qrBoxX = 12;
    const qrBoxY = 12;
    const qrBoxSize = 120;
    
    // Pure white background for maximum scanner optical contrast
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(qrBoxX, qrBoxY, qrBoxSize, qrBoxSize);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 3;
    ctx.strokeRect(qrBoxX, qrBoxY, qrBoxSize, qrBoxSize);

    // Draw QR Code
    const qrSize = 104;
    const qrCanvas = getSlotQrCanvas(slotCode, qrSize);
    if (qrCanvas) {
        ctx.drawImage(qrCanvas, qrBoxX + 8, qrBoxY + 8, qrSize, qrSize);
    } else {
        // Fallback placeholder pattern if QRCode library unavailable
        ctx.fillStyle = '#f1f5f9';
        ctx.fillRect(qrBoxX + 8, qrBoxY + 8, qrSize, qrSize);
        ctx.fillStyle = '#64748b';
        ctx.font = 'bold 16px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('QR CODE', qrBoxX + qrBoxSize / 2, qrBoxY + qrBoxSize / 2);
    }

    // 4. Right side: Top Header Ribbon (Col & Level info)
    const rightX = 140;
    const rightW = 360;
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(rightX, 12, rightW, 44);

    ctx.fillStyle = '#38bdf8';
    ctx.font = '900 20px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const lvlText = lvlNum === 0 ? 'P0 (POSADZKA)' : `POZIOM ${lvlNum}`;
    ctx.fillText(`GNIAZDO ${colNum} • ${lvlText}`, rightX + rightW / 2, 34);

    // 5. Right side: Main Location Code (slotCode)
    ctx.fillStyle = '#0f172a';
    ctx.font = '900 48px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(slotCode, rightX + rightW / 2, 96);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = true;
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

const rackHeaderTextureCache = new Map();

function getLargeRackHeaderTexture(rackId, occupiedCount, totalSlots = 0, isPickingMode = false) {
    const key = `${rackId}_${occupiedCount}_${totalSlots}_${isPickingMode ? 1 : 0}`;
    if (rackHeaderTextureCache.has(key)) {
        return rackHeaderTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 200;
    const ctx = canvas.getContext('2d');

    // 1. High contrast dark glassmorphic card
    const bgGrad = ctx.createLinearGradient(0, 0, 640, 200);
    if (occupiedCount > 0) {
        bgGrad.addColorStop(0, '#0f172a');
        bgGrad.addColorStop(1, '#1e293b');
    } else {
        bgGrad.addColorStop(0, '#1e293b');
        bgGrad.addColorStop(1, '#334155');
    }
    ctx.fillStyle = bgGrad;

    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(10, 10, 620, 180, 28);
    } else {
        ctx.rect(10, 10, 620, 180);
    }
    ctx.fill();

    // 2. High-visibility glowing border
    ctx.strokeStyle = occupiedCount > 0 ? (isPickingMode ? '#f59e0b' : '#38bdf8') : '#64748b';
    ctx.lineWidth = 8;
    ctx.stroke();

    // 3. Top accent indicator bar
    const topAccent = ctx.createLinearGradient(20, 14, 620, 14);
    if (isPickingMode && occupiedCount > 0) {
        topAccent.addColorStop(0, '#f59e0b');
        topAccent.addColorStop(0.5, '#fbbf24');
        topAccent.addColorStop(1, '#ef4444');
    } else {
        topAccent.addColorStop(0, '#38bdf8');
        topAccent.addColorStop(0.5, '#818cf8');
        topAccent.addColorStop(1, '#10b981');
    }
    ctx.fillStyle = topAccent;
    ctx.fillRect(40, 16, 560, 8);

    // 4. Large Bold Rack Identifier (e.g. "REGAŁ R02" or "STREFA MP01")
    let title = `REGAŁ ${rackId}`;
    let fontSize = 86;
    if (rackId === 'MP01') {
        title = 'STREFA MP01 (PRODUKCJA)';
        fontSize = 50;
    } else if (rackId === 'BFMP01' || rackId === 'BF_MP01') {
        title = 'BUFOR MP01 (BFMP01)';
        fontSize = 52;
    } else if (rackId.startsWith('BF')) {
        title = `BUFOR ${rackId}`;
        fontSize = 68;
    }

    ctx.fillStyle = '#ffffff';
    ctx.font = `900 ${fontSize}px "Outfit", "Inter", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0,0,0,0.95)';
    ctx.shadowBlur = 12;
    ctx.fillText(title, 320, 84);
    ctx.shadowBlur = 0;

    // 5. Bottom Status Capsule Pill
    let badgeText = '';
    let badgeBg = '#0284c7';
    let badgeTextColor = '#ffffff';

    if (isPickingMode) {
        if (occupiedCount > 0) {
            badgeBg = '#d97706';
            badgeTextColor = '#fef08a';
            badgeText = `🎯 ${occupiedCount} DO POBRANIA (FIFO)`;
        } else {
            badgeBg = '#475569';
            badgeTextColor = '#cbd5e1';
            badgeText = 'BRAK POZYCJI ZE ZLECENIA';
        }
    } else {
        badgeBg = occupiedCount > 0 ? '#0284c7' : '#475569';
        badgeTextColor = '#ffffff';
        badgeText = `📦 ${occupiedCount} ${totalSlots > 0 ? '/ ' + totalSlots : ''} ZAJĘTYCH PALET`;
    }

    ctx.fillStyle = badgeBg;
    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(110, 138, 420, 42, 14);
    } else {
        ctx.rect(110, 138, 420, 42);
    }
    ctx.fill();

    ctx.fillStyle = badgeTextColor;
    ctx.font = '900 24px "Outfit", "Inter", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(badgeText, 320, 159);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    rackHeaderTextureCache.set(key, texture);
    return texture;
}

const floorBayTextureCache = new Map();

function getFloorBayTexture(displayCode, isOccupied = false, isBlocked = false) {
    const key = `${displayCode}_${isOccupied ? 1 : 0}_${isBlocked ? 1 : 0}`;
    if (floorBayTextureCache.has(key)) {
        return floorBayTextureCache.get(key);
    }

    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    ctx.clearRect(0, 0, 512, 512);

    ctx.fillStyle = isOccupied ? 'rgba(30, 41, 59, 0.55)' : 'rgba(15, 23, 42, 0.35)';
    ctx.fillRect(8, 8, 496, 496);

    const lineColor = isBlocked ? '#ef4444' : (isOccupied ? '#f59e0b' : '#38bdf8');
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 14;

    const arm = 90;
    // Top-left
    ctx.beginPath();
    ctx.moveTo(14, 14 + arm);
    ctx.lineTo(14, 14);
    ctx.lineTo(14 + arm, 14);
    ctx.stroke();

    // Top-right
    ctx.beginPath();
    ctx.moveTo(498 - arm, 14);
    ctx.lineTo(498, 14);
    ctx.lineTo(498, 14 + arm);
    ctx.stroke();

    // Bottom-right
    ctx.beginPath();
    ctx.moveTo(498, 498 - arm);
    ctx.lineTo(498, 498);
    ctx.lineTo(498 - arm, 498);
    ctx.stroke();

    // Bottom-left
    ctx.beginPath();
    ctx.moveTo(14 + arm, 498);
    ctx.lineTo(14, 498);
    ctx.lineTo(14, 498 - arm);
    ctx.stroke();

    ctx.save();
    ctx.setLineDash([16, 14]);
    ctx.strokeStyle = isBlocked ? 'rgba(239, 68, 68, 0.4)' : (isOccupied ? 'rgba(245, 158, 11, 0.35)' : 'rgba(56, 189, 248, 0.35)');
    ctx.lineWidth = 4;
    ctx.strokeRect(30, 30, 452, 452);
    ctx.restore();

    ctx.fillStyle = isBlocked ? '#991b1b' : (isOccupied ? '#0369a1' : '#1e293b');
    ctx.beginPath();
    if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(106, 434, 300, 64, 12);
    } else {
        ctx.rect(106, 434, 300, 64);
    }
    ctx.fill();
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 4;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = '900 32px "Outfit", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(displayCode || 'MP01', 256, 466);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    floorBayTextureCache.set(key, texture);
    return texture;
}

let hazardTextureCache = null;
function getHazardBorderTexture() {
    if (hazardTextureCache) return hazardTextureCache;

    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 32;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#facc15';
    ctx.fillRect(0, 0, 256, 32);

    ctx.fillStyle = '#0f172a';
    for (let x = -32; x < 288; x += 32) {
        ctx.beginPath();
        ctx.moveTo(x, 32);
        ctx.lineTo(x + 20, 32);
        ctx.lineTo(x + 36, 0);
        ctx.lineTo(x + 16, 0);
        ctx.closePath();
        ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(10, 1);
    hazardTextureCache = texture;
    return texture;
}
