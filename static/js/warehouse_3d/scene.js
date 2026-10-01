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

function startWarehouse3D() {
    init3DStage();
    loadWarehouseData(true);
    makeDrawerDraggable();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startWarehouse3D);
} else {
    startWarehouse3D();
}

function init3DStage() {
    const container = document.getElementById('wh3dCanvasStage');
    if (!container) return false;

    if (typeof THREE === 'undefined') {
        console.warn('[Warehouse3D] THREE is not loaded yet. Scheduling retry...');
        if (!window._wh3dInitRetries) window._wh3dInitRetries = 0;
        if (window._wh3dInitRetries < 30) {
            window._wh3dInitRetries++;
            setTimeout(init3DStage, 100);
        } else {
            console.error('[Warehouse3D] Failed to initialize 3D: THREE.js library is missing.');
        }
        return false;
    }

    if (renderer && scene && warehouseGroup) {
        return true;
    }

    // Suppress global SmartPolling and partial DOM reloads on the 3D twin page
    if (typeof stopSmartPolling === 'function') {
        stopSmartPolling();
    }
    const mainEl = document.getElementById('mainContent');
    if (mainEl) {
        mainEl.setAttribute('data-no-autorefresh', 'true');
    }

    const parentCard = document.getElementById('wh3dViewportCard');
    const width = container.clientWidth || (parentCard ? parentCard.clientWidth : 0) || window.innerWidth || 1200;
    const height = container.clientHeight || (parentCard ? parentCard.clientHeight : 0) || 650;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1120);
    scene.fog = new THREE.FogExp2(0x0b1120, 0.012);

    camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 350);
    camera.position.set(-18, 14, 22);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height, true);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    container.innerHTML = '';
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    container.appendChild(renderer.domElement);

    // Auto-detect container resizing (e.g. tab switches, mode changes, window resize)
    if (window.ResizeObserver && !container._wh3dResizeObserved) {
        container._wh3dResizeObserved = true;
        const ro = new ResizeObserver(() => {
            onWindowResize();
        });
        ro.observe(container);
        if (parentCard) ro.observe(parentCard);
    }

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

    if (activeWarehouseState && activeWarehouseState.racks) {
        const rackId = (document.getElementById('selectRackFilter') || {}).value || 'ALL';
        buildWarehouseScene(activeWarehouseState.racks, rackId, false);
    }
    return true;
}

function onWindowResize() {
    const container = document.getElementById('wh3dCanvasStage');
    const parentCard = document.getElementById('wh3dViewportCard');
    if (!container || !camera || !renderer) return;
    const width = container.clientWidth || (parentCard ? parentCard.clientWidth : 0);
    const height = container.clientHeight || (parentCard ? parentCard.clientHeight : 0);
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, true);
    if (renderer.domElement) {
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
    }
}
window.onWindowResize = onWindowResize;

