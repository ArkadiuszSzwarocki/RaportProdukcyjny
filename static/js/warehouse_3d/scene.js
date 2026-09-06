/**
 * Warehouse 3D - Scene Lifecycle, Camera Controls, Stage Reconstruction & API Data Sync
 */

let scene, camera, renderer, controls;
let warehouseGroup;
let interactiveSlotMeshes = [];
let raycaster, mouse;
let isAutoRotating = false;
let activeWarehouseState = null;
let searchDebounceTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    init3DStage();
    loadWarehouseData(true);
    makeDrawerDraggable();
});

function init3DStage() {
    const container = document.getElementById('wh3dCanvasStage');
    if (!container || typeof THREE === 'undefined') return;

    // Suppress global SmartPolling and partial DOM reloads on the 3D twin page
    if (typeof stopSmartPolling === 'function') {
        stopSmartPolling();
    }
    const mainEl = document.getElementById('mainContent');
    if (mainEl) {
        mainEl.setAttribute('data-no-autorefresh', 'true');
    }

    const width = container.clientWidth || 900;
    const height = container.clientHeight || 600;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1120);
    scene.fog = new THREE.FogExp2(0x0b1120, 0.012);

    camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 350);
    camera.position.set(-18, 14, 22);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    if (typeof THREE.OrbitControls !== 'undefined') {
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.maxPolarAngle = Math.PI / 2 - 0.02;
        controls.minDistance = 2;
        controls.maxDistance = 140;
        controls.target.set(-5, 3, 0);
    }

    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1e293b, 0.75);
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.95);
    dirLight.position.set(25, 40, 25);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    scene.add(dirLight);

    const blueLight = new THREE.PointLight(0x38bdf8, 0.45, 60);
    blueLight.position.set(-10, 10, 0);
    scene.add(blueLight);

    const floorGeo = new THREE.PlaneGeometry(160, 160);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.85, metalness: 0.15 });
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.receiveShadow = true;
    scene.add(floorMesh);

    const gridHelper = new THREE.GridHelper(140, 70, 0x38bdf8, 0x1e293b);
    gridHelper.position.y = 0.01;
    scene.add(gridHelper);

    warehouseGroup = new THREE.Group();
    scene.add(warehouseGroup);

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    initSharedResources();

    renderer.domElement.addEventListener('pointerdown', onDocumentPointerDown, false);
    window.addEventListener('pointermove', onDocumentPointerMove, false);
    window.addEventListener('pointerup', onDocumentPointerUp, false);
    window.addEventListener('resize', onWindowResize, false);

    function renderLoop() {
        requestAnimationFrame(renderLoop);
        if (controls) {
            controls.update();
            if (isAutoRotating) {
                warehouseGroup.rotation.y += 0.003;
            }
        }
        renderer.render(scene, camera);
    }
    renderLoop();
}

