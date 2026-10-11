/**
 * Picking 3D Rack View Module
 * Self-contained, offline-ready 3D isometric warehouse rack renderer with target slot HUD.
 */
const Picking3dRackView = (function () {
    'use strict';

    let canvas, ctx, animId;
    let target = { rackId: 'R01', col: 1, lvl: 1 };
    let panX = 0, panY = 0, zoom = 1, isDragging = false, dragStart = { x: 0, y: 0 };

    function parseLocation(locStr) {
        if (!locStr) return { rackId: 'R01', col: 1, lvl: 1, raw: '' };
        let clean = String(locStr).trim().toUpperCase();
        if (clean.startsWith('RO')) clean = 'R0' + clean.slice(2);

        let m = clean.match(/^R\s*0?(\d{1,2})[\s\-_/.]0?(\d{1,2})[\s\-_/.]0?(\d{1,2})$/);
        if (m) {
            return { rackId: 'R' + String(m[1]).padStart(2, '0'), col: parseInt(m[2], 10) || 1, lvl: parseInt(m[3], 10) || 1, raw: clean };
        }
        const stripped = clean.replace(/[^A-Z0-9]/g, '');
        m = stripped.match(/^R(\d{2})(\d{2})(\d{2})$/);
        if (m) {
            return { rackId: 'R' + m[1], col: parseInt(m[2], 10) || 1, lvl: parseInt(m[3], 10) || 1, raw: clean };
        }
        m = stripped.match(/^R(\d{1})(\d{2})(\d{2})$/);
        if (m) {
            return { rackId: 'R0' + m[1], col: parseInt(m[2], 10) || 1, lvl: parseInt(m[3], 10) || 1, raw: clean };
        }
        return { rackId: clean.includes('MP') ? 'MP01' : (clean.slice(0, 3) || 'R01'), col: 1, lvl: 1, raw: clean };
    }

    function init(containerId) {
        const container = document.getElementById(containerId || 'picking-3d-canvas-container');
        if (!container) return;

        container.innerHTML = '';
        canvas = document.createElement('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.cursor = 'grab';
        container.appendChild(canvas);
        ctx = canvas.getContext('2d');

        bindEvents();
        resize();
        if (!animId) animate();
    }

    function bindEvents() {
        if (!canvas) return;
        canvas.onmousedown = function (e) {
            isDragging = true;
            dragStart = { x: e.clientX - panX, y: e.clientY - panY };
            canvas.style.cursor = 'grabbing';
        };
        window.onmousemove = function (e) {
            if (!isDragging) return;
            panX = e.clientX - dragStart.x;
            panY = e.clientY - dragStart.y;
        };
        window.onmouseup = function () {
            isDragging = false;
            if (canvas) canvas.style.cursor = 'grab';
        };
        canvas.onwheel = function (e) {
            e.preventDefault();
            const factor = e.deltaY < 0 ? 1.1 : 0.9;
            zoom = Math.max(0.6, Math.min(2.5, zoom * factor));
        };
        window.addEventListener('resize', resize);
    }

    function resize() {
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        canvas.width = (rect.width || 440) * dpr;
        canvas.height = (rect.height || 330) * dpr;
        if (ctx) ctx.scale(dpr, dpr);
    }

    function project(c, l, d) {
        const bayW = 38 * zoom, lvlH = 46 * zoom, depthOff = 22 * zoom;
        const x = (c * bayW) + (d * depthOff) + panX;
        const y = -(l * lvlH) + (d * depthOff * 0.45) + panY;
        return { x: x, y: y };
    }

    function drawIsoBox(c, l, w, h, depth, topCol, frontCol, sideCol) {
        const f0 = project(c, l, 0), f1 = project(c + w, l, 0), f2 = project(c + w, l + h, 0), f3 = project(c, l + h, 0);
        const b0 = project(c, l, depth), b1 = project(c + w, l, depth), b2 = project(c + w, l + h, depth), b3 = project(c, l + h, depth);

        ctx.fillStyle = topCol;
        ctx.beginPath();
        ctx.moveTo(f3.x, f3.y); ctx.lineTo(f2.x, f2.y); ctx.lineTo(b2.x, b2.y); ctx.lineTo(b3.x, b3.y);
        ctx.closePath(); ctx.fill();

        ctx.fillStyle = sideCol;
        ctx.beginPath();
        ctx.moveTo(f2.x, f2.y); ctx.lineTo(b2.x, b2.y); ctx.lineTo(b1.x, b1.y); ctx.lineTo(f1.x, f1.y);
        ctx.closePath(); ctx.fill();

        ctx.fillStyle = frontCol;
        ctx.beginPath();
        ctx.moveTo(f0.x, f0.y); ctx.lineTo(f1.x, f1.y); ctx.lineTo(f2.x, f2.y); ctx.lineTo(f3.x, f3.y);
        ctx.closePath(); ctx.fill();
    }

    function render() {
        if (!canvas || !ctx) return;
        const rect = canvas.getBoundingClientRect();
        const cw = rect.width, ch = rect.height;
        ctx.clearRect(0, 0, cw, ch);

        const totalCols = Math.max(target.col, 10);
        const totalLvls = Math.max(target.lvl, 3);
        const originX = cw * 0.15;
        const originY = ch * 0.72;

        ctx.save();
        ctx.translate(originX, originY);

        // Floor Grid
        ctx.strokeStyle = '#1e293b';
        ctx.lineWidth = 1;
        for (let i = 0; i <= totalCols + 2; i++) {
            const p0 = project(i, 0, -0.5), p1 = project(i, 0, 1.8);
            ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke();
        }

        // Uprights & Pallets
        for (let l = 1; l <= totalLvls; l++) {
            for (let c = 1; c <= totalCols; c++) {
                const isTarget = (c === target.col && l === target.lvl);
                if (isTarget) {
                    const time = Date.now() * 0.005;
                    const glowAlpha = 0.4 + Math.sin(time) * 0.25;
                    ctx.fillStyle = 'rgba(16, 185, 129, ' + glowAlpha + ')';
                    const pA = project(c - 0.1, l - 0.05, 0), pB = project(c + 1.1, l + 0.95, 0.9);
                    ctx.fillRect(pA.x, pB.y, (pB.x - pA.x), (pA.y - pB.y));

                    drawIsoBox(c + 0.08, l, 0.84, 0.65, 0.8, '#34d399', '#10b981', '#059669');
                } else {
                    drawIsoBox(c + 0.1, l, 0.8, 0.55, 0.75, '#d4a373', '#b48a56', '#8c6239');
                }
            }
        }

        // Beams and Posts
        for (let c = 0; c <= totalCols; c++) {
            drawIsoBox(c - 0.05, 0.1, 0.1, totalLvls + 0.4, 0.1, '#38bdf8', '#0284c7', '#0369a1');
            drawIsoBox(c - 0.05, 0.1, 0.1, totalLvls + 0.4, 0.9, '#38bdf8', '#0284c7', '#0369a1');
        }
        for (let l = 1; l <= totalLvls; l++) {
            drawIsoBox(0, l - 0.08, totalCols + 0.05, 0.12, 0.1, '#fb923c', '#ea580c', '#c2410c');
            drawIsoBox(0, l - 0.08, totalCols + 0.05, 0.12, 0.9, '#fb923c', '#ea580c', '#c2410c');
        }

        // Floating Target 3D HUD Badge
        const tPos = project(target.col + 0.5, target.lvl + 1.1, 0.4);
        drawHudBadge(tPos.x, tPos.y, target.rackId, target.col, target.lvl);

        ctx.restore();
    }

    function drawHudBadge(x, y, rackId, col, lvl) {
        ctx.save();
        ctx.translate(x, y);

        ctx.fillStyle = '#0f172a';
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(-80, -42, 160, 42, 8) : ctx.fillRect(-80, -42, 160, 42);
        ctx.fill(); ctx.stroke();

        ctx.fillStyle = '#10b981';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('REGAŁ: ' + rackId, 0, -23);

        ctx.fillStyle = '#f8fafc';
        ctx.font = '600 11px sans-serif';
        ctx.fillText('P: ' + lvl + ' • GNIAZDO: ' + col, 0, -7);

        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.moveTo(-6, 0); ctx.lineTo(6, 0); ctx.lineTo(0, 7);
        ctx.closePath(); ctx.fill();
        ctx.restore();
    }

    function animate() {
        render();
        animId = requestAnimationFrame(animate);
    }

    function highlightTarget(locStr) {
        target = parseLocation(locStr);
        resetCamera();
    }

    function resetCamera() {
        if (!canvas) return;
        const cw = canvas.getBoundingClientRect().width || 440;
        zoom = 1;
        panX = (cw * 0.45) - (target.col * 38);
        panY = (target.lvl * 20);
    }

    return {
        init: init,
        highlightTarget: highlightTarget,
        resetCamera: resetCamera,
        resize: resize,
        parseLocation: parseLocation
    };
})();

window.Picking3dRackView = Picking3dRackView;
