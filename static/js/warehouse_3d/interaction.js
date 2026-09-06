/**
 * Warehouse 3D - Interaction, Raycasting, Drag & Drop Relocation & Inspection Drawer
 */

let is3DDragEnabled = false;
let selectedSlotMesh = null;
let dropZoneHighlightMesh = null;

let dragState = {
    isDragging: false,
    pending: false,
    slot: null,
    rack: null,
    pallet: null,
    slotGroup: null,
    hitMesh: null,
    originalPos: null,
    targetSlot: null,
    targetRack: null,
    targetMesh: null,
    startX: 0,
    startY: 0,
    hasMoved: false
};

function toggleRelocateMode() {
    is3DDragEnabled = !is3DDragEnabled;
    updateRelocateButtonUI();
    if (is3DDragEnabled) {
        notifyUser('🔓 Tryb relokacji myszą został ODBLOKOWANY. Możesz teraz przeciągać palety na wolne gniazda.', 'info');
    } else {
        notifyUser('🔒 Tryb relokacji został ZABLOKOWANY.', 'info');
    }
}

function updateRelocateButtonUI() {
    const btn = document.getElementById('btnToggleRelocateMode');
    const icon = document.getElementById('iconRelocateLock');
    const text = document.getElementById('textRelocateLock');
    if (!btn || !icon || !text) return;
    if (is3DDragEnabled) {
        btn.classList.add('relocate-active');
        icon.innerText = 'lock_open';
        icon.style.color = '#000000';
        text.innerText = 'Relokacja: ODBLOKOWANA';
    } else {
        btn.classList.remove('relocate-active');
        icon.innerText = 'lock';
        icon.style.color = '#94a3b8';
        text.innerText = 'Relokacja (Zablokowana)';
    }
}

function resetRelocateMode() {
    if (is3DDragEnabled) {
        is3DDragEnabled = false;
        updateRelocateButtonUI();
    }
}

function onDocumentPointerDown(event) {
    if (!camera || !scene || !renderer || event.button !== 0) return;

    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(interactiveSlotMeshes, false);

    if (intersects.length > 0) {
        const hit = intersects[0].object;
        const slot = hit.userData.slot;
        const rack = hit.userData.rack;
        const slotGroup = hit.userData.parentGroup;

        const pallets = (slot.pallets && slot.pallets.length > 0) ? slot.pallets : (slot.pallet ? [slot.pallet] : []);
        const pallet = (pallets.length > 0) ? pallets[0] : null;

        dragState = {
            isDragging: false,
            pending: true,
            slot: slot,
            rack: rack,
            pallet: pallet,
            slotGroup: slotGroup,
            hitMesh: hit,
            originalPos: slotGroup ? slotGroup.position.clone() : new THREE.Vector3(),
            targetSlot: null,
            targetRack: null,
            targetMesh: null,
            startX: event.clientX,
            startY: event.clientY,
            hasMoved: false
        };
    }
}

function onDocumentPointerMove(event) {
    if (!is3DDragEnabled) return;
    if (!dragState.pending && !dragState.isDragging) return;

    const dist = Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY);

    if (!dragState.isDragging && dist > 6) {
        if (dragState.slot && dragState.slot.is_occupied && dragState.pallet) {
            dragState.isDragging = true;
            dragState.hasMoved = true;
            if (controls) controls.enabled = false;

            if (dragState.slotGroup) {
                dragState.slotGroup.position.y = dragState.originalPos.y + 0.38;
            }

            const hud = document.getElementById('wh3dDragHUD');
            const hudText = document.getElementById('wh3dDragHUDText');
            if (hud && hudText) {
                const pCode = dragState.pallet.nr_palety || dragState.pallet.display_id || `ID #${dragState.pallet.id}`;
                hudText.innerHTML = `Przenosisz paletę: <span style="color:#38bdf8; font-family:monospace;">${pCode}</span> • Upuść na wolne gniazdo regałowe`;
                hud.style.display = 'flex';
            }
        } else {
            dragState.pending = false;
            return;
        }
    }

    if (dragState.isDragging) {
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(interactiveSlotMeshes, false);

        let foundTarget = false;
        if (intersects.length > 0) {
            for (let hit of intersects) {
                const s = hit.object.userData.slot;
                const r = hit.object.userData.rack;
                if (s && s.location_code !== dragState.slot.location_code) {
                    foundTarget = true;
                    dragState.targetSlot = s;
                    dragState.targetRack = r;
                    dragState.targetMesh = hit.object;

                    showDropZoneHighlight(hit.object, s, r, !s.is_occupied);

                    const hudText = document.getElementById('wh3dDragHUDText');
                    if (hudText) {
                        if (!s.is_occupied) {
                            hudText.innerHTML = `🟢 <span style="color: #4ade80;">WOLNE GNIAZDO: ${s.location_code}</span> • Puść przycisk myszy, aby przenieść`;
                        } else {
                            hudText.innerHTML = `⛔ <span style="color: #f87171;">ZAJĘTE GNIAZDO: ${s.location_code}</span> • Wybierz puste miejsce`;
                        }
                    }
                    break;
                }
            }
        }

        if (!foundTarget) {
            dragState.targetSlot = null;
            dragState.targetRack = null;
            dragState.targetMesh = null;
            clearDropZoneHighlight();
            const hudText = document.getElementById('wh3dDragHUDText');
            if (hudText) {
                const pCode = dragState.pallet.nr_palety || dragState.pallet.display_id || `ID #${dragState.pallet.id}`;
                hudText.innerHTML = `Przenosisz paletę: <span style="color:#38bdf8; font-family:monospace;">${pCode}</span> • Najedź na wolne gniazdo`;
            }
        }
    }
}