async function loadWarehouseData(showMask = false, preserveCamera = false, overrideOrderRef = null) {
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
    const orderSelect = document.getElementById('selectPickingOrderFilter');
    const orderRef = overrideOrderRef !== null ? overrideOrderRef : (orderSelect ? orderSelect.value : '');

    try {
        let url = `/api/warehouse/3d/state?linia=${encodeURIComponent(linia)}&rack_id=${encodeURIComponent(rackId)}`;
        if (orderRef) {
            url += `&order_ref=${encodeURIComponent(orderRef)}`;
        }
        const res = await fetch(url);
        const data = await res.json();

        const emptyOverlay = document.getElementById('wh3dEmptyOrderOverlay');
        if (emptyOverlay) emptyOverlay.style.display = 'none';

        if (data && data.success && data.racks && data.racks.length > 0) {
            activeWarehouseState = data;
            updateMetricsHUD(data.summary);

            // Dynamic visibility of rack chips: only show tabs for racks that have items from the order!
            const activeRackIds = new Set(data.racks.map(r => r.rack_id));
            document.querySelectorAll('.wh3d-rack-chips .wh3d-chip').forEach(chip => {
                const rId = chip.innerText.trim();
                if (rId.startsWith('R')) {
                    chip.style.display = activeRackIds.has(rId) ? 'inline-flex' : 'none';
                } else {
                    chip.style.display = 'inline-flex';
                }
            });

            buildWarehouseScene(data.racks, rackId, preserveCamera);
        } else if (orderRef && data && data.success && (!data.racks || data.racks.length === 0)) {
            // Picking order is fully completed / has 0 pending pallets to pick on racks
            activeWarehouseState = data;
            updateMetricsHUD(data.summary || {
                total_slots_count: 0,
                total_occupied_count: 0,
                total_free_count: 0,
                total_fifo_count: 0,
                total_expiring_count: 0,
                total_big_bags_count: 0,
                total_bags_count: 0,
                total_blocked_count: 0,
                global_occupancy_percent: 0
            });

            // Hide individual rack chips since no racks have pending items for this order
            document.querySelectorAll('.wh3d-rack-chips .wh3d-chip').forEach(chip => {
                const rId = chip.innerText.trim();
                if (rId.startsWith('R')) {
                    chip.style.display = 'none';
                }
            });

            // Clear 3D racks & pallets from scene so stale pallets NEVER remain
            buildWarehouseScene([], 'ALL', false);

            if (emptyOverlay) {
                const titleEl = document.getElementById('wh3dEmptyOrderTitle');
                const msgEl = document.getElementById('wh3dEmptyOrderMsg');
                if (titleEl) titleEl.innerText = `Zlecenie ${orderRef} jest w 100% zrealizowane`;
                if (msgEl) msgEl.innerText = `Wszystkie palety z tego zlecenia zostały już skompletowane i pobrane z regałów magazynowych na strefę MP01 / produkcję. Na regałach nie ma oczekujących pozycji do zdjęcia.`;
                emptyOverlay.style.display = 'flex';
            }
        } else if (rackId !== 'ALL') {
            console.warn('[Warehouse3D] Rack filter returned 0 racks, falling back to ALL');
            let fallbackUrl = `/api/warehouse/3d/state?linia=${encodeURIComponent(linia)}&rack_id=ALL`;
            if (orderRef) {
                fallbackUrl += `&order_ref=${encodeURIComponent(orderRef)}`;
            }
            const fbRes = await fetch(fallbackUrl);
            const fbData = await fbRes.json();
            if (fbData && fbData.success && fbData.racks && fbData.racks.length > 0) {
                activeWarehouseState = fbData;
                updateMetricsHUD(fbData.summary);
                buildWarehouseScene(fbData.racks, 'ALL', false);
            } else {
                buildWarehouseScene([], 'ALL', false);
                if (orderRef && emptyOverlay) emptyOverlay.style.display = 'flex';
            }
        } else {
            console.error('[Warehouse3D] API empty state:', data);
            buildWarehouseScene([], 'ALL', false);
            if (orderRef && emptyOverlay) {
                emptyOverlay.style.display = 'flex';
            } else if (typeof showToast === 'function') {
                showToast('Brak danych magazynowych dla wybranego filtru.', 'info');
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

function selectRackQuick(rackId, overrideOrderRef = null) {
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
    loadWarehouseData(false, false, overrideOrderRef);
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
    if (!warehouseGroup) {
        const ready = init3DStage();
        if (!ready || !warehouseGroup) {
            console.warn('[Warehouse3D] warehouseGroup not ready, deferring buildWarehouseScene...');
            setTimeout(() => {
                if (activeWarehouseState && activeWarehouseState.racks) {
                    buildWarehouseScene(activeWarehouseState.racks, focusedRackId, preserveCamera);
                }
            }, 120);
            return;
        }
    }
    warehouseGroup.clear();
    interactiveSlotMeshes = [];
    closeInspectDrawer();

    const payloadFilter = document.getElementById('selectPayloadFilter').value;
    const searchTerm = (document.getElementById('whSearchInput').value || '').trim().toLowerCase();
    const orderSelect = document.getElementById('selectPickingOrderFilter');
    const isOrderFilterActive = Boolean(orderSelect && orderSelect.value && orderSelect.value !== '');

    // Filter out racks with 0 items when viewing entire hall or an active picking order
    let racksToRender = racks;
    if (focusedRackId === 'ALL' || isOrderFilterActive) {
        const nonEmptyRacks = racks.filter(rack => {
            if (focusedRackId !== 'ALL' && rack.rack_id === focusedRackId && !isOrderFilterActive) {
                return true; // user explicitly clicked a single rack tab in general inventory mode
            }
            const occ = (rack.occupied_slots !== undefined && rack.occupied_slots !== null)
                ? rack.occupied_slots
                : (rack.slots ? rack.slots.filter(s => s.is_occupied || (s.pallets && s.pallets.length > 0)).length : 0);
            return occ > 0;
        });

        if (nonEmptyRacks.length > 0) {
            racksToRender = nonEmptyRacks;
        }
    } else if (focusedRackId && focusedRackId !== 'ALL') {
        const single = racks.filter(r => r.rack_id === focusedRackId);
        if (single.length > 0) {
            racksToRender = single;
        }
    }

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

    racksToRender.forEach((rack) => {
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

        // ----------------------------------------------------
        // Prominent 3D Large Overhead Rack Sign (Smart billboard)
        // ----------------------------------------------------
        const rackOccCount = (rack.occupied_slots !== undefined && rack.occupied_slots !== null)
            ? rack.occupied_slots
            : (rack.slots ? rack.slots.filter(s => s.is_occupied || (s.pallets && s.pallets.length > 0)).length : 0);

        if (typeof getLargeRackHeaderTexture === 'function') {
            const signTex = getLargeRackHeaderTexture(
                rack.rack_id, 
                rackOccCount, 
                rack.total_slots || (cols * lvls), 
                isOrderFilterActive
            );
            
            const signGroup = new THREE.Group();
            const signCenterX = (cols * bayW) / 2;
            const signTopY = lvls * lvlH + 1.25;
            signGroup.position.set(signCenterX, signTopY, 0);

            // Two support uprights down to top beam
            const poleGeo = new THREE.CylinderGeometry(0.025, 0.025, 1.2, 8);
            const poleMat = sharedMats.steel || new THREE.MeshStandardMaterial({ color: 0x64748b, metalness: 0.8, roughness: 0.2 });
            
            const poleLeft = new THREE.Mesh(poleGeo, poleMat);
            poleLeft.position.set(-1.4, -0.6, 0);
            signGroup.add(poleLeft);

            const poleRight = new THREE.Mesh(poleGeo, poleMat);
            poleRight.position.set(1.4, -0.6, 0);
            signGroup.add(poleRight);

            // High-visibility Sprite billboard that always faces camera
            const signSpriteMat = new THREE.SpriteMaterial({ 
                map: signTex, 
                depthTest: false, 
                transparent: true 
            });
            const signSprite = new THREE.Sprite(signSpriteMat);
            signSprite.scale.set(4.6, 1.44, 1);
            signSprite.renderOrder = 999;
            signGroup.add(signSprite);

            // Clickable hit mesh for quick jumping to this rack
            const signHitGeo = new THREE.BoxGeometry(4.8, 1.5, 0.8);
            const signHitMat = new THREE.MeshBasicMaterial({ visible: false });
            const signHitMesh = new THREE.Mesh(signHitGeo, signHitMat);
            signHitMesh.userData = { rackId: rack.rack_id, isRackHeader: true };
            signGroup.add(signHitMesh);
            interactiveSlotMeshes.push(signHitMesh);

            rackGroup.add(signGroup);
        }

        const isShelving = Boolean(rack.is_shelving || rack.rack_type === 'SHELVING' || rack.rack_id === 'R09');

        if (isShelving) {
            // Shelving rack structure (Regał Półkowy - smukłe profile, lite półki na każdym poziomie)
            const shelfPostGeo = new THREE.BoxGeometry(0.045, lvls * lvlH + 0.05, 0.045);
            const shelfPostMat = sharedMats.shelfSteel || sharedMats.steel;

            for (let c = 0; c <= cols; c++) {
                const cx = c * bayW;
                const postF = new THREE.Mesh(shelfPostGeo, shelfPostMat);
                postF.position.set(cx, (lvls * lvlH + 0.05) / 2, depth / 2);
                postF.castShadow = true;

                const postR = new THREE.Mesh(shelfPostGeo, shelfPostMat);
                postR.position.set(cx, (lvls * lvlH + 0.05) / 2, -depth / 2);
                postR.castShadow = true;

                rackGroup.add(postF, postR);

                // Side ties between front and rear uprights
                for (let l = 1; l <= lvls; l++) {
                    const tieGeo = new THREE.BoxGeometry(0.03, 0.03, depth);
                    const tieMesh = new THREE.Mesh(tieGeo, shelfPostMat);
                    tieMesh.position.set(cx, (l - 1) * lvlH + 0.015, 0);
                    rackGroup.add(tieMesh);
                }
            }

            // Solid shelves (blaty półkowe) on every level 1..lvls
            for (let l = 1; l <= lvls; l++) {
                const shelfY = (l - 1) * lvlH;
                for (let c = 1; c <= cols; c++) {
                    const slotX = (c - 0.5) * bayW;
                    const slotCode = `${rack.rack_id}${String(c).padStart(2, '0')}${String(l).padStart(2, '0')}`;

                    // Solid galvanized/painted shelf surface plate
                    const shelfDeckGeo = new THREE.BoxGeometry(bayW * 0.98, 0.022, depth * 0.96);
                    const shelfDeck = new THREE.Mesh(shelfDeckGeo, sharedMats.shelfPanel);
                    shelfDeck.position.set(slotX, shelfY + 0.011, 0);
                    shelfDeck.receiveShadow = true;
                    rackGroup.add(shelfDeck);

                    // Front shelf edge with label strip
                    const labelTex = getBeamSlotLabelTexture(slotCode, c, l);
                    const labelGeo = new THREE.PlaneGeometry(Math.min(0.50, bayW * 0.44), 0.12);
                    const labelMat = new THREE.MeshBasicMaterial({ map: labelTex, transparent: false, depthWrite: true });
                    const labelMesh = new THREE.Mesh(labelGeo, labelMat);
                    labelMesh.position.set(slotX, shelfY + 0.011, depth / 2 + 0.015);
                    rackGroup.add(labelMesh);
                }
            }
        } else {
            // High-bay pallet racking (Regały wysokiego składowania palet)
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

            // 1. Beams and labels for elevated levels (Level 2, 3, ..., lvls)
            for (let l = 2; l <= lvls; l++) {
                const beamY = (l - 1) * lvlH;
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

            // 2. Floor location labels for Level 1 (Poziom 1 na posadzce / podłodze pod paletami)
            for (let c = 1; c <= cols; c++) {
                const slotX = (c - 0.5) * bayW;
                const slotCode = `${rack.rack_id}${String(c).padStart(2, '0')}01`;
                
                const labelTex1 = getBeamSlotLabelTexture(slotCode, c, 1);
                const floorLabelGeo = new THREE.PlaneGeometry(0.56, 0.16);
                const floorLabelMat = new THREE.MeshBasicMaterial({ map: labelTex1, transparent: false, depthWrite: true });
                const floorLabelMesh = new THREE.Mesh(floorLabelGeo, floorLabelMat);
                floorLabelMesh.position.set(slotX, 0.015, depth / 2 + 0.12);
                floorLabelMesh.rotation.x = -Math.PI / 2;
                rackGroup.add(floorLabelMesh);
            }
        }

        rack.slots.forEach(slot => {
            const col = slot.column_index || slot.column;
            const lvl = slot.level_index || slot.level;
            const slotX = (col - 0.5) * bayW;
            // Levels count from floor up: Level 1 on floor (0m), Level 2 on beam 1 (lvlH), Level 3 on beam 2 (2*lvlH), etc.
            const slotY = (lvl - 1) * lvlH;
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
            slotGroup.userData = { slot: slot, rack: rack, isShelving: isShelving };

            if (slot.is_occupied) {
                if (isShelving) {
                    // Render realistic multi-item assortment on shelf
                    const shelfAssortment = createRealisticShelfAssortmentGroup(slotPallets, bayW, depth, lvlH);
                    slotGroup.add(shelfAssortment);

                    const pStatus = slotPallets.find(p => p.is_picking_target || p.is_first_fifo || p.is_expired || p.is_expiring_soon);
                    if (pStatus) {
                        const badgeTex = getPalletStatusBadgeTexture(
                            pStatus.is_first_fifo, 
                            pStatus.fifo_rank, 
                            pStatus.is_expired, 
                            pStatus.is_expiring_soon, 
                            pStatus.days_to_exp,
                            Boolean(pStatus.is_picking_target),
                            pStatus.order_ref || ''
                        );
                        const badgeMat = new THREE.SpriteMaterial({ map: badgeTex, depthTest: false, transparent: true });
                        const badgeSprite = new THREE.Sprite(badgeMat);
                        const spriteY = (slotPallets.length > 1) ? Math.min(lvlH * 0.95, 0.72) : Math.min(lvlH * 0.78, 0.55);
                        badgeSprite.position.set(0, spriteY, 0);
                        badgeSprite.scale.set(0.72, 0.20, 1);
                        badgeSprite.renderOrder = 999;
                        slotGroup.add(badgeSprite);
                    }

                    if (slot.is_blocked) {
                        const blockBoxGeo = new THREE.BoxGeometry(bayW * 0.90, lvlH * 0.65, depth * 0.85);
                        const blockMesh = new THREE.Mesh(blockBoxGeo, sharedMats.blocked);
                        blockMesh.position.set(0, (lvlH * 0.65) / 2, 0);
                        blockMesh.material.transparent = true;
                        blockMesh.material.opacity = 0.40;
                        slotGroup.add(blockMesh);
                    }
                } else {
                    const isInd = (rack.depth_m >= 1.2);
                    
                    slotPallets.forEach((p, pIdx) => {
                        const yOffset = pIdx * 0.85;
                        const subGroup = new THREE.Group();
                        subGroup.position.set(0, yOffset, 0);

                        const palletGroup = createRealisticPalletGroup(isInd);
                        subGroup.add(palletGroup);

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
                            subGroup.add(bigBagGroup);
                        } else {
                            const pinwheelStack = createRealisticPinwheelStack(prodName, batchNum, weightStr);
                            subGroup.add(pinwheelStack);
                        }

                        slotGroup.add(subGroup);
                    });

                    // Multi-pallet badge if stacked (e.g. 2 Hydro pallets on level 1)
                    if (slotPallets.length > 1) {
                        const multiTex = getShelfMultiItemBadgeTexture(slotPallets.length);
                        const multiMat = new THREE.SpriteMaterial({ map: multiTex, depthTest: false, transparent: true });
                        const multiSprite = new THREE.Sprite(multiMat);
                        const spriteY = (slotPallets.length * 0.85) + 0.65;
                        multiSprite.position.set(0, spriteY, 0);
                        multiSprite.scale.set(0.70, 0.20, 1);
                        multiSprite.renderOrder = 998;
                        slotGroup.add(multiSprite);
                    }

                    const p = slotPallets[0];
                    if (p && (p.is_picking_target || p.is_first_fifo || p.is_expired || p.is_expiring_soon)) {
                        const badgeTex = getPalletStatusBadgeTexture(
                            p.is_first_fifo, 
                            p.fifo_rank, 
                            p.is_expired, 
                            p.is_expiring_soon, 
                            p.days_to_exp,
                            Boolean(p.is_picking_target),
                            p.order_ref || ''
                        );
                        const badgeMat = new THREE.SpriteMaterial({ map: badgeTex, depthTest: false, transparent: true });
                        const badgeSprite = new THREE.Sprite(badgeMat);
                        const baseSpriteY = (slot.payload_type === 'BIG_BAG') ? 1.48 : 1.28;
                        const spriteY = (slotPallets.length > 1) ? baseSpriteY + 0.85 : baseSpriteY;
                        badgeSprite.position.set(0, spriteY, 0);
                        badgeSprite.scale.set(0.76, 0.23, 1);
                        badgeSprite.renderOrder = 999;
                        slotGroup.add(badgeSprite);

                        if (p.is_picking_target) {
                            // High-visibility downwards pointing target beacon cone
                            const coneGeo = new THREE.ConeGeometry(0.16, 0.36, 4);
                            const coneMat = new THREE.MeshBasicMaterial({ 
                                color: (p.fifo_rank === 1) ? 0xf59e0b : 0x38bdf8 
                            });
                            const coneMesh = new THREE.Mesh(coneGeo, coneMat);
                            coneMesh.rotation.x = Math.PI;
                            coneMesh.position.set(0, spriteY + 0.32, 0);
                            slotGroup.add(coneMesh);
                        }
                    }

                    if (slot.is_blocked) {
                        const blockBoxGeo = new THREE.BoxGeometry(1.24, slotPallets.length > 1 ? 1.75 : 1.05, 0.84);
                        const blockMesh = new THREE.Mesh(blockBoxGeo, sharedMats.blocked);
                        blockMesh.position.set(0, slotPallets.length > 1 ? 0.95 : 0.62, 0);
                        blockMesh.material.transparent = true;
                        blockMesh.material.opacity = 0.45;
                        slotGroup.add(blockMesh);
                    }
                }
            } else {
                if (isShelving) {
                    const emptyShelfMesh = new THREE.Mesh(new THREE.BoxGeometry(bayW * 0.88, 0.005, depth * 0.85), sharedMats.emptySlot);
                    emptyShelfMesh.position.set(0, 0.015, 0);
                    slotGroup.add(emptyShelfMesh);
                } else {
                    const emptyMesh = new THREE.Mesh(sharedGeos.palletBase, sharedMats.emptySlot);
                    emptyMesh.position.set(0, 0.07, 0);
                    slotGroup.add(emptyMesh);
                }
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
            let minX = Infinity, maxX = -Infinity;
            let minZ = Infinity, maxZ = -Infinity;
            let maxTopY = 4;

            racksToRender.forEach(r => {
                const rx = r.position_x;
                const rz = r.position_z;
                const rw = r.columns * r.bay_width_m;
                const rh = r.levels * r.level_height_m;
                minX = Math.min(minX, rx);
                maxX = Math.max(maxX, rx + rw);
                minZ = Math.min(minZ, rz - r.depth_m * 2);
                maxZ = Math.max(maxZ, rz + r.depth_m * 2);
                maxTopY = Math.max(maxTopY, rh);
            });

            if (minX !== Infinity && isFinite(minX)) {
                const midX = (minX + maxX) / 2;
                const midZ = (minZ + maxZ) / 2;
                const spanX = Math.max(maxX - minX, 12);
                const spanZ = Math.max(maxZ - minZ, 12);
                const maxSpan = Math.max(spanX, spanZ);

                controls.target.set(midX, maxTopY * 0.45, midZ);
                camera.position.set(midX - maxSpan * 0.45, maxTopY + maxSpan * 0.85, midZ + maxSpan * 1.15);
            } else {
                controls.target.set(0, 4, 0);
                camera.position.set(-25, 20, 32);
            }
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