function onWindowResize() {
    const container = document.getElementById('wh3dCanvasStage');
    if (!container || !camera || !renderer) return;
    const width = container.clientWidth;
    const height = container.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

async function loadWarehouseData(showMask = false, preserveCamera = false) {
    const loader = document.getElementById('wh3dLoadingMask');
    if (showMask && loader) {
        loader.style.display = 'flex';
    }

    const safetyTimer = setTimeout(() => {
        if (loader && loader.style.display !== 'none') {
            loader.style.display = 'none';
        }
    }, 4000);

    const linia = (document.getElementById('selectLineFilter') || {}).value || 'ALL';
    const rackId = (document.getElementById('selectRackFilter') || {}).value || 'ALL';

    try {
        const url = `/api/warehouse/3d/state?linia=${encodeURIComponent(linia)}&rack_id=${encodeURIComponent(rackId)}`;
        const res = await fetch(url);
        const data = await res.json();

        if (data && data.success && data.racks && data.racks.length > 0) {
            activeWarehouseState = data;
            updateMetricsHUD(data.summary);
            buildWarehouseScene(data.racks, rackId, preserveCamera);
        } else if (rackId !== 'ALL') {
            console.warn('[Warehouse3D] Rack filter returned 0 racks, falling back to ALL');
            const fallbackUrl = `/api/warehouse/3d/state?linia=${encodeURIComponent(linia)}&rack_id=ALL`;
            const fbRes = await fetch(fallbackUrl);
            const fbData = await fbRes.json();
            if (fbData && fbData.success && fbData.racks && fbData.racks.length > 0) {
                activeWarehouseState = fbData;
                updateMetricsHUD(fbData.summary);
                buildWarehouseScene(fbData.racks, 'ALL', false);
            }
        } else {
            console.error('[Warehouse3D] API error or empty state:', data);
            if (typeof showToast === 'function') {
                showToast('Błąd pobierania danych 3D: ' + (data ? data.error : 'Brak odpowiedzi'), 'error');
            }
        }
    } catch (err) {
        console.error('[Warehouse3D] Load error:', err);
        if (typeof showToast === 'function') {
            showToast('Błąd połączenia z serwerem 3D.', 'error');
        }
    } finally {
        clearTimeout(safetyTimer);
        if (loader) loader.style.display = 'none';
    }
}

function updateMetricsHUD(summary) {
    if (!summary) return;
    document.getElementById('statTotalSlots').innerHTML = `${summary.total_slots_count} <span style="font-size: 11px; color:#64748b;">gniazd</span>`;
    document.getElementById('statOccupiedSlots').innerText = summary.total_occupied_count;
    document.getElementById('statFreeSlots').innerText = summary.total_free_count;
    const elFifo = document.getElementById('statFifoCount');
    if (elFifo) elFifo.innerText = summary.total_fifo_count !== undefined ? summary.total_fifo_count : 0;
    const elExp = document.getElementById('statExpiringCount');
    if (elExp) elExp.innerText = summary.total_expiring_count !== undefined ? summary.total_expiring_count : 0;
    document.getElementById('statBigBags').innerText = summary.total_big_bags_count;
    document.getElementById('statBags').innerText = summary.total_bags_count;
    document.getElementById('statBlocked').innerText = summary.total_blocked_count;
    document.getElementById('statOccupancyPct').innerText = `${summary.global_occupancy_percent}%`;
}

function selectRackQuick(rackId) {
    resetRelocateMode();
    document.querySelectorAll('.wh3d-chip').forEach(c => c.classList.remove('active'));
    const select = document.getElementById('selectRackFilter');
    if (select) select.value = rackId;
    
    const chips = document.querySelectorAll('.wh3d-chip');
    chips.forEach(c => {
        if (c.innerText.trim() === rackId || (rackId === 'ALL' && c.innerText.includes('HALA'))) {
            c.classList.add('active');
        }
    });
    loadWarehouseData(false, false);
}

function onRackFilterChanged(rackId) {
    selectRackQuick(rackId);
}

function onLineFilterChanged() {
    resetRelocateMode();
    loadWarehouseData(false, false);
}

function onFilterCriteriaChanged() {
    if (activeWarehouseState) {
        const rackId = document.getElementById('selectRackFilter').value;
        buildWarehouseScene(activeWarehouseState.racks, rackId, true);
    }
}

function buildWarehouseScene(racks, focusedRackId, preserveCamera = false) {
    if (!warehouseGroup) return;
    warehouseGroup.clear();
    interactiveSlotMeshes = [];
    closeInspectDrawer();

    const payloadFilter = document.getElementById('selectPayloadFilter').value;
    const searchTerm = (document.getElementById('whSearchInput').value || '').trim().toLowerCase();

    let focusCenter = new THREE.Vector3(0, 3, 0);
    let foundFocus = false;

    let filteredTotalSlots = 0;
    let filteredOccupied = 0;
    let filteredFree = 0;
    let filteredBigBags = 0;
    let filteredBags = 0;
    let filteredBlocked = 0;
    let filteredFifo = 0;
    let filteredExpiring = 0;

    racks.forEach((rack) => {
        const rx = rack.position_x;
        const rz = rack.position_z;
        const cols = rack.columns;
        const lvls = rack.levels;
        const bayW = rack.bay_width_m;
        const lvlH = rack.level_height_m;
        const depth = rack.depth_m;

        if (rack.rack_id === focusedRackId) {
            focusCenter.set(rx + (cols * bayW) / 2, (lvls * lvlH) / 2, rz);
            foundFocus = true;
        }

        const rackGroup = new THREE.Group();
        rackGroup.position.set(rx, 0, rz);

        const colGeo = new THREE.BoxGeometry(0.08, lvls * lvlH + 0.15, 0.08);
        const basePlateGeo = new THREE.BoxGeometry(0.18, 0.02, 0.18);
        const beamGeo = new THREE.BoxGeometry(cols * bayW + 0.16, 0.08, 0.06);

        for (let c = 0; c <= cols; c += 2) {
            const cx = c * bayW;

            const colF = new THREE.Mesh(colGeo, sharedMats.steel);
            colF.position.set(cx, (lvls * lvlH + 0.15) / 2, depth / 2);
            colF.castShadow = true;

            const colR = new THREE.Mesh(colGeo, sharedMats.steel);
            colR.position.set(cx, (lvls * lvlH + 0.15) / 2, -depth / 2);
            colR.castShadow = true;

            const bpF = new THREE.Mesh(basePlateGeo, sharedMats.steel);
            bpF.position.set(cx, 0.01, depth / 2);
            const bpR = new THREE.Mesh(basePlateGeo, sharedMats.steel);
            bpR.position.set(cx, 0.01, -depth / 2);

            rackGroup.add(colF, colR, bpF, bpR);

            for (let l = 0; l <= lvls; l++) {
                const by = l * lvlH;
                if (by > 0) {
                    const hBrace = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.04, depth), sharedMats.steel);
                    hBrace.position.set(cx, by, 0);
                    rackGroup.add(hBrace);
                }
                if (l < lvls) {
                    const diagLen = Math.sqrt(depth * depth + lvlH * lvlH);
                    const diagGeo = new THREE.BoxGeometry(0.03, 0.03, diagLen);
                    const dBrace = new THREE.Mesh(diagGeo, sharedMats.steel);
                    dBrace.position.set(cx, l * lvlH + lvlH / 2, 0);
                    dBrace.rotation.x = (l % 2 === 0 ? 1 : -1) * Math.atan2(lvlH, depth);
                    rackGroup.add(dBrace);
                }
            }
        }

        for (let l = 1; l <= lvls; l++) {
            const beamY = l * lvlH;
            const beamF = new THREE.Mesh(beamGeo, sharedMats.beam);
            beamF.position.set((cols * bayW) / 2, beamY, depth / 2);
            beamF.castShadow = true;

            const beamR = new THREE.Mesh(beamGeo, sharedMats.beam);
            beamR.position.set((cols * bayW) / 2, beamY, -depth / 2);
            beamR.castShadow = true;

            rackGroup.add(beamF, beamR);

            for (let c = 1; c <= cols; c++) {
                const slotX = (c - 0.5) * bayW;
                const slotCode = `${rack.rack_id}${String(c).padStart(2, '0')}${String(l).padStart(2, '0')}`;
                
                const labelTex = getBeamSlotLabelTexture(slotCode, c, l);
                const labelGeo = new THREE.PlaneGeometry(0.56, 0.16);
                const labelMat = new THREE.MeshBasicMaterial({ map: labelTex, transparent: false, depthWrite: true });
                const labelMesh = new THREE.Mesh(labelGeo, labelMat);
                labelMesh.position.set(slotX, beamY, depth / 2 + 0.032);
                rackGroup.add(labelMesh);
            }
        }

        rack.slots.forEach(slot => {
            const col = slot.column_index || slot.column;
            const lvl = slot.level_index || slot.level;
            const slotX = (col - 0.5) * bayW;
            const slotY = lvl * lvlH;
            const slotZ = 0;

            const slotPallets = (slot.pallets && slot.pallets.length > 0) ? slot.pallets : (slot.pallet ? [slot.pallet] : []);

            let matchesSearch = true;
            if (searchTerm) {
                const locMatch = slot.location_code.toLowerCase().includes(searchTerm);
                let palletMatch = false;
                if (slotPallets.length > 0) {
                    palletMatch = slotPallets.some(p => {
                        const pNr = String(p.nr_palety || p.display_id || '').toLowerCase();
                        const pProd = String(p.product_name || p.nazwa_produktu || '').toLowerCase();
                        const pBatch = String(p.batch || p.partia || '').toLowerCase();
                        return pNr.includes(searchTerm) || pProd.includes(searchTerm) || pBatch.includes(searchTerm);
                    });
                }
                matchesSearch = locMatch || palletMatch;
            }

            let matchesFilter = true;
            if (payloadFilter === 'FIFO') {
                matchesFilter = slotPallets.some(p => p.is_first_fifo);
            } else if (payloadFilter === 'EXPIRING') {
                matchesFilter = slotPallets.some(p => p.is_expiring_soon);
            } else if (payloadFilter === 'EXPIRED') {
                matchesFilter = slotPallets.some(p => p.is_expired);
            } else if (payloadFilter === 'BIG_BAG') {
                matchesFilter = (slot.payload_type === 'BIG_BAG' && slot.is_occupied);
            } else if (payloadFilter === 'BAGS') {
                matchesFilter = (slot.payload_type === 'BAGS' && slot.is_occupied);
            } else if (payloadFilter === 'BLOCKED') {
                matchesFilter = slot.is_blocked;
            } else if (payloadFilter === 'OCCUPIED') {
                matchesFilter = slot.is_occupied;
            } else if (payloadFilter === 'EMPTY') {
                matchesFilter = !slot.is_occupied;
            }

            if (!matchesSearch || !matchesFilter) {
                return;
            }

            filteredTotalSlots++;
            if (slot.is_occupied) {
                filteredOccupied++;
                if (slot.payload_type === 'BIG_BAG') filteredBigBags++;
                else if (slot.payload_type === 'BAGS') filteredBags++;
                if (slot.is_blocked) filteredBlocked++;
                if (slotPallets.some(p => p.is_first_fifo)) filteredFifo++;
                if (slotPallets.some(p => p.is_expiring_soon || p.is_expired)) filteredExpiring++;
            } else {
                filteredFree++;
            }

            const slotGroup = new THREE.Group();
            slotGroup.position.set(slotX, slotY, slotZ);
            slotGroup.userData = { slot: slot, rack: rack };

            if (slot.is_occupied) {
                const isInd = (rack.depth_m >= 1.2);
                const palletGroup = createRealisticPalletGroup(isInd);
                slotGroup.add(palletGroup);

                const p = slotPallets[0];
                const prodName = p ? (p.product_name || p.nazwa_produktu || 'SUROWIEC SYPKI') : 'SUROWIEC SYPKI';
                const batchNum = p ? (p.batch || p.partia || 'PL-2026') : 'PL-2026';
                let weightStr = (slot.payload_type === 'BIG_BAG' ? '1000 kg' : '25.0 kg');
                if (p) {
                    if (p.weight_kg !== undefined && p.weight_kg !== null && !isNaN(Number(p.weight_kg))) {
                        weightStr = `${Number(p.weight_kg).toFixed(0)} kg`;
                    } else if (p.amount !== undefined && p.amount !== null) {
                        weightStr = `${p.amount} ${p.unit || 'kg'}`;
                    }
                }

                if (slot.payload_type === 'BIG_BAG') {
                    const bigBagGroup = createRealisticBigBagGroup(prodName, batchNum, weightStr);
                    slotGroup.add(bigBagGroup);
                } else {
                    const pinwheelStack = createRealisticPinwheelStack(prodName, batchNum, weightStr);
                    slotGroup.add(pinwheelStack);
                }

                if (p && (p.is_first_fifo || p.is_expired || p.is_expiring_soon)) {
                    const badgeTex = getPalletStatusBadgeTexture(p.is_first_fifo, p.fifo_rank, p.is_expired, p.is_expiring_soon, p.days_to_exp);
                    const badgeMat = new THREE.SpriteMaterial({ map: badgeTex, depthTest: false, transparent: true });
                    const badgeSprite = new THREE.Sprite(badgeMat);
                    const spriteY = (slot.payload_type === 'BIG_BAG') ? 1.48 : 1.28;
                    badgeSprite.position.set(0, spriteY, 0);
                    badgeSprite.scale.set(0.72, 0.22, 1);
                    badgeSprite.renderOrder = 999;
                    slotGroup.add(badgeSprite);
                }

                if (slot.is_blocked) {
                    const blockBoxGeo = new THREE.BoxGeometry(1.24, 1.05, 0.84);
                    const blockMesh = new THREE.Mesh(blockBoxGeo, sharedMats.blocked);
                    blockMesh.position.set(0, 0.62, 0);
                    blockMesh.material.transparent = true;
                    blockMesh.material.opacity = 0.45;
                    slotGroup.add(blockMesh);
                }
            } else {
                const emptyMesh = new THREE.Mesh(sharedGeos.palletBase, sharedMats.emptySlot);
                emptyMesh.position.set(0, 0.07, 0);
                slotGroup.add(emptyMesh);
            }

            const hitGeo = new THREE.BoxGeometry(bayW * 0.92, lvlH * 0.90, depth * 0.95);
            const hitMat = new THREE.MeshBasicMaterial({ visible: false });
            const hitMesh = new THREE.Mesh(hitGeo, hitMat);
            hitMesh.position.set(0, (lvlH * 0.90) / 2, 0);
            hitMesh.userData = { slot: slot, rack: rack, parentGroup: slotGroup };
            slotGroup.add(hitMesh);

            interactiveSlotMeshes.push(hitMesh);
            rackGroup.add(slotGroup);
        });

        warehouseGroup.add(rackGroup);
    });

    if (searchTerm || payloadFilter !== 'ALL') {
        const occPct = filteredTotalSlots > 0 ? ((filteredOccupied / filteredTotalSlots) * 100).toFixed(1) : 0;
        updateMetricsHUD({
            total_slots_count: filteredTotalSlots,
            total_occupied_count: filteredOccupied,
            total_free_count: filteredFree,
            total_big_bags_count: filteredBigBags,
            total_bags_count: filteredBags,
            total_blocked_count: filteredBlocked,
            total_fifo_count: filteredFifo,
            total_expiring_count: filteredExpiring,
            global_occupancy_percent: occPct
        });
    } else if (activeWarehouseState && activeWarehouseState.summary) {
        updateMetricsHUD(activeWarehouseState.summary);
    }

    if (controls && !preserveCamera) {
        if (focusedRackId === 'ALL') {
            controls.target.set(0, 4, 0);
            camera.position.set(-25, 20, 32);
        } else if (foundFocus) {
            controls.target.copy(focusCenter);
            camera.position.set(focusCenter.x, focusCenter.y + 6, focusCenter.z + 12);
        }
        controls.update();
    }
}