async function onDocumentPointerUp(event) {
    if (controls) controls.enabled = true;

    const hud = document.getElementById('wh3dDragHUD');
    if (hud) hud.style.display = 'none';
    clearDropZoneHighlight();

    if (dragState.isDragging) {
        const targetSlot = dragState.targetSlot;
        const pallet = dragState.pallet;

        if (targetSlot && !targetSlot.is_occupied && pallet) {
            await executePallet3DMove(pallet, targetSlot.location_code);
        } else {
            if (dragState.slotGroup && dragState.originalPos) {
                dragState.slotGroup.position.copy(dragState.originalPos);
            }
        }
    } else if (dragState.pending && !dragState.hasMoved) {
        const clickDist = Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY);
        if (clickDist <= 6 && dragState.slot && dragState.rack && dragState.hitMesh) {
            selectSlot(dragState.slot, dragState.rack, dragState.hitMesh);
        }
    }

    dragState.isDragging = false;
    dragState.pending = false;
    dragState.slot = null;
    dragState.pallet = null;
    dragState.slotGroup = null;
}

function showDropZoneHighlight(mesh, slot, rack, isValid) {
    if (!dropZoneHighlightMesh) {
        const boxGeo = new THREE.BoxGeometry(rack.bay_width_m * 0.95, rack.level_height_m * 0.95, rack.depth_m * 0.95);
        dropZoneHighlightMesh = new THREE.Mesh(boxGeo, isValid ? sharedMats.dropValid : sharedMats.dropInvalid);
        scene.add(dropZoneHighlightMesh);
    } else {
        dropZoneHighlightMesh.material = isValid ? sharedMats.dropValid : sharedMats.dropInvalid;
    }

    const worldPos = new THREE.Vector3();
    mesh.getWorldPosition(worldPos);
    dropZoneHighlightMesh.position.copy(worldPos);
    dropZoneHighlightMesh.visible = true;
}

function clearDropZoneHighlight() {
    if (dropZoneHighlightMesh) {
        dropZoneHighlightMesh.visible = false;
    }
}

function notifyUser(msg, type = 'info') {
    if (typeof showToast === 'function') {
        showToast(msg, type);
        return;
    }
    console.log(`[3D WMS] [${type.toUpperCase()}] ${msg}`);
}

async function executePallet3DMove(pallet, newLocation) {
    const palletId = pallet.id;
    const palletType = pallet.pallet_type || pallet.typ || 'Surowiec';
    const linia = pallet.linia || (typeof LINIA !== 'undefined' ? LINIA : 'PSD');
    const pCode = pallet.nr_palety || pallet.display_id || `#${palletId}`;

    try {
        const res = await fetch('/warehouse-v2/api/pallet/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: palletId,
                type: palletType,
                location: newLocation,
                linia: linia
            })
        });

        const data = await res.json();
        if (data && data.success) {
            notifyUser(`✅ Paleta ${pCode} została pomyślnie przeniesiona na lokalizację: ${newLocation}`, 'success');
            await loadWarehouseData(false, true);
        } else {
            notifyUser(`Błąd relokacji: ${data ? (data.error || 'Nie udało się przenieść palety') : 'Błąd serwera'}`, 'error');
            if (dragState.slotGroup && dragState.originalPos) {
                dragState.slotGroup.position.copy(dragState.originalPos);
            }
        }
    } catch (err) {
        console.error('Błąd przenoszenia palety:', err);
        notifyUser('Błąd połączenia z serwerem podczas relokacji.', 'error');
        if (dragState.slotGroup && dragState.originalPos) {
            dragState.slotGroup.position.copy(dragState.originalPos);
        }
    }
}

function selectSlot(slot, rack, mesh) {
    if (selectedSlotMesh) {
        scene.remove(selectedSlotMesh);
        selectedSlotMesh = null;
    }

    const boxGeo = new THREE.BoxGeometry(rack.bay_width_m * 0.95, rack.level_height_m * 0.95, rack.depth_m * 0.95);
    selectedSlotMesh = new THREE.Mesh(boxGeo, sharedMats.highlight);
    
    const worldPos = new THREE.Vector3();
    mesh.getWorldPosition(worldPos);
    selectedSlotMesh.position.copy(worldPos);
    scene.add(selectedSlotMesh);

    openInspectDrawer(slot, rack);
}

function openInspectDrawer(slot, rack) {
    const drawer = document.getElementById('wh3dInspectDrawer');
    const locBadge = document.getElementById('inspectLocCode');
    const content = document.getElementById('inspectContent');
    if (!drawer || !locBadge || !content) return;

    locBadge.innerText = slot.location_code;

    let html = `
        <div class="wh3d-row">
            <span class="wh3d-row-lbl">Regał / Sektor:</span>
            <span class="wh3d-row-val">${rack.name}</span>
        </div>
        <div class="wh3d-row">
            <span class="wh3d-row-lbl">Kolumna / Poziom:</span>
            <span class="wh3d-row-val">K${slot.column_index} • P${slot.level_index}</span>
        </div>
        <div class="wh3d-row">
            <span class="wh3d-row-lbl">Status Slotu:</span>
            <span class="wh3d-row-val" style="color: ${slot.is_occupied ? '#10b981' : '#94a3b8'}">
                ${slot.is_occupied ? '● ZAJĘTY' : '○ WOLNY'}
            </span>
        </div>
    `;

    const pallets = (slot.pallets && slot.pallets.length > 0) ? slot.pallets : (slot.pallet ? [slot.pallet] : []);

    if (slot.is_occupied && pallets.length > 0) {
        pallets.forEach((p) => {
            const isBlocked = p.is_blocked || slot.is_blocked;
            const pNum = p.nr_palety || p.display_id || `PAL-${p.id || 'N/A'}`;
            const amountText = (p.weight_kg !== undefined && p.weight_kg !== null) 
                ? `${p.weight_kg.toFixed(1)} ${p.unit || 'kg'}`
                : (p.amount ? `${p.amount} ${p.unit || 'kg'}` : '-');

            let pkgLabel = 'Worki (25kg)';
            if (p.packaging_type === 'BIG_BAG') pkgLabel = 'Big Bag (1000kg)';
            else if (p.packaging_type === 'WRAPPED_PALLET') pkgLabel = 'Paleta Owinięta / Karton';

            let fifoPill = '';
            if (p.is_first_fifo) {
                fifoPill = `<span style="background: linear-gradient(135deg, #f59e0b, #d97706); color: #000000; font-weight: 900; font-size: 10px; padding: 2px 8px; border-radius: 6px; box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);">⚡ PIERWSZE FIFO (#1)</span>`;
            } else if (p.fifo_rank) {
                fifoPill = `<span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 10px; padding: 2px 6px; border-radius: 6px;">FIFO: #${p.fifo_rank}</span>`;
            }

            let expPill = '';
            if (p.is_expired) {
                expPill = `<span style="background: #ef4444; color: #ffffff; font-weight: 800; font-size: 10px; padding: 2px 8px; border-radius: 6px;">⚠️ ${p.exp_status_label || 'PRZETERMINOWANA'}</span>`;
            } else if (p.is_expiring_soon) {
                expPill = `<span style="background: #f59e0b; color: #000000; font-weight: 800; font-size: 10px; padding: 2px 8px; border-radius: 6px;">⌛ ${p.exp_status_label || 'KRÓTKI TERMIN'}</span>`;
            } else if (p.days_to_exp !== null && p.days_to_exp !== undefined) {
                expPill = `<span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 10px; padding: 2px 6px; border-radius: 6px;">✅ Ważna (${p.days_to_exp} dni)</span>`;
            }

            html += `
                <div class="wh3d-pallet-card ${isBlocked ? 'blocked' : ''}" style="margin-top: 12px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                        <strong style="color: #38bdf8; font-size: 14px; font-family: monospace;">${pNum}</strong>
                        <span class="status-pill ${isBlocked ? 'praca' : 'ready'}" style="font-size: 10px; padding: 2px 8px;">
                            ${isBlocked ? '⛔ KWARANTANNA' : 'DOSTĘPNA'}
                        </span>
                    </div>

                    ${(fifoPill || expPill) ? `
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; padding: 6px 8px; background: rgba(15, 23, 42, 0.6); border-radius: 8px;">
                        ${fifoPill}
                        ${expPill}
                    </div>
                    ` : ''}

                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Produkt:</span>
                        <span class="wh3d-row-val" style="color: #fef08a;">${p.product_name || '-'}</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Kategoria / Typ:</span>
                        <span class="wh3d-row-val">${p.pallet_type || 'Wyrób'} (${pkgLabel})</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Stan / Masa:</span>
                        <span class="wh3d-row-val">${amountText}</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Partia (LOT):</span>
                        <span class="wh3d-row-val">${p.batch || '-'}</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Data Produkcji:</span>
                        <span class="wh3d-row-val">${p.date_prod || '-'}</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Data Ważności:</span>
                        <span class="wh3d-row-val">${p.date_exp || '-'}</span>
                    </div>
                    <div class="wh3d-row">
                        <span class="wh3d-row-lbl">Hala / Magazyn:</span>
                        <span class="wh3d-row-val">${p.linia || 'PSD'}</span>
                    </div>
                    ${isBlocked && p.block_reason ? `
                    <div class="wh3d-row" style="margin-top: 6px; border-top: 1px dashed rgba(239, 68, 68, 0.4); padding-top: 6px;">
                        <span class="wh3d-row-lbl" style="color: #ef4444;">Powód Blokady:</span>
                        <span class="wh3d-row-val" style="color: #fca5a5;">${p.block_reason}</span>
                    </div>
                    ` : ''}
                </div>
            `;
        });
    } else {
        html += `
            <div style="text-align: center; padding: 24px 12px; color: #94a3b8; font-size: 13px;">
                <span class="material-icons" style="font-size: 32px; color: #64748b; margin-bottom: 6px;">check_box_outline_blank</span>
                <div>Gniazdo regałowe jest puste i gotowe do przyjęcia palety.</div>
            </div>
        `;
    }

    content.innerHTML = html;
    drawer.classList.add('open');
}