function setCameraPreset(mode) {
    if (!camera || !controls) return;
    const target = controls.target;

    if (mode === 'ISO') {
        camera.position.set(target.x - 14, target.y + 12, target.z + 16);
    } else if (mode === 'FRONT') {
        camera.position.set(target.x, target.y + 2, target.z + 18);
    } else if (mode === 'TOP') {
        camera.position.set(target.x, target.y + 28, target.z + 0.1);
    }
    controls.update();
}

function resetCameraView() {
    const rackId = document.getElementById('selectRackFilter').value;
    if (activeWarehouseState) {
        buildWarehouseScene(activeWarehouseState.racks, rackId, false);
    }
}

function toggleAutoRotate() {
    isAutoRotating = !isAutoRotating;
    const btn = document.getElementById('btnRotateToggle');
    if (btn) {
        btn.classList.toggle('active', isAutoRotating);
    }
}

function onSearchInputChanged() {
    if (searchDebounceTimer) {
        clearTimeout(searchDebounceTimer);
    }
    searchDebounceTimer = setTimeout(() => {
        onFilterCriteriaChanged();
    }, 100);
}

function handleSearchKey(event) {
    if (event.key === 'Enter') {
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        onFilterCriteriaChanged();
    }
}

// Stage recovery in case an external partial reload ever replaces the DOM
window.addEventListener('app:partialReload', () => {
    const container = document.getElementById('wh3dCanvasStage');
    if (container && (!renderer || !container.contains(renderer.domElement))) {
        console.warn('[Warehouse3D] Re-initializing 3D stage after DOM replacement event');
        init3DStage();
        loadWarehouseData(false, true);
    }
});