function closeInspectDrawer() {
    const drawer = document.getElementById('wh3dInspectDrawer');
    if (drawer) drawer.classList.remove('open');
    if (selectedSlotMesh) {
        scene.remove(selectedSlotMesh);
        selectedSlotMesh = null;
    }
}

function makeDrawerDraggable() {
    const drawer = document.getElementById('wh3dInspectDrawer');
    if (!drawer) return;

    let isDragging = false;
    let startX, startY, initialLeft, initialTop;

    const onDragStart = (clientX, clientY, target) => {
        if (target.closest('.wh3d-drawer-close')) return;
        isDragging = true;
        startX = clientX;
        startY = clientY;
        const rect = drawer.getBoundingClientRect();
        const parentRect = drawer.parentElement.getBoundingClientRect();
        initialLeft = rect.left - parentRect.left;
        initialTop = rect.top - parentRect.top;
        drawer.style.right = 'auto';
        drawer.style.left = initialLeft + 'px';
        drawer.style.top = initialTop + 'px';
    };

    const onDragMove = (clientX, clientY) => {
        if (!isDragging) return;
        const dx = clientX - startX;
        const dy = clientY - startY;
        const parentRect = drawer.parentElement.getBoundingClientRect();
        let newLeft = initialLeft + dx;
        let newTop = initialTop + dy;
        newLeft = Math.max(10, Math.min(newLeft, parentRect.width - drawer.offsetWidth - 10));
        newTop = Math.max(10, Math.min(newTop, parentRect.height - drawer.offsetHeight - 10));
        drawer.style.left = newLeft + 'px';
        drawer.style.top = newTop + 'px';
    };

    const onDragEnd = () => {
        isDragging = false;
    };

    drawer.addEventListener('mousedown', (e) => {
        if (e.target.closest('.wh3d-drawer-hdr')) {
            onDragStart(e.clientX, e.clientY, e.target);
        }
    });

    document.addEventListener('mousemove', (e) => {
        onDragMove(e.clientX, e.clientY);
    });

    document.addEventListener('mouseup', onDragEnd);

    drawer.addEventListener('touchstart', (e) => {
        if (e.target.closest('.wh3d-drawer-hdr')) {
            const t = e.touches[0];
            onDragStart(t.clientX, t.clientY, e.target);
        }
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
        if (isDragging && e.touches.length > 0) {
            const t = e.touches[0];
            onDragMove(t.clientX, t.clientY);
        }
    }, { passive: true });

    document.addEventListener('touchend', onDragEnd);
}
