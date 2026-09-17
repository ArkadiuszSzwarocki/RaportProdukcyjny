(function() {
    let activeFilter = 'ALL';
    let activeErrFilter = 'ALL';
    let isPaused = false;
    let currentConfig = {
        total_layers: 13,
        full_layers: 12,
        bags_per_layer: 4,
        top_layer_bags: 2,
        bag_weight_kg: 25.0,
        total_bags: 50
    };
    let availablePresets = [];

    const terminalEl = document.getElementById('mqttTerminalLogs');
    const errorsContainer = document.getElementById('machineErrorsContainer');
    const stackContainer = document.getElementById('stackLayersContainer');

    // ─────────────────────────────────────────────────────────────
    // THEME MANAGEMENT (LIGHT / DARK)
    // ─────────────────────────────────────────────────────────────
    function initTheme() {
        const savedTheme = localStorage.getItem('maszyny_theme') || 'dark';
        applyTheme(savedTheme);
    }

    function applyTheme(theme) {
        const body = document.body;
        const icon = document.getElementById('themeIcon');
        const text = document.getElementById('themeText');
        
        if (theme === 'dark') {
            body.classList.add('dark-theme');
            if (icon) icon.innerText = 'dark_mode';
            if (text) text.innerText = 'CIEMNY MOTYW';
            if (scene3d) scene3d.background = new THREE.Color(0x0b1120);
            if (sceneWrapper3d) sceneWrapper3d.background = new THREE.Color(0x0b1120);
        } else {
            body.classList.remove('dark-theme');
            if (icon) icon.innerText = 'light_mode';
            if (text) text.innerText = 'JASNY MOTYW';
            // Sleek dark tech background for 3D viewports to avoid eye glare
            if (scene3d) scene3d.background = new THREE.Color(0x0f172a);
            if (sceneWrapper3d) sceneWrapper3d.background = new THREE.Color(0x0f172a);
        }
        localStorage.setItem('maszyny_theme', theme);
    }

    window.toggleTheme = function() {
        const isDark = document.body.classList.contains('dark-theme');
        applyTheme(isDark ? 'light' : 'dark');
    };

    // ─────────────────────────────────────────────────────────────
    // 3D DIGITAL TWIN PALLET ENGINE (THREE.JS - HIGH-LEVEL PALLETIZER)
    // ─────────────────────────────────────────────────────────────
    let scene3d, camera3d, renderer3d, controls3d;
    let palletGroup3d, bagsGroup3d, machineFrameGroup3d, upperPlateLeft3d, upperPlateRight3d, upperBagsGroup3d;
    let palletElevatorPiston3d;
    let autoRotate3d = false;
    let targetPalletY = 1.48; // High-level palletizer: empty pallet starts elevated directly under formation plates (Y: 1.48m)
    let currentPalletY = 1.48;
    let targetPalletX = 0; // Horizontal conveyor outfeed position (X: 0 = elevator, X: 2.45 = outfeed to wrapper)
    let currentPalletX = 0;
    let rollerMeshes3d = [];
    let lastPalletizer3dState = '';
    let current3dLayer = 0;
    let current3dBag = 0;
    let turnerClampGroup3d = null;
    let isTurnerActiveAnim = false;
    let isPusherActiveAnim = false;
    let isTransferActiveAnim = false;
    let baggerJawLeft3d = null, baggerJawRight3d = null;
    let isBaggerJawsClosedAnim = false;
    let baggerBeaconGreen3d = null;

    function init3dScene() {
        const container = document.getElementById('pallet3dCanvasContainer');
        if (!container || typeof THREE === 'undefined') return;

        const width = container.clientWidth || 360;
        const height = container.clientHeight || 230;

        // Scene
        scene3d = new THREE.Scene();
        scene3d.background = new THREE.Color(0x0b1120);

        // Camera
        camera3d = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
        camera3d.position.set(2.2, 3.8, 6.2);

        // Renderer
        renderer3d = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer3d.setSize(width, height);
        renderer3d.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer3d.shadowMap.enabled = true;
        renderer3d.shadowMap.type = THREE.PCFSoftShadowMap;

        container.innerHTML = '';
        container.appendChild(renderer3d.domElement);

        // Orbit Controls (Pełna swoboda obrotu i przesuwania sceny)
        if (typeof THREE.OrbitControls !== 'undefined') {
            controls3d = new THREE.OrbitControls(camera3d, renderer3d.domElement);
            controls3d.enableDamping = true;
            controls3d.dampingFactor = 0.05;
            controls3d.maxPolarAngle = Math.PI / 2 + 0.05;
            controls3d.minDistance = 1.0;
            controls3d.maxDistance = 16.0;
            controls3d.enablePan = true;
            controls3d.screenSpacePanning = true; // Naturalne przesuwanie w płaszczyźnie ekranu (lewo/prawo/góra/dół)
            controls3d.panSpeed = 1.2;
            controls3d.mouseButtons = {
                LEFT: THREE.MOUSE.ROTATE,
                MIDDLE: THREE.MOUSE.DOLLY,
                RIGHT: THREE.MOUSE.PAN
            };
            controls3d.touches = {
                ONE: THREE.TOUCH.ROTATE,
                TWO: THREE.TOUCH.DOLLY_PAN
            };
            controls3d.target.set(-1.8, 1.0, 0); // Oś obrotu wyśrodkowana na całą linię technologiczną (od pakowaczki po odbiór)
        }

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
        scene3d.add(ambientLight);

        const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
        dirLight.position.set(4, 9, 4);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 1024;
        dirLight.shadow.mapSize.height = 1024;
        scene3d.add(dirLight);

        const blueFillLight = new THREE.DirectionalLight(0x0284c7, 0.35);
        blueFillLight.position.set(-4, 3, -4);
        scene3d.add(blueFillLight);

        // Shadow Plane (Expanded to cover extended floor roller track, infeed span and bagger)
        const shadowPlaneGeo = new THREE.PlaneGeometry(14, 8);
        const shadowPlaneMat = new THREE.ShadowMaterial({ opacity: 0.15 });
        const shadowPlane = new THREE.Mesh(shadowPlaneGeo, shadowPlaneMat);
        shadowPlane.rotation.x = -Math.PI / 2;
        shadowPlane.position.set(-1.80, -0.01, 0);
        shadowPlane.receiveShadow = true;
        scene3d.add(shadowPlane);

        // Groups
        palletGroup3d = new THREE.Group();
        bagsGroup3d = new THREE.Group();
        machineFrameGroup3d = new THREE.Group();
        upperBagsGroup3d = new THREE.Group();

        scene3d.add(machineFrameGroup3d);
        scene3d.add(palletGroup3d);
        scene3d.add(bagsGroup3d);
        scene3d.add(upperBagsGroup3d);

        build3dPalletizerMachineFrame();
        build3dEuroPallet();
        rebuild3dBags(current3dLayer, current3dBag, false, 0, null, null);

        // Animation Loop
        function animate3d() {
            requestAnimationFrame(animate3d);

            // Krok 0: Animated Bagger Sealing Jaws (szczęki zgrzewające worki wg MQTT szczekiZamkniete)
            if (baggerJawLeft3d && baggerJawRight3d) {
                const targetLeftX = isBaggerJawsClosedAnim ? -6.22 : -6.32;
                const targetRightX = isBaggerJawsClosedAnim ? -6.18 : -6.08;
                baggerJawLeft3d.position.x += (targetLeftX - baggerJawLeft3d.position.x) * 0.18;
                baggerJawRight3d.position.x += (targetRightX - baggerJawRight3d.position.x) * 0.18;
            }

            // Smooth vertical elevator movement (winda paletyzatora)
            currentPalletY += (targetPalletY - currentPalletY) * 0.08;
            if (palletGroup3d) {
                palletGroup3d.position.y = currentPalletY;
            }
            if (bagsGroup3d) {
                bagsGroup3d.position.y = currentPalletY;
            }
            if (palletElevatorPiston3d) {
                // Telescopic lift cylinder extending from floor (0.05m) to elevator carriage
                palletElevatorPiston3d.scale.y = Math.max(0.04, currentPalletY / 1.48);
            }

            // Smooth horizontal outfeed conveyor movement (płynny wyjazd palety wzdłuż rolotoku)
            if (Math.abs(targetPalletX - currentPalletX) > 0.001) {
                const diffX = targetPalletX - currentPalletX;
                currentPalletX += diffX * 0.04;
                if (palletGroup3d) palletGroup3d.position.x = currentPalletX;
                if (bagsGroup3d) bagsGroup3d.position.x = currentPalletX;

                // Rotate steel rollers along conveyor bed while pallet is rolling
                if (rollerMeshes3d && rollerMeshes3d.length > 0) {
                    const rotDelta = (diffX > 0 ? 0.06 : -0.06);
                    rollerMeshes3d.forEach(r => { r.rotation.z += rotDelta; });
                }
            }

            // Krok 2: Animated Bag Turner Clamp rotation (obracakPraca wg MQTT_PROCESS_FLOW.md)
            if (turnerClampGroup3d && isTurnerActiveAnim) {
                turnerClampGroup3d.rotation.y += 0.08;
            } else if (turnerClampGroup3d) {
                turnerClampGroup3d.rotation.y = 0;
            }

            // Krok 3: Animated Pusher paddle movement (popychaczPraca wg MQTT_PROCESS_FLOW.md)
            if (pusherPaddleMesh3d && isPusherActiveAnim) {
                pusherPaddleMesh3d.position.z = -0.94 + Math.sin(Date.now() * 0.007) * 0.38;
            }

            // Krok 6: Outfeed transfer rollers rotation when transfer signal is active
            if (isTransferActiveAnim && rollerMeshes3d && rollerMeshes3d.length > 0) {
                rollerMeshes3d.forEach(r => { r.rotation.z += 0.06; });
            }

            if (controls3d) {
                if (autoRotate3d) {
                    palletGroup3d.rotation.y += 0.004;
                    bagsGroup3d.rotation.y += 0.004;
                }
                controls3d.update();
            }
            renderer3d.render(scene3d, camera3d);
        }
        animate3d();

        window.addEventListener('resize', on3dWindowResize);
    }

    function on3dWindowResize() {
        const container = document.getElementById('pallet3dCanvasContainer');
        if (!container || !camera3d || !renderer3d) return;
        const width = container.clientWidth;
        const height = container.clientHeight;
        camera3d.aspect = width / height;
        camera3d.updateProjectionMatrix();
        renderer3d.setSize(width, height);
    }

    // ─────────────────────────────────────────────────────────────
    // PALLETIZER 3D CAMERA & PAN NAVIGATION CONTROLS
    // ─────────────────────────────────────────────────────────────
    let is3dPanMode = false;

    window.toggle3dPanMode = function() {
        if (!controls3d) return;
        is3dPanMode = !is3dPanMode;
        const btn = document.getElementById('btnTogglePan');
        if (is3dPanMode) {
            controls3d.mouseButtons.LEFT = THREE.MOUSE.PAN;
            controls3d.mouseButtons.RIGHT = THREE.MOUSE.ROTATE;
            if (btn) {
                btn.classList.add('active');
                btn.innerHTML = '<span class="material-icons">pan_tool</span> PRZESUŃ (LPM)';
            }
        } else {
            controls3d.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
            controls3d.mouseButtons.RIGHT = THREE.MOUSE.PAN;
            if (btn) {
                btn.classList.remove('active');
                btn.innerHTML = '<span class="material-icons">pan_tool</span> PRZESUŃ';
            }
        }
    };

    window.pan3dCamera = function(deltaX) {
        if (!controls3d || !camera3d) return;
        controls3d.target.x += deltaX;
        camera3d.position.x += deltaX;
        controls3d.update();
    };

    window.toggle3dAutoRotate = function() {
        autoRotate3d = !autoRotate3d;
        const btn = document.getElementById('btnAutoRotate');
        if (btn) btn.classList.toggle('active', autoRotate3d);
    };

    window.set3dCameraView = function(view) {
        if (!camera3d || !controls3d) return;
        autoRotate3d = false;
        const btn = document.getElementById('btnAutoRotate');
        if (btn) btn.classList.remove('active');

        if (view === 'iso') {
            camera3d.position.set(2.2, 3.8, 6.2);
            controls3d.target.set(-1.8, 1.0, 0);
        } else if (view === 'top') {
            camera3d.position.set(-1.8, 8.5, 0.01);
            controls3d.target.set(-1.8, 1.0, 0);
        } else if (view === 'bagger') {
            camera3d.position.set(-4.2, 2.2, 2.8);
            controls3d.target.set(-5.6, 1.1, -0.78);
        }
        controls3d.update();
    };

    window.reset3dCamera = function() {
        window.set3dCameraView('iso');
        if (palletGroup3d) palletGroup3d.rotation.y = 0;
        if (bagsGroup3d) bagsGroup3d.rotation.y = 0;
    };

    // Creates an authentic, detailed Euro / Industrial wooden pallet with boards, stringers, blocks, and skids
    function create3dFullEuroPalletMesh(isIndustrial, woodMat) {
        const pallet = new THREE.Group();
        const pW = isIndustrial ? 1.0 : 0.8;
        const pL = 1.2;

        const blockPositionsX = [-0.50, 0, 0.50];
        const blockPositionsZ = isIndustrial ? [-0.425, 0, 0.425] : [-0.325, 0, 0.325];

        // 1. Bottom Runner Skids (3 boards running along X, length 1.20m, thickness 22mm)
        const botSkidGeo = new THREE.BoxGeometry(pL, 0.022, 0.145);
        for (let bz of blockPositionsZ) {
            const skid = new THREE.Mesh(botSkidGeo, woodMat);
            skid.position.set(0, 0.011, bz);
            skid.castShadow = true;
            skid.receiveShadow = true;
            pallet.add(skid);
        }

        // 2. Spacer Blocks (9 blocks 145x78x145mm creating realistic forklift slots)
        const blockGeo = new THREE.BoxGeometry(0.145, 0.078, 0.145);
        for (let bx of blockPositionsX) {
            for (let bz of blockPositionsZ) {
                const block = new THREE.Mesh(blockGeo, woodMat);
                block.position.set(bx, 0.061, bz);
                block.castShadow = true;
                block.receiveShadow = true;
                pallet.add(block);
            }
        }

        // 3. Cross Stringer Boards (3 boards running across Z, length pW, thickness 22mm)
        const crossGeo = new THREE.BoxGeometry(0.145, 0.022, pW);
        for (let bx of blockPositionsX) {
            const cross = new THREE.Mesh(crossGeo, woodMat);
            cross.position.set(bx, 0.111, 0);
            cross.castShadow = true;
            cross.receiveShadow = true;
            pallet.add(cross);
        }

        // 4. Top Deck Boards (5 for EURO or 7 for Industrial, running along X, length 1.20m)
        if (isIndustrial) {
            const topBoardWidths = [0.145, 0.100, 0.100, 0.145, 0.100, 0.100, 0.145];
            const topBoardZ = [-0.4275, -0.285, -0.1425, 0, 0.1425, 0.285, 0.4275];
            for (let i = 0; i < 7; i++) {
                const boardGeo = new THREE.BoxGeometry(pL, 0.022, topBoardWidths[i]);
                const board = new THREE.Mesh(boardGeo, woodMat);
                board.position.set(0, 0.133, topBoardZ[i]);
                board.castShadow = true;
                board.receiveShadow = true;
                pallet.add(board);
            }
        } else {
            const topBoardWidths = [0.145, 0.100, 0.145, 0.100, 0.145];
            const topBoardZ = [-0.3275, -0.175, 0, 0.175, 0.3275];
            for (let i = 0; i < 5; i++) {
                const boardGeo = new THREE.BoxGeometry(pL, 0.022, topBoardWidths[i]);
                const board = new THREE.Mesh(boardGeo, woodMat);
                board.position.set(0, 0.133, topBoardZ[i]);
                board.castShadow = true;
                board.receiveShadow = true;
                pallet.add(board);
            }
        }

        return pallet;
    }

    // Build Realistic Upper Infeed Conveyor, Bag Turner, Row Pusher, and Split Formation Table
    let pusherPaddleMesh3d = null;

    function build3dPalletizerMachineFrame() {
        if (!machineFrameGroup3d) return;
        machineFrameGroup3d.clear();

        const steelMat = new THREE.MeshStandardMaterial({
            color: 0x334155,
            roughness: 0.5,
            metalness: 0.7
        });
        const yellowMat = new THREE.MeshStandardMaterial({
            color: 0xf59e0b,
            roughness: 0.4,
            metalness: 0.3
        });
        const beltMat = new THREE.MeshStandardMaterial({
            color: 0x1e293b,
            roughness: 0.8,
            metalness: 0.1
        });
        const chromeMat = new THREE.MeshStandardMaterial({
            color: 0xe2e8f0,
            roughness: 0.2,
            metalness: 0.85
        });

        const infeedZ = -0.78;
        const beltW = 0.60;
        const halfRail = 0.31; // Guide rail offset from center (clear internal width 0.62m)

        // 4 Vertical Heavy Duty Columns (Enclosing infeed staging belt at Z: -0.78 and split plates at Z: 0.18)
        const colGeo = new THREE.BoxGeometry(0.08, 2.3, 0.08);
        const colPos = [
            [-0.65, 1.15, -0.98],
            [0.65, 1.15, -0.98],
            [-0.65, 1.15, 0.65],
            [0.65, 1.15, 0.65]
        ];
        colPos.forEach(p => {
            const col = new THREE.Mesh(colGeo, steelMat);
            col.position.set(p[0], p[1], p[2]);
            col.castShadow = true;
            machineFrameGroup3d.add(col);
        });

        // Upper Perimeter Top Beams (Y: 2.25)
        const beamXGeo = new THREE.BoxGeometry(1.38, 0.08, 0.08);
        const beamZGeo = new THREE.BoxGeometry(0.08, 0.08, 1.71);

        const b1 = new THREE.Mesh(beamXGeo, steelMat); b1.position.set(0, 2.25, -0.98);
        const b2 = new THREE.Mesh(beamXGeo, steelMat); b2.position.set(0, 2.25, 0.65);
        const b3 = new THREE.Mesh(beamZGeo, steelMat); b3.position.set(-0.65, 2.25, -0.165);
        const b4 = new THREE.Mesh(beamZGeo, steelMat); b4.position.set(0.65, 2.25, -0.165);
        machineFrameGroup3d.add(b1, b2, b3, b4);

        // ─────────────────────────────────────────────────────────────
        // PALLET ELEVATOR VERTICAL GUIDE RAILS & HYDRAULIC CYLINDER
        // ─────────────────────────────────────────────────────────────
        const guideRailGeo = new THREE.BoxGeometry(0.04, 2.2, 0.04);
        const guideL = new THREE.Mesh(guideRailGeo, chromeMat);
        guideL.position.set(-0.61, 1.15, 0.18);
        const guideR = new THREE.Mesh(guideRailGeo, chromeMat);
        guideR.position.set(0.61, 1.15, 0.18);
        machineFrameGroup3d.add(guideL, guideR);

        // Base Outer Cylinder fixed to floor (Y: 0.0 to 0.75m)
        const pistonBaseGeo = new THREE.CylinderGeometry(0.055, 0.055, 0.85, 20);
        const pistonBaseMesh = new THREE.Mesh(pistonBaseGeo, steelMat);
        pistonBaseMesh.position.set(0, 0.425, 0.18);
        pistonBaseMesh.castShadow = true;
        machineFrameGroup3d.add(pistonBaseMesh);

        // Dynamic Telescopic Chrome Shaft (scales with currentPalletY)
        const pistonShaftGeo = new THREE.CylinderGeometry(0.038, 0.038, 1.48, 20);
        pistonShaftGeo.translate(0, 0.74, 0); // Translation so Y scaling extends upward from base
        palletElevatorPiston3d = new THREE.Mesh(pistonShaftGeo, chromeMat);
        palletElevatorPiston3d.position.set(0, 0.05, 0.18);
        machineFrameGroup3d.add(palletElevatorPiston3d);

        // ─────────────────────────────────────────────────────────────
        // 0. WAGOPAKOWACZKA AUTOMATYCZNA (AUTOMATED FORM-FILL-SEAL BAGGING MACHINE)
        // Positioned on the floor at X: -6.20m, Z: infeedZ (-0.78m)
        // High-fidelity industrial digital twin matching production line specifications
        // ─────────────────────────────────────────────────────────────
        const baggerX = -6.20;
        const baggerDarkMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.6, metalness: 0.5 });
        const baggerSteelMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.55 });
        const baggerPanelMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.45, metalness: 0.45 });
        const baggerGlassMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.08, metalness: 0.15, transparent: true, opacity: 0.38 });
        const baggerHeatMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xd97706, emissiveIntensity: 0.9, roughness: 0.25 });
        const baggerHopperMat = new THREE.MeshStandardMaterial({ color: 0x18202f, roughness: 0.75, metalness: 0.25 });

        // 4 Vertical Cabinet Corner Columns (Y: 0 to 2.45m)
        const baggerColGeo = new THREE.BoxGeometry(0.08, 2.45, 0.08);
        const baggerColPositions = [
            [baggerX - 0.46, 1.225, infeedZ - 0.46],
            [baggerX + 0.46, 1.225, infeedZ - 0.46],
            [baggerX - 0.46, 1.225, infeedZ + 0.46],
            [baggerX + 0.46, 1.225, infeedZ + 0.46]
        ];
        baggerColPositions.forEach(pos => {
            const col = new THREE.Mesh(baggerColGeo, baggerDarkMat);
            col.position.set(pos[0], pos[1], pos[2]);
            col.castShadow = true;
            machineFrameGroup3d.add(col);
        });

        // Top Frame Horizontal Beams (Y: 2.41m)
        const baggerBeamXGeo = new THREE.BoxGeometry(1.00, 0.08, 0.08);
        const baggerBeamZGeo = new THREE.BoxGeometry(0.08, 0.08, 1.00);
        const bbm1 = new THREE.Mesh(baggerBeamXGeo, baggerDarkMat); bbm1.position.set(baggerX, 2.41, infeedZ - 0.46);
        const bbm2 = new THREE.Mesh(baggerBeamXGeo, baggerDarkMat); bbm2.position.set(baggerX, 2.41, infeedZ + 0.46);
        const bbm3 = new THREE.Mesh(baggerBeamZGeo, baggerDarkMat); bbm3.position.set(baggerX - 0.46, 2.41, infeedZ);
        const bbm4 = new THREE.Mesh(baggerBeamZGeo, baggerDarkMat); bbm4.position.set(baggerX + 0.46, 2.41, infeedZ);
        machineFrameGroup3d.add(bbm1, bbm2, bbm3, bbm4);

        // Roof Top Deck Plate
        const baggerRoofGeo = new THREE.BoxGeometry(1.00, 0.03, 1.00);
        const baggerRoof = new THREE.Mesh(baggerRoofGeo, baggerDarkMat);
        baggerRoof.position.set(baggerX, 2.45, infeedZ);
        machineFrameGroup3d.add(baggerRoof);

        // Rear & Left Protective Enclosure Steel Panels
        const baggerRearPanelGeo = new THREE.BoxGeometry(0.92, 2.40, 0.02);
        const baggerRearPanel = new THREE.Mesh(baggerRearPanelGeo, baggerSteelMat);
        baggerRearPanel.position.set(baggerX, 1.20, infeedZ - 0.46);
        const baggerLeftPanelGeo = new THREE.BoxGeometry(0.02, 2.40, 0.92);
        const baggerLeftPanel = new THREE.Mesh(baggerLeftPanelGeo, baggerPanelMat);
        baggerLeftPanel.position.set(baggerX - 0.46, 1.20, infeedZ);
        machineFrameGroup3d.add(baggerRearPanel, baggerLeftPanel);

        // Lower Cabinet Base Enclosure (Front & Right)
        const baggerLowerDoorGeo = new THREE.BoxGeometry(0.88, 0.70, 0.02);
        const baggerLowerDoor = new THREE.Mesh(baggerLowerDoorGeo, baggerSteelMat);
        baggerLowerDoor.position.set(baggerX, 0.35, infeedZ + 0.46);
        const baggerLowerRightGeo = new THREE.BoxGeometry(0.02, 0.70, 0.88);
        const baggerLowerRight = new THREE.Mesh(baggerLowerRightGeo, baggerSteelMat);
        baggerLowerRight.position.set(baggerX + 0.46, 0.35, infeedZ);
        machineFrameGroup3d.add(baggerLowerDoor, baggerLowerRight);

        // Front Safety Viewing Glass Window & Surrounding Frame
        const baggerFrontGlassGeo = new THREE.BoxGeometry(0.86, 1.55, 0.02);
        const baggerFrontGlass = new THREE.Mesh(baggerFrontGlassGeo, baggerGlassMat);
        baggerFrontGlass.position.set(baggerX, 1.525, infeedZ + 0.46);
        machineFrameGroup3d.add(baggerFrontGlass);

        // Yellow Crossbar / Horizontal Protection Bar across Lower Window
        const yellowBarGeo = new THREE.BoxGeometry(0.96, 0.045, 0.045);
        const yellowBarMesh = new THREE.Mesh(yellowBarGeo, yellowMat);
        yellowBarMesh.position.set(baggerX, 0.78, infeedZ + 0.48);
        machineFrameGroup3d.add(yellowBarMesh);

        // ─────────────────────────────────────────────────────────────
        // HOPPER (LEJ ZASYPOWY) - MATTE CHARCOAL SILO FUNNEL ON ROOF
        // ─────────────────────────────────────────────────────────────
        const baggerHopperBaseGeo = new THREE.CylinderGeometry(0.24, 0.24, 0.06, 24);
        const baggerHopperBase = new THREE.Mesh(baggerHopperBaseGeo, baggerSteelMat);
        baggerHopperBase.position.set(baggerX, 2.48, infeedZ);
        machineFrameGroup3d.add(baggerHopperBase);

        const baggerHopperGeo = new THREE.CylinderGeometry(0.48, 0.22, 0.50, 24);
        const baggerHopper = new THREE.Mesh(baggerHopperGeo, baggerHopperMat);
        baggerHopper.position.set(baggerX, 2.73, infeedZ);
        baggerHopper.castShadow = true;
        machineFrameGroup3d.add(baggerHopper);

        const baggerHopperRimGeo = new THREE.CylinderGeometry(0.50, 0.50, 0.04, 24);
        const baggerHopperRim = new THREE.Mesh(baggerHopperRimGeo, baggerDarkMat);
        baggerHopperRim.position.set(baggerX, 2.98, infeedZ);
        machineFrameGroup3d.add(baggerHopperRim);

        // ─────────────────────────────────────────────────────────────
        // VERTICAL FORMING TUBE & FILM SHOULDER (TUBUS FORMUJĄCY)
        // ─────────────────────────────────────────────────────────────
        const baggerFormerTubeGeo = new THREE.CylinderGeometry(0.16, 0.16, 0.85, 24);
        const baggerFormerTubeMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.35, metalness: 0.75 });
        const baggerFormerTube = new THREE.Mesh(baggerFormerTubeGeo, baggerFormerTubeMat);
        baggerFormerTube.position.set(baggerX, 1.55, infeedZ);
        baggerFormerTube.castShadow = true;
        machineFrameGroup3d.add(baggerFormerTube);

        const baggerShoulderGeo = new THREE.CylinderGeometry(0.26, 0.17, 0.20, 24);
        const baggerShoulder = new THREE.Mesh(baggerShoulderGeo, baggerFormerTubeMat);
        baggerShoulder.position.set(baggerX, 2.05, infeedZ);
        machineFrameGroup3d.add(baggerShoulder);

        // ─────────────────────────────────────────────────────────────
        // HORIZONTAL FILM REEL ROLL ON UPPER RIGHT (ROLKA FOLII)
        // ─────────────────────────────────────────────────────────────
        const baggerFilmRollGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.48, 24);
        const baggerFilmRollMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.25, metalness: 0.2, transparent: true, opacity: 0.85 });
        const baggerFilmRoll = new THREE.Mesh(baggerFilmRollGeo, baggerFilmRollMat);
        baggerFilmRoll.rotation.x = Math.PI / 2;
        baggerFilmRoll.position.set(baggerX + 0.36, 2.12, infeedZ - 0.10);
        baggerFilmRoll.castShadow = true;

        const baggerSpoolCoreGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.56, 16);
        const baggerSpoolCore = new THREE.Mesh(baggerSpoolCoreGeo, chromeMat);
        baggerSpoolCore.rotation.x = Math.PI / 2;
        baggerSpoolCore.position.set(baggerX + 0.36, 2.12, infeedZ - 0.10);
        machineFrameGroup3d.add(baggerFilmRoll, baggerSpoolCore);

        // ─────────────────────────────────────────────────────────────
        // PNEUMATIC HEATED SEALING JAWS (SZCZĘKI ZGRZEWAJĄCE WORKI - MQTT szczekiZamkniete)
        // Positioned at Y: 0.82m inside the bagger tower
        // ─────────────────────────────────────────────────────────────
        const jawGeo = new THREE.BoxGeometry(0.05, 0.08, 0.52);
        const heatFaceGeo = new THREE.BoxGeometry(0.012, 0.035, 0.50);

        // Left Jaw (X: -6.32m when open, moves right to -6.22m when closed)
        baggerJawLeft3d = new THREE.Group();
        baggerJawLeft3d.position.set(baggerX - 0.12, 0.82, infeedZ);
        const jawLMesh = new THREE.Mesh(jawGeo, steelMat);
        const heatLMesh = new THREE.Mesh(heatFaceGeo, baggerHeatMat); heatLMesh.position.set(0.026, 0, 0);
        const jawLCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.22, 12), chromeMat);
        jawLCyl.rotation.z = Math.PI / 2; jawLCyl.position.set(-0.13, 0, 0);
        baggerJawLeft3d.add(jawLMesh, heatLMesh, jawLCyl);
        machineFrameGroup3d.add(baggerJawLeft3d);

        // Right Jaw (X: -6.08m when open, moves left to -6.18m when closed)
        baggerJawRight3d = new THREE.Group();
        baggerJawRight3d.position.set(baggerX + 0.12, 0.82, infeedZ);
        const jawRMesh = new THREE.Mesh(jawGeo, steelMat);
        const heatRMesh = new THREE.Mesh(heatFaceGeo, baggerHeatMat); heatRMesh.position.set(-0.026, 0, 0);
        const jawRCyl = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.22, 12), chromeMat);
        jawRCyl.rotation.z = Math.PI / 2; jawRCyl.position.set(0.13, 0, 0);
        baggerJawRight3d.add(jawRMesh, heatRMesh, jawRCyl);
        machineFrameGroup3d.add(baggerJawRight3d);

        // Machine Operator HMI Touchscreen Console (Cyan display on front panel)
        const baggerHmiStandGeo = new THREE.BoxGeometry(0.04, 0.04, 0.12);
        const baggerHmiStand = new THREE.Mesh(baggerHmiStandGeo, chromeMat);
        baggerHmiStand.position.set(baggerX - 0.25, 1.45, infeedZ + 0.48);
        const baggerHmiScreenGeo = new THREE.BoxGeometry(0.24, 0.18, 0.03);
        const baggerHmiScreenMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0284c7, emissiveIntensity: 0.75 });
        const baggerHmiScreen = new THREE.Mesh(baggerHmiScreenGeo, baggerHmiScreenMat);
        baggerHmiScreen.position.set(baggerX - 0.25, 1.45, infeedZ + 0.54);
        machineFrameGroup3d.add(baggerHmiStand, baggerHmiScreen);

        // Tri-Color Andon Signal Tower Beacon on Roof Corner
        const beaconStemGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.18, 12);
        const beaconStem = new THREE.Mesh(beaconStemGeo, chromeMat);
        beaconStem.position.set(baggerX - 0.42, 2.54, infeedZ + 0.42);
        const beaconRed = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.04, 12), new THREE.MeshStandardMaterial({ color: 0xef4444, roughness: 0.2 }));
        beaconRed.position.set(baggerX - 0.42, 2.64, infeedZ + 0.42);
        const beaconAmber = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.04, 12), new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.2 }));
        beaconAmber.position.set(baggerX - 0.42, 2.68, infeedZ + 0.42);
        baggerBeaconGreen3d = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.04, 12), new THREE.MeshStandardMaterial({ color: 0x10b981, emissive: 0x059669, emissiveIntensity: 0.8, roughness: 0.2 }));
        baggerBeaconGreen3d.position.set(baggerX - 0.42, 2.72, infeedZ + 0.42);
        machineFrameGroup3d.add(beaconStem, beaconRed, beaconAmber, baggerBeaconGreen3d);

        // ─────────────────────────────────────────────────────────────
        // 0b. MAŁA TAŚMA POZIOMA POD SZCZĘKAMI (SHORT TAKEAWAY DISCHARGE CONVEYOR)
        // Spans from X: -6.55m to X: -5.15m at floor level Y: 0.35m
        // ─────────────────────────────────────────────────────────────
        const takeawayX = -5.85;
        const takeawayLength = 1.40;
        const takeawayBeltGeo = new THREE.BoxGeometry(takeawayLength, 0.05, beltW);
        const takeawayBeltMesh = new THREE.Mesh(takeawayBeltGeo, beltMat);
        takeawayBeltMesh.position.set(takeawayX, 0.35, infeedZ);
        takeawayBeltMesh.castShadow = true;
        machineFrameGroup3d.add(takeawayBeltMesh);

        // Side Guide Rails on takeaway belt
        const takeawayRailGeo = new THREE.BoxGeometry(takeawayLength, 0.09, 0.02);
        const tRail1 = new THREE.Mesh(takeawayRailGeo, yellowMat); tRail1.position.set(takeawayX, 0.40, infeedZ - halfRail);
        const tRail2 = new THREE.Mesh(takeawayRailGeo, yellowMat); tRail2.position.set(takeawayX, 0.40, infeedZ + halfRail);
        machineFrameGroup3d.add(tRail1, tRail2);

        // Takeaway Conveyor Floor Support Legs
        const takeawayLegGeo = new THREE.BoxGeometry(0.05, 0.35, 0.05);
        for (let tlx of [-6.45, -5.25]) {
            for (let tlz of [infeedZ - 0.24, infeedZ + 0.24]) {
                const tLeg = new THREE.Mesh(takeawayLegGeo, steelMat);
                tLeg.position.set(tlx, 0.175, tlz);
                machineFrameGroup3d.add(tLeg);
            }
        }

        // Takeaway Belt Geared Drive Motor
        const takeawayMotorGeo = new THREE.BoxGeometry(0.18, 0.14, 0.16);
        const takeawayMotor = new THREE.Mesh(takeawayMotorGeo, steelMat);
        takeawayMotor.position.set(-6.50, 0.35, infeedZ - 0.36);
        machineFrameGroup3d.add(takeawayMotor);

        // ─────────────────────────────────────────────────────────────
        // 0c. TAŚMA SKOŚNA WZNOSZĄCA (INCLINE CLEATED CONVEYOR BELT)
        // Runs from X: -5.15m (Y: 0.35m) up to X: -3.75m (Y: 1.78m) - length: 2.00m, angle: ~45.6°
        // ─────────────────────────────────────────────────────────────
        const inclineCenterX = -4.45;
        const inclineCenterY = 1.065;
        const inclineAngle = 0.796; // +45.6 degrees rotation around Z (rising from takeaway belt to infeed belt)
        const inclineLength = 2.00;

        const inclineGroup = new THREE.Group();
        inclineGroup.position.set(inclineCenterX, inclineCenterY, infeedZ);
        inclineGroup.rotation.z = inclineAngle;

        // Incline Conveyor Bed Belt
        const inclineBeltGeo = new THREE.BoxGeometry(inclineLength, 0.05, beltW);
        const inclineBeltMesh = new THREE.Mesh(inclineBeltGeo, beltMat);
        inclineBeltMesh.castShadow = true;
        inclineGroup.add(inclineBeltMesh);

        // 8 Cleats / Flights along belt to physically carry sacks uphill (poprzeczne zabieraki gumowe)
        const cleatGeo = new THREE.BoxGeometry(0.016, 0.035, beltW - 0.04);
        const cleatMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.9 });
        for (let cx = -0.85; cx <= 0.85; cx += 0.22) {
            const cleat = new THREE.Mesh(cleatGeo, cleatMat);
            cleat.position.set(cx, 0.035, 0);
            cleat.castShadow = true;
            inclineGroup.add(cleat);
        }

        // Incline Yellow Side Guide Rails (Bandy boczne wznoszące)
        const inclineRailGeo = new THREE.BoxGeometry(inclineLength, 0.10, 0.02);
        const iRail1 = new THREE.Mesh(inclineRailGeo, yellowMat); iRail1.position.set(0, 0.055, -halfRail);
        const iRail2 = new THREE.Mesh(inclineRailGeo, yellowMat); iRail2.position.set(0, 0.055, +halfRail);
        inclineGroup.add(iRail1, iRail2);

        machineFrameGroup3d.add(inclineGroup);

        // Incline Conveyor Heavy Duty Structural Support Posts down to floor
        const incLeg1Geo = new THREE.BoxGeometry(0.05, 0.55, 0.05);
        const incL1 = new THREE.Mesh(incLeg1Geo, steelMat); incL1.position.set(-4.95, 0.275, infeedZ - halfRail);
        const incL2 = new THREE.Mesh(incLeg1Geo, steelMat); incL2.position.set(-4.95, 0.275, infeedZ + halfRail);

        const incLeg2Geo = new THREE.BoxGeometry(0.05, 1.05, 0.05);
        const incL3 = new THREE.Mesh(incLeg2Geo, steelMat); incL3.position.set(-4.45, 0.525, infeedZ - halfRail);
        const incL4 = new THREE.Mesh(incLeg2Geo, steelMat); incL4.position.set(-4.45, 0.525, infeedZ + halfRail);

        const incLeg3Geo = new THREE.BoxGeometry(0.05, 1.55, 0.05);
        const incL5 = new THREE.Mesh(incLeg3Geo, steelMat); incL5.position.set(-3.95, 0.775, infeedZ - halfRail);
        const incL6 = new THREE.Mesh(incLeg3Geo, steelMat); incL6.position.set(-3.95, 0.775, infeedZ + halfRail);
        machineFrameGroup3d.add(incL1, incL2, incL3, incL4, incL5, incL6);

        // Top Head Pulley Geared Electric Drive Motor
        const inclineMotorGeo = new THREE.BoxGeometry(0.20, 0.16, 0.16);
        const inclineMotor = new THREE.Mesh(inclineMotorGeo, steelMat);
        inclineMotor.position.set(-3.75, 1.82, infeedZ - 0.36);
        machineFrameGroup3d.add(inclineMotor);

        // ─────────────────────────────────────────────────────────────
        // INFEED CONVEYOR WITH DYNAMIC CHECKWEIGHER & REJECT DROP FLAP
        // Shifted back by 1.35m (1 pallet + clearance) with added conveyor belt extension
        // ─────────────────────────────────────────────────────────────

        // Section 1: Infeed Belt from Bagging Machine (Shifted back to X: -3.75 to -3.25, Y: 1.78)
        const infeed1Geo = new THREE.BoxGeometry(0.50, 0.06, beltW);
        const infeed1Mesh = new THREE.Mesh(infeed1Geo, beltMat);
        infeed1Mesh.position.set(-3.50, 1.78, infeedZ);
        infeed1Mesh.castShadow = true;
        machineFrameGroup3d.add(infeed1Mesh);

        // Section 2: Checkweigher Dynamic Scale Platform (Shifted back to X: -3.25 to -2.81, Y: 1.78)
        const scaleBedGeo = new THREE.BoxGeometry(0.44, 0.05, beltW);
        const scaleMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.3, metalness: 0.7 });
        const scaleMesh = new THREE.Mesh(scaleBedGeo, scaleMat);
        scaleMesh.position.set(-3.03, 1.775, infeedZ);
        scaleMesh.castShadow = true;
        machineFrameGroup3d.add(scaleMesh);

        // Load cell sensors under scale platform
        const loadCellGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.04, 12);
        for (let lcx of [-3.17, -2.89]) {
            for (let lcz of [infeedZ - 0.24, infeedZ + 0.24]) {
                const cell = new THREE.Mesh(loadCellGeo, chromeMat);
                cell.position.set(lcx, 1.73, lcz);
                machineFrameGroup3d.add(cell);
            }
        }

        // Section 3: Pneumatic Reject Drop Flap / Trapdoor (Klapa Zrzutu Odrzutów)
        // Shifted back to X: -2.63 (span -2.82 to -2.44)
        const flapGeo = new THREE.BoxGeometry(0.38, 0.03, beltW);
        const flapMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.3, metalness: 0.6 });
        rejectFlapMesh3d = new THREE.Mesh(flapGeo, flapMat);
        rejectFlapMesh3d.position.set(-2.63, 1.78, infeedZ);
        rejectFlapMesh3d.castShadow = true;
        machineFrameGroup3d.add(rejectFlapMesh3d);

        // Pneumatic cylinder operating the reject flap
        const rejectCylGeo = new THREE.CylinderGeometry(0.016, 0.016, 0.28, 12);
        const rejectCyl = new THREE.Mesh(rejectCylGeo, chromeMat);
        rejectCyl.position.set(-2.63, 1.62, infeedZ - 0.28);
        machineFrameGroup3d.add(rejectCyl);

        // Reject Drop Funnel / Chute (Kosz / rynna zrzutowa na worki z błędem)
        const chuteGeo = new THREE.BoxGeometry(0.42, 1.20, beltW + 0.02);
        const chuteMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.6, metalness: 0.3, transparent: true, opacity: 0.65 });
        const chuteMesh = new THREE.Mesh(chuteGeo, chuteMat);
        chuteMesh.position.set(-2.63, 1.05, infeedZ);
        machineFrameGroup3d.add(chuteMesh);

        // Reject Collection Bin Box on Floor (Maintains clear safety margin before roller track)
        const binBoxGeo = new THREE.BoxGeometry(0.55, 0.45, beltW + 0.04);
        const binBoxMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.6, metalness: 0.4 });
        const binBox = new THREE.Mesh(binBoxGeo, binBoxMat);
        binBox.position.set(-2.63, 0.22, infeedZ);
        binBox.castShadow = true;

        // Safety yellow rim on the reject collection bin
        const binRimGeo = new THREE.BoxGeometry(0.57, 0.04, beltW + 0.06);
        const binRim = new THREE.Mesh(binRimGeo, yellowMat);
        binRim.position.set(-2.63, 0.44, infeedZ);
        machineFrameGroup3d.add(binBox, binRim);

        // Section 3b: NEW INTERMEDIATE EXTENSION CONVEYOR BELT (Dołożony kawałek taśmy łączący zrzut z podejściem do obracaka)
        // Spans from X: -2.44 to -1.07 (length: 1.37m, center: -1.755)
        const extensionBeltGeo = new THREE.BoxGeometry(1.37, 0.06, beltW);
        const extensionBeltMesh = new THREE.Mesh(extensionBeltGeo, beltMat);
        extensionBeltMesh.position.set(-1.755, 1.78, infeedZ);
        extensionBeltMesh.castShadow = true;
        machineFrameGroup3d.add(extensionBeltMesh);

        // Intermediate belt support roller drive beneath
        const beltRollerGeo = new THREE.CylinderGeometry(0.04, 0.04, beltW + 0.04, 16);
        const rollerSub = new THREE.Mesh(beltRollerGeo, chromeMat);
        rollerSub.rotation.x = Math.PI / 2;
        rollerSub.position.set(-1.755, 1.73, infeedZ);
        machineFrameGroup3d.add(rollerSub);

        // Section 4: Lead-in belt to Turner (X: -1.07 to -0.69)
        const leadInGeo = new THREE.BoxGeometry(0.38, 0.06, beltW);
        const leadInMesh = new THREE.Mesh(leadInGeo, beltMat);
        leadInMesh.position.set(-0.88, 1.78, infeedZ);
        leadInMesh.castShadow = true;
        machineFrameGroup3d.add(leadInMesh);

        // Infeed Conveyor Support Legs (Extended to cover full span from -3.65 to -0.75)
        const legGeo = new THREE.BoxGeometry(0.05, 1.78, 0.05);
        const legPositions = [
            [-3.65, 0.89, infeedZ - 0.28], [-3.65, 0.89, infeedZ + 0.28],
            [-2.85, 0.89, infeedZ - 0.28], [-2.85, 0.89, infeedZ + 0.28],
            [-2.05, 0.89, infeedZ - 0.28], [-2.05, 0.89, infeedZ + 0.28],
            [-1.30, 0.89, infeedZ - 0.28], [-1.30, 0.89, infeedZ + 0.28],
            [-0.75, 0.89, infeedZ - 0.28], [-0.75, 0.89, infeedZ + 0.28]
        ];
        legPositions.forEach(lp => {
            const leg = new THREE.Mesh(legGeo, steelMat);
            leg.position.set(lp[0], lp[1], lp[2]);
            machineFrameGroup3d.add(leg);
        });

        // Infeed Conveyor Side Guide Rails (Extended length 3.10m from -3.75 to -0.65, center -2.20)
        const infeedRailGeo = new THREE.BoxGeometry(3.10, 0.09, 0.02);
        const railBack = new THREE.Mesh(infeedRailGeo, yellowMat); railBack.position.set(-2.20, 1.83, infeedZ - halfRail);
        const railFront = new THREE.Mesh(infeedRailGeo, yellowMat); railFront.position.set(-2.20, 1.83, infeedZ + halfRail);
        machineFrameGroup3d.add(railBack, railFront);

        // Infeed Electric Drive Motor
        const motorGeo = new THREE.BoxGeometry(0.22, 0.16, 0.18);
        const motorMesh = new THREE.Mesh(motorGeo, steelMat);
        motorMesh.position.set(-3.60, 1.78, infeedZ - 0.38);
        machineFrameGroup3d.add(motorMesh);

        // ─────────────────────────────────────────────────────────────
        // OVERHEAD CLAMP BAG TURNER (OBRACAK WORKÓW Z DWOMA ŁAPKAMI ŚCISKAJĄCYMI OD GÓRY)
        // Positioned along the infeed belt at X = -1.05m (ciut dalej przed windą)
        // ─────────────────────────────────────────────────────────────
        const turnerX = -1.05;

        // Overhead portal bridge frame across conveyor belt
        const turnerColGeo = new THREE.BoxGeometry(0.05, 0.46, 0.05);
        const tCol1 = new THREE.Mesh(turnerColGeo, steelMat);
        tCol1.position.set(turnerX, 2.01, infeedZ - halfRail - 0.03);
        const tCol2 = new THREE.Mesh(turnerColGeo, steelMat);
        tCol2.position.set(turnerX, 2.01, infeedZ + halfRail + 0.03);

        const turnerTopBeamGeo = new THREE.BoxGeometry(0.06, 0.06, (halfRail * 2) + 0.12);
        const tBeam = new THREE.Mesh(turnerTopBeamGeo, steelMat);
        tBeam.position.set(turnerX, 2.24, infeedZ);
        machineFrameGroup3d.add(tCol1, tCol2, tBeam);

        // Fixed vertical rotary actuator cylinder suspended from top beam
        const rotaryActuatorGeo = new THREE.CylinderGeometry(0.045, 0.045, 0.14, 16);
        const rotaryActuator = new THREE.Mesh(rotaryActuatorGeo, steelMat);
        rotaryActuator.position.set(turnerX, 2.14, infeedZ);
        machineFrameGroup3d.add(rotaryActuator);

        // Rotating Clamp Head Group (Obracająca się głowica z dwoma łapkami zaciskającymi od góry)
        turnerClampGroup3d = new THREE.Group();
        turnerClampGroup3d.position.set(turnerX, 2.05, infeedZ);

        // Central vertical chrome shaft connecting actuator to clamp yoke
        const shaftGeo = new THREE.CylinderGeometry(0.024, 0.024, 0.10, 16);
        const shaft = new THREE.Mesh(shaftGeo, chromeMat);
        shaft.position.set(0, 0.01, 0);
        turnerClampGroup3d.add(shaft);

        // Horizontal cross yoke (Belka nośna łapek zaciskowych)
        const yokeGeo = new THREE.BoxGeometry(0.08, 0.04, 0.44);
        const yoke = new THREE.Mesh(yokeGeo, yellowMat);
        yoke.position.set(0, -0.04, 0);
        yoke.castShadow = true;
        turnerClampGroup3d.add(yoke);

        // Two vertical clamping arms ("dwie łapki zciskające od góry") with rubber grip pads
        const turnerArmGeo = new THREE.BoxGeometry(0.04, 0.18, 0.03);
        const padGeo = new THREE.BoxGeometry(0.24, 0.07, 0.025);
        const rubberPadMat = new THREE.MeshStandardMaterial({
            color: 0x1e293b,
            roughness: 0.9,
            metalness: 0.1
        });

        // Left Clamping Arm & Grip Pad
        const armL = new THREE.Mesh(turnerArmGeo, chromeMat);
        armL.position.set(0, -0.12, -0.20);
        const padL = new THREE.Mesh(padGeo, rubberPadMat);
        padL.position.set(0, -0.17, -0.19);
        padL.castShadow = true;
        turnerClampGroup3d.add(armL, padL);

        // Right Clamping Arm & Grip Pad
        const armR = new THREE.Mesh(turnerArmGeo, chromeMat);
        armR.position.set(0, -0.12, 0.20);
        const padR = new THREE.Mesh(padGeo, rubberPadMat);
        padR.position.set(0, -0.17, 0.19);
        padR.castShadow = true;
        turnerClampGroup3d.add(armR, padR);

        machineFrameGroup3d.add(turnerClampGroup3d);

        // Internal Receiving / Staging Conveyor & Transfer Bed (Stół buforowy rzędu łączący obracak z płytami rozjazdowymi)
        // Spans from pusher rear Z: -0.98 continuously to the front edge of split formation plates Z: -0.18 (depth 0.80m)
        const stagingConveyorGeo = new THREE.BoxGeometry(1.28, 0.05, 0.80);
        const stagingConveyorMesh = new THREE.Mesh(stagingConveyorGeo, beltMat);
        stagingConveyorMesh.position.set(0, 1.74, -0.58);
        stagingConveyorMesh.castShadow = true;
        machineFrameGroup3d.add(stagingConveyorMesh);

        // Stainless steel transfer bridge transition between staging table and split plates
        const bridgeBevelGeo = new THREE.BoxGeometry(1.28, 0.015, 0.04);
        const bridgeBevel = new THREE.Mesh(bridgeBevelGeo, chromeMat);
        bridgeBevel.position.set(0, 1.745, -0.18);
        machineFrameGroup3d.add(bridgeBevel);

        // Split Formation Plates / Trapdoor (Płyty rozsuwane dwudzielne, Z: 0.18, Y: 1.74)
        const plateGeo = new THREE.BoxGeometry(0.48, 0.022, 0.72);
        upperPlateLeft3d = new THREE.Mesh(plateGeo, chromeMat);
        upperPlateLeft3d.position.set(-0.25, 1.74, 0.18);
        upperPlateLeft3d.castShadow = true;

        upperPlateRight3d = new THREE.Mesh(plateGeo, chromeMat);
        upperPlateRight3d.position.set(0.25, 1.74, 0.18);
        upperPlateRight3d.castShadow = true;

        machineFrameGroup3d.add(upperPlateLeft3d);
        machineFrameGroup3d.add(upperPlateRight3d);

        // ROW PUSHER (PRZEPYCHACZ PNEUMATYCZNY W CZERWONEJ RAMCE)
        // Overhead support beam & dual pneumatic cylinders positioned above the rear of staging conveyor
        const pusherSupportBeamGeo = new THREE.BoxGeometry(1.30, 0.06, 0.06);
        const pusherSupportBeam = new THREE.Mesh(pusherSupportBeamGeo, steelMat);
        pusherSupportBeam.position.set(0, 2.05, infeedZ - 0.20);
        machineFrameGroup3d.add(pusherSupportBeam);

        const pusherCylinderGeo = new THREE.CylinderGeometry(0.022, 0.022, 0.65, 16);
        const cyl1 = new THREE.Mesh(pusherCylinderGeo, chromeMat);
        cyl1.rotation.x = Math.PI / 2;
        cyl1.position.set(-0.32, 1.95, infeedZ - 0.05);
        const cyl2 = new THREE.Mesh(pusherCylinderGeo, chromeMat);
        cyl2.rotation.x = Math.PI / 2;
        cyl2.position.set(0.32, 1.95, infeedZ - 0.05);
        machineFrameGroup3d.add(cyl1, cyl2);

        // Moving Pusher Paddle / Blade (Żółta belka spychająca)
        const paddleGeo = new THREE.BoxGeometry(1.16, 0.14, 0.04);
        pusherPaddleMesh3d = new THREE.Mesh(paddleGeo, yellowMat);
        pusherPaddleMesh3d.position.set(0, 1.84, infeedZ - 0.16);
        pusherPaddleMesh3d.castShadow = true;
        machineFrameGroup3d.add(pusherPaddleMesh3d);

        // ─────────────────────────────────────────────────────────────
        // 1. MOTORIZED FLOOR ROLLER CONVEYOR BED (EXTENDED WZDŁUŻ OSI X)
        // Spans from X: -4.00 (under shifted dispenser) to X: +2.45 (outfeed)
        // ─────────────────────────────────────────────────────────────
        const isIndustrial = !String(currentConfig.pallet_type || '').toUpperCase().includes('EURO');
        const pWidth = isIndustrial ? 1.0 : 0.8;
        const pLength = 1.2;
        const trackZ = 0.18; // Exactly centered under split formation plates

        // Main structural side rails running from Shifted Dispenser (X: -4.05) through Stacking (X: 0) to Outfeed (X: +2.45)
        const trackLengthX = 6.50;
        const trackCenterX = -0.80;
        const sideRailGeo = new THREE.BoxGeometry(trackLengthX, 0.10, 0.06);
        const halfRailZ = (pWidth / 2) + 0.08;

        const sideRailRear = new THREE.Mesh(sideRailGeo, steelMat);
        sideRailRear.position.set(trackCenterX, 0.05, trackZ - halfRailZ);
        sideRailRear.castShadow = true;

        const sideRailFront = new THREE.Mesh(sideRailGeo, steelMat);
        sideRailFront.position.set(trackCenterX, 0.05, trackZ + halfRailZ);
        sideRailFront.castShadow = true;
        machineFrameGroup3d.add(sideRailRear, sideRailFront);

        // Safety yellow guide edges on roller track
        const guardEdgeGeo = new THREE.BoxGeometry(trackLengthX, 0.04, 0.02);
        const guardRear = new THREE.Mesh(guardEdgeGeo, yellowMat); guardRear.position.set(trackCenterX, 0.10, trackZ - halfRailZ);
        const guardFront = new THREE.Mesh(guardEdgeGeo, yellowMat); guardFront.position.set(trackCenterX, 0.10, trackZ + halfRailZ);
        machineFrameGroup3d.add(guardRear, guardFront);

        // Rotating Cylindrical Steel Rollers along X axis (from X: -3.95 to X: 2.35)
        rollerMeshes3d = [];
        const rollerLength = (halfRailZ * 2) - 0.04;
        const rollerGeo = new THREE.CylinderGeometry(0.028, 0.028, rollerLength, 16);
        for (let rx = -3.95; rx <= 2.35; rx += 0.22) {
            const roller = new THREE.Mesh(rollerGeo, chromeMat);
            roller.rotation.x = Math.PI / 2;
            roller.position.set(rx, 0.055, trackZ);
            roller.castShadow = true;
            machineFrameGroup3d.add(roller);
            rollerMeshes3d.push(roller);
        }

        // Roller track drive motors
        const rollerMotorGeo = new THREE.BoxGeometry(0.18, 0.14, 0.18);
        const motor1 = new THREE.Mesh(rollerMotorGeo, steelMat);
        motor1.position.set(-3.85, 0.07, trackZ + halfRailZ + 0.12);
        const motor2 = new THREE.Mesh(rollerMotorGeo, steelMat);
        motor2.position.set(2.25, 0.07, trackZ + halfRailZ + 0.12);
        machineFrameGroup3d.add(motor1, motor2);

        // ─────────────────────────────────────────────────────────────
        // 2. EMPTY PALLET MAGAZINE / DISPENSER (SHIFTED BACK BY 1 PALLET + CLEARANCE: X: -3.20)
        // ─────────────────────────────────────────────────────────────
        const dispenserX = -3.20;
        const dispColGeo = new THREE.BoxGeometry(0.06, 1.60, 0.06);
        const dispHalfX = (pLength / 2) + 0.04; // 0.64m
        const dispHalfZ = (pWidth / 2) + 0.04;  // 0.54m or 0.44m

        const dispCorners = [
            [dispenserX - dispHalfX, 0.80, trackZ - dispHalfZ],
            [dispenserX + dispHalfX, 0.80, trackZ - dispHalfZ],
            [dispenserX - dispHalfX, 0.80, trackZ + dispHalfZ],
            [dispenserX + dispHalfX, 0.80, trackZ + dispHalfZ]
        ];
        dispCorners.forEach(c => {
            const dCol = new THREE.Mesh(dispColGeo, steelMat);
            dCol.position.set(c[0], c[1], c[2]);
            dCol.castShadow = true;
            machineFrameGroup3d.add(dCol);
        });

        // Top Funnel Guide Angles (Along X: pLength + 0.16m)
        const funnelGeo = new THREE.BoxGeometry(pLength + 0.16, 0.05, 0.05);
        const fun1 = new THREE.Mesh(funnelGeo, yellowMat); fun1.position.set(dispenserX, 1.60, trackZ - dispHalfZ);
        const fun2 = new THREE.Mesh(funnelGeo, yellowMat); fun2.position.set(dispenserX, 1.60, trackZ + dispHalfZ);
        machineFrameGroup3d.add(fun1, fun2);

        // Pneumatic Bottom Pallet Separator Pawls
        const pawlGeo = new THREE.BoxGeometry(0.12, 0.06, 0.08);
        const pawlL = new THREE.Mesh(pawlGeo, chromeMat); pawlL.position.set(dispenserX - dispHalfX + 0.02, 0.22, trackZ);
        const pawlR = new THREE.Mesh(pawlGeo, chromeMat); pawlR.position.set(dispenserX + dispHalfX - 0.02, 0.22, trackZ);
        machineFrameGroup3d.add(pawlL, pawlR);

        // Stack of 6 Empty Pełnoprawne Wooden Pallets in Magazine Chute (At dispenserX, trackZ)
        const woodMat = new THREE.MeshStandardMaterial({
            color: 0xc89d66,
            roughness: 0.8,
            metalness: 0.1
        });

        for (let pIdx = 0; pIdx < 6; pIdx++) {
            const stackPallet = create3dFullEuroPalletMesh(isIndustrial, woodMat);
            stackPallet.position.set(dispenserX, 0.055 + (pIdx * 0.144), trackZ);
            machineFrameGroup3d.add(stackPallet);
        }

        // ─────────────────────────────────────────────────────────────
        // 3. INTERMEDIATE PALLET WITH CARDBOARD SLIP SHEET (STANOWISKO PRZEKŁADKI)
        // Positioned in the gap between dispenser (X: -3.20) and elevator (X: 0) at X: -1.60
        // ─────────────────────────────────────────────────────────────
        const slipPalletX = -1.60;

        // Base pełnoprawna wooden pallet on roller track
        const slipPallet = create3dFullEuroPalletMesh(isIndustrial, woodMat);
        slipPallet.position.set(slipPalletX, 0.055, trackZ);
        machineFrameGroup3d.add(slipPallet);

        // Cardboard Slip Sheet / Bottom Layer Sheet (Tekturowa przekładka)
        const cardboardMat = new THREE.MeshStandardMaterial({
            color: 0xba8c59, // Natural Kraft / Corrugated Cardboard tone
            roughness: 0.95,
            metalness: 0.02
        });
        const slipSheetGeo = new THREE.BoxGeometry(pLength - 0.04, 0.008, pWidth - 0.04);
        const slipSheetMesh = new THREE.Mesh(slipSheetGeo, cardboardMat);
        slipSheetMesh.position.set(slipPalletX, 0.055 + 0.144 + 0.004, trackZ);
        slipSheetMesh.castShadow = true;
        machineFrameGroup3d.add(slipSheetMesh);

        // Slip Sheet Applicator Gantry / Vacuum Gripper Beam Overhead (Rama podajnika przekładek)
        const gantryColGeo = new THREE.BoxGeometry(0.05, 1.40, 0.05);
        const g1 = new THREE.Mesh(gantryColGeo, steelMat); g1.position.set(slipPalletX - 0.55, 0.70, trackZ - halfRailZ - 0.04);
        const g2 = new THREE.Mesh(gantryColGeo, steelMat); g2.position.set(slipPalletX + 0.55, 0.70, trackZ - halfRailZ - 0.04);
        const gantryBeamGeo = new THREE.BoxGeometry(1.20, 0.06, 0.06);
        const gBeam = new THREE.Mesh(gantryBeamGeo, yellowMat); gBeam.position.set(slipPalletX, 1.35, trackZ - halfRailZ - 0.04);
        machineFrameGroup3d.add(g1, g2, gBeam);

        // Pneumatic Vacuum Suction Arm extending over pallet center
        const slipArmGeo = new THREE.BoxGeometry(0.04, 0.04, halfRailZ + 0.06);
        const slipArmMesh = new THREE.Mesh(slipArmGeo, chromeMat);
        slipArmMesh.position.set(slipPalletX, 1.35, trackZ - (halfRailZ / 2));
        const suctionCupGeo = new THREE.CylinderGeometry(0.04, 0.02, 0.04, 12);
        const suctionCup1 = new THREE.Mesh(suctionCupGeo, steelMat);
        suctionCup1.position.set(slipPalletX - 0.20, 1.31, trackZ);
        const suctionCup2 = new THREE.Mesh(suctionCupGeo, steelMat);
        suctionCup2.position.set(slipPalletX + 0.20, 1.31, trackZ);
        machineFrameGroup3d.add(slipArmMesh, suctionCup1, suctionCup2);
    }

    // Build Realistic Wooden Pallet & Steel Lift Carriage (Industrial 1.0m x 1.2m vs EURO 0.8m x 1.2m) at (X: 0, Z: 0.18)
    function build3dEuroPallet() {
        if (!palletGroup3d) return;
        palletGroup3d.clear();
        palletGroup3d.position.set(currentPalletX, currentPalletY, 0.18); // Dynamic elevator vertical and horizontal position

        const woodMat = new THREE.MeshStandardMaterial({
            color: 0xc89d66,
            roughness: 0.8,
            metalness: 0.1
        });
        const carriageMat = new THREE.MeshStandardMaterial({
            color: 0x1e293b,
            roughness: 0.5,
            metalness: 0.7
        });
        const yellowHazardMat = new THREE.MeshStandardMaterial({
            color: 0xf59e0b,
            roughness: 0.4,
            metalness: 0.3
        });

        const isIndustrial = !String(currentConfig.pallet_type || '').toUpperCase().includes('EURO');
        const forkSpanX = isIndustrial ? 0.35 : 0.28;

        // ─────────────────────────────────────────────────────────────
        // STEEL ELEVATOR CARRIAGE FRAME & LIFT FORKS (WÓZEK WINDY PALETYZATORA)
        // ─────────────────────────────────────────────────────────────
        const forkGeo = new THREE.BoxGeometry(0.12, 0.04, 1.26);
        const forkL = new THREE.Mesh(forkGeo, carriageMat);
        forkL.position.set(-forkSpanX, -0.02, 0);
        forkL.castShadow = true;
        const forkR = new THREE.Mesh(forkGeo, carriageMat);
        forkR.position.set(forkSpanX, -0.02, 0);
        forkR.castShadow = true;
        palletGroup3d.add(forkL, forkR);

        // Cross carriage beam connecting forks under center of pallet
        const crossCarriageGeo = new THREE.BoxGeometry(1.22, 0.05, 0.18);
        const crossCarriage = new THREE.Mesh(crossCarriageGeo, carriageMat);
        crossCarriage.position.set(0, -0.02, 0);
        crossCarriage.castShadow = true;
        palletGroup3d.add(crossCarriage);

        // Side guide brackets sliding along the column guide rails at X: -0.61 and +0.61
        const bracketGeo = new THREE.BoxGeometry(0.08, 0.14, 0.10);
        const bracketL = new THREE.Mesh(bracketGeo, yellowHazardMat);
        bracketL.position.set(-0.61, -0.02, 0);
        bracketL.castShadow = true;
        const bracketR = new THREE.Mesh(bracketGeo, yellowHazardMat);
        bracketR.position.set(0.61, -0.02, 0);
        bracketR.castShadow = true;
        palletGroup3d.add(bracketL, bracketR);

        // Add authentic full wooden pallet on elevator forks
        const elevatorPallet = create3dFullEuroPalletMesh(isIndustrial, woodMat);
        palletGroup3d.add(elevatorPallet);
    }

    // ─────────────────────────────────────────────────────────────
    // DYNAMIC SACK TEXTURE GENERATOR (AGRONETZWERK BRANDING & ACTIVE ORDER)
    // ─────────────────────────────────────────────────────────────
    let currentActiveOrder = {
        product_name: 'KREDA NAWOZOWA AGRO GRANULOWANA',
        batch_number: 'LOT-20260906-001',
        production_date: '2026-09-06',
        expiry_date: '2028-09-05',
        weight_kg: 25.0,
        brand: 'AGRONETZWERK',
        sub_brand: 'AGRO PREMIUM FERTILIZERS'
    };

    // Cached procedural canvas textures for realistic bulk product sacks
    let sackTextureNormal = null;
    let sackTextureRotated = null;
    let sackTextureLatest = null;
    let sackTextureLatestRotated = null;

    function resetSackTextureCache() {
        sackTextureNormal = null;
        sackTextureRotated = null;
        sackTextureLatest = null;
        sackTextureLatestRotated = null;
    }

    // Draws Agronetzwerk vector logo badge (emerald leaf & network nodes) on 2D context
    function drawAgronetzwerkLogo(ctx, cx, cy, scale) {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(scale, scale);

        // Outer Hexagonal / Shield Badge
        ctx.fillStyle = '#065f46';
        ctx.beginPath();
        ctx.moveTo(0, -32);
        ctx.lineTo(28, -16);
        ctx.lineTo(28, 16);
        ctx.lineTo(0, 32);
        ctx.lineTo(-28, 16);
        ctx.lineTo(-28, -16);
        ctx.closePath();
        ctx.fill();

        // Inner glowing border
        ctx.strokeStyle = '#34d399';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Leaf / Crop Plant Emblem
        ctx.fillStyle = '#10b981';
        ctx.beginPath();
        ctx.moveTo(0, -20);
        ctx.quadraticCurveTo(16, -10, 12, 14);
        ctx.quadraticCurveTo(0, 24, 0, 24);
        ctx.quadraticCurveTo(0, 24, -12, 14);
        ctx.quadraticCurveTo(-16, -10, 0, -20);
        ctx.fill();

        // Central leaf vein & network nodes
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, 22);
        ctx.lineTo(0, -14);
        ctx.moveTo(0, 4);
        ctx.lineTo(8, -4);
        ctx.moveTo(0, 12);
        ctx.lineTo(-8, 4);
        ctx.stroke();

        // Golden connection node points
        ctx.fillStyle = '#fbbf24';
        for (let pt of [[0, -14], [8, -4], [-8, 4], [0, 22]]) {
            ctx.beginPath();
            ctx.arc(pt[0], pt[1], 2.5, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.restore();
    }

    function generateSackCanvasTexture(isLatest, isRotated) {
        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 512;
        const ctx = canvas.getContext('2d');

        const order = currentActiveOrder || {};
        const prodName = String(order.product_name || 'KREDA NAWOZOWA AGRO GRANULOWANA').toUpperCase();
        const batchNo = String(order.batch_number || 'LOT-20260906-01');
        const prodDate = String(order.production_date || '2026-09-06');
        const expDate = String(order.expiry_date || '2028-09-05');
        const weightKg = (order.weight_kg || 25.0).toFixed(1);

        // Background: Clean Multi-wall Kraft / Industrial Packaging Paper
        ctx.fillStyle = isLatest ? '#e0f2fe' : '#f8fafc';
        ctx.fillRect(0, 0, 512, 512);

        // Subtle paper fiber grain noise
        for (let i = 0; i < 4500; i++) {
            const rx = Math.random() * 512;
            const ry = Math.random() * 512;
            ctx.fillStyle = (Math.random() > 0.5) ? 'rgba(0,0,0,0.025)' : 'rgba(255,255,255,0.05)';
            ctx.fillRect(rx, ry, 2, 2);
        }

        // Top & Bottom stitched seam bands (przeszycie nicią / zgrzewy przemysłowe)
        const seamColor = isLatest ? '#0284c7' : '#047857';
        ctx.fillStyle = seamColor;
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
            // ──────────────── HORIZONTAL ORIENTATION (Normal Sack) ────────────────
            // Top Green Brand Banner
            ctx.fillStyle = '#065f46';
            ctx.fillRect(34, 40, 444, 76);

            // Draw Agronetzwerk Brand Logo & Name
            drawAgronetzwerkLogo(ctx, 80, 78, 0.9);
            ctx.fillStyle = '#ffffff';
            ctx.font = '900 28px "Montserrat", "Arial Black", sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText('AGRONETZWERK', 125, 78);
            ctx.fillStyle = '#34d399';
            ctx.font = 'bold 12px monospace';
            ctx.fillText('AGRO PREMIUM CROP NUTRITION & FERTILIZERS', 125, 98);

            // Central Product Name Ribbon
            ctx.fillStyle = isLatest ? '#0284c7' : '#047857';
            ctx.fillRect(34, 130, 444, 150);

            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';

            // Split and wrap product name cleanly
            if (prodName.length > 24) {
                const words = prodName.split(' ');
                const mid = Math.ceil(words.length / 2);
                const line1 = words.slice(0, mid).join(' ');
                const line2 = words.slice(mid).join(' ');
                ctx.font = '900 25px sans-serif';
                ctx.fillText(line1, 256, 175);
                ctx.fillText(line2, 256, 210);
            } else {
                ctx.font = '900 30px sans-serif';
                ctx.fillText(prodName, 256, 190);
            }

            ctx.fillStyle = '#fef08a'; // Bright yellow badge
            ctx.font = '900 22px sans-serif';
            ctx.fillText(`● MASA NETTO: ${weightKg} kg ●`, 256, 255);

            // Bottom Traceability & Industrial Batch Box
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(40, 298, 432, 168);
            ctx.strokeStyle = '#cbd5e1';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(40, 298, 432, 168);

            ctx.fillStyle = '#0f172a';
            ctx.textAlign = 'left';
            ctx.font = '900 15px monospace';
            ctx.fillText(`PARTIA / LOT: ${batchNo}`, 58, 332);

            ctx.font = 'bold 14px monospace';
            ctx.fillStyle = '#334155';
            ctx.fillText(`DATA PRODUKCJI: ${prodDate}`, 58, 362);
            ctx.fillText(`NAJLEPIEJ ZUŻYĆ PRZED: ${expDate}`, 58, 392);

            ctx.font = 'bold 12px monospace';
            ctx.fillStyle = '#64748b';
            ctx.fillText('NORMA: EN 197-1 CE ■ ISO 9001:2015 ■ PL', 58, 424);

            // Simulated Barcode on the bottom right
            ctx.fillStyle = '#0f172a';
            for (let bx = 330; bx < 450; bx += 4) {
                const bWidth = (Math.sin(bx * 13) > 0) ? 2.5 : 1.2;
                ctx.fillRect(bx, 320, bWidth, 48);
            }
            ctx.font = '9px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(batchNo.replace(/[^0-9]/g, '').slice(0, 12) || '590123456789', 390, 380);

        } else {
            // ──────────────── VERTICAL 90° ROTATED ORIENTATION ────────────────
            ctx.save();
            ctx.translate(256, 256);
            ctx.rotate(Math.PI / 2);

            // Top Brand Banner
            ctx.fillStyle = '#065f46';
            ctx.fillRect(-222, -216, 444, 76);

            drawAgronetzwerkLogo(ctx, -176, -178, 0.9);
            ctx.fillStyle = '#ffffff';
            ctx.font = '900 28px "Montserrat", "Arial Black", sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText('AGRONETZWERK', -131, -178);
            ctx.fillStyle = '#34d399';
            ctx.font = 'bold 12px monospace';
            ctx.fillText('AGRO PREMIUM CROP NUTRITION & FERTILIZERS', -131, -158);

            // Central Product Name Ribbon
            ctx.fillStyle = isLatest ? '#0284c7' : '#047857';
            ctx.fillRect(-222, -126, 444, 150);

            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';

            if (prodName.length > 24) {
                const words = prodName.split(' ');
                const mid = Math.ceil(words.length / 2);
                const line1 = words.slice(0, mid).join(' ');
                const line2 = words.slice(mid).join(' ');
                ctx.font = '900 25px sans-serif';
                ctx.fillText(line1, 0, -81);
                ctx.fillText(line2, 0, -46);
            } else {
                ctx.font = '900 30px sans-serif';
                ctx.fillText(prodName, 0, -66);
            }

            ctx.fillStyle = '#fef08a';
            ctx.font = '900 22px sans-serif';
            ctx.fillText(`● MASA NETTO: ${weightKg} kg ●`, 0, -1);

            // Bottom Traceability & Batch Box
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(-216, 42, 432, 168);
            ctx.strokeStyle = '#cbd5e1';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(-216, 42, 432, 168);

            ctx.fillStyle = '#0f172a';
            ctx.textAlign = 'left';
            ctx.font = '900 15px monospace';
            ctx.fillText(`PARTIA / LOT: ${batchNo}`, -198, 76);

            ctx.font = 'bold 14px monospace';
            ctx.fillStyle = '#334155';
            ctx.fillText(`DATA PRODUKCJI: ${prodDate}`, -198, 106);
            ctx.fillText(`NAJLEPIEJ ZUŻYĆ PRZED: ${expDate}`, -198, 136);

            ctx.font = 'bold 12px monospace';
            ctx.fillStyle = '#64748b';
            ctx.fillText('NORMA: EN 197-1 CE ■ ISO 9001:2015 ■ PL', -198, 168);

            // Simulated Barcode
            ctx.fillStyle = '#0f172a';
            for (let bx = 74; bx < 194; bx += 4) {
                const bWidth = (Math.sin(bx * 13) > 0) ? 2.5 : 1.2;
                ctx.fillRect(bx, 64, bWidth, 48);
            }
            ctx.font = '9px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(batchNo.replace(/[^0-9]/g, '').slice(0, 12) || '590123456789', 134, 124);

            ctx.restore();
        }

        const texture = new THREE.CanvasTexture(canvas);
        texture.anisotropy = 4;
        return texture;
    }

    // Creates deformed pillow geometry simulating natural bulk powder/granule settling & internal pressure
    function createBulkSackGeometry(w, h, l) {
        const geo = new THREE.BoxGeometry(w, h, l, 16, 6, 16);
        const pos = geo.attributes.position;
        const halfW = w / 2;
        const halfH = h / 2;
        const halfL = l / 2;

        for (let i = 0; i < pos.count; i++) {
            let x = pos.getX(i);
            let y = pos.getY(i);
            let z = pos.getZ(i);

            const nx = x / halfW; // -1 .. 1
            const ny = y / halfH; // -1 .. 1
            const nz = z / halfL; // -1 .. 1

            // 1. Pillow bulge on top and bottom face
            if (ny > 0.4) {
                const centerBulge = Math.cos(nx * Math.PI * 0.46) * Math.cos(nz * Math.PI * 0.46);
                y += centerBulge * (h * 0.32);
            }

            pos.setXYZ(i, x, y, z);
        }
        geo.computeVertexNormals();
        return geo;
    }

    // Creates an ultra-realistic industrial bulk product sack with natural pillow shape and valve details
    function create3dBagMesh(width, height, length, isLatest, isRotated) {
        const bagGroup = new THREE.Group();

        // Lazy initialize canvas textures
        if (!sackTextureNormal) {
            sackTextureNormal = generateSackCanvasTexture(false, false);
            sackTextureRotated = generateSackCanvasTexture(false, true);
            sackTextureLatest = generateSackCanvasTexture(true, false);
            sackTextureLatestRotated = generateSackCanvasTexture(true, true);
        }

        const mapTex = isLatest 
            ? (isRotated ? sackTextureLatestRotated : sackTextureLatest)
            : (isRotated ? sackTextureRotated : sackTextureNormal);

        const sackGeo = createBulkSackGeometry(width, height, length);
        const sackMat = new THREE.MeshStandardMaterial({
            map: mapTex,
            roughness: 0.82,
            metalness: 0.05,
            emissive: isLatest ? 0x0284c7 : 0x000000,
            emissiveIntensity: isLatest ? 0.20 : 0.0
        });

        const sackMesh = new THREE.Mesh(sackGeo, sackMat);
        sackMesh.castShadow = true;
        sackMesh.receiveShadow = true;
        bagGroup.add(sackMesh);

        return bagGroup;
    }

    // Rebuilds 3D Stacking: Pallet holds actual completed layers; Upper conveyor and split plate hold active bags
    function rebuild3dBags(currentLayer, currentBag, isLineRunning, bpm, palletizerData, checkweigherData, baggerData) {
        if (!bagsGroup3d || !upperBagsGroup3d) return;
        bagsGroup3d.clear();
        upperBagsGroup3d.clear();
        bagsGroup3d.position.set(currentPalletX, currentPalletY, 0.18); // Follows dynamic elevator vertical and horizontal outfeed position

        const fullLayers = (palletizerData && palletizerData.full_layers) || currentConfig.full_layers || currentConfig.total_layers || 12;
        const bagsPerLayer = (palletizerData && palletizerData.bags_per_layer) || currentConfig.bags_per_layer || 4;
        const topLayerBags = (palletizerData && palletizerData.top_layer_bags !== undefined) ? palletizerData.top_layer_bags : (currentConfig.top_layer_bags !== undefined ? currentConfig.top_layer_bags : 2);

        const bagHeight = 0.095;
        const baseHeight = 0.144; // Top surface of wooden pallet

        // Exact Euro Pallet matching dimensions (0.80m x 1.20m)
        const bagW = 0.385; // 2 bags = 0.77m width (inside 0.80m pallet)
        const bagL = 0.585; // 2 bags = 1.17m length (inside 1.20m pallet)

        // 1. RENDER ACTUAL COMPLETED LAYERS ON THE PALLET (1 .. currentLayer - 1)
        const maxBagsInCurrent = (currentLayer > fullLayers) ? topLayerBags : bagsPerLayer;
        const fullyDepositedLayers = (currentBag >= maxBagsInCurrent) ? currentLayer : (currentLayer - 1);

        // DYNAMIC PALLET ELEVATOR HEIGHT (Winda paletyzatora) & HORIZONTAL ROLLER CONVEYOR OUTFEED:
        // When empty / waiting for layer 1 (fullyDepositedLayers <= 0), pallet is elevated at TOP (1.48m) at X: 0.
        // As layers accumulate, it steps down 95mm per layer.
        // On transfer / completion / oproznianie, it lowers to floor roller level (0.06m).
        // Once lowered, it smoothly rolls out horizontally along X (+2.45m) towards wrapper!
        const isTransferring = palletizerData && (palletizerData.status === 'TRANSFER' || palletizerData.status === 'DO ODBIORU' || palletizerData.is_emptying || palletizerData.wrapper_start_signal || (palletizerData.pallet_progress_percent >= 100 && fullyDepositedLayers >= fullLayers));
        if (isTransferring) {
            targetPalletY = 0.06;
            // Roll out along X roller conveyor towards stretch wrapper
            if (currentPalletY <= 0.35) {
                targetPalletX = 2.45;
            } else {
                targetPalletX = 0;
            }
        } else if (fullyDepositedLayers <= 0) {
            targetPalletY = 1.48; // Lifted high under split plates
            targetPalletX = 0;
        } else {
            targetPalletY = Math.max(0.06, 1.48 - (fullyDepositedLayers * bagHeight));
            targetPalletX = 0;
        }

        for (let l = 1; l <= fullyDepositedLayers; l++) {
            const isTopLayer = (l > fullLayers);
            const bagsInThisLayer = isTopLayer ? topLayerBags : bagsPerLayer;
            const layerY = baseHeight + (l - 1) * bagHeight + (bagHeight / 2);
            const isEvenLayer = (l % 2 === 0);

            for (let b = 1; b <= bagsInThisLayer; b++) {
                let posX = 0, posZ = 0;

                if (isTopLayer) {
                    if (topLayerBags === 2) { posX = (b === 1) ? -0.194 : 0.194; posZ = 0; }
                    else if (topLayerBags === 1) { posX = 0; posZ = 0; }
                    else { posX = (b % 2 === 0 ? 0.194 : -0.194); posZ = (b > 2 ? 0.294 : -0.294); }
                } else if (bagsPerLayer === 4) {
                    // Flush 2x2 grid forming perfectly straight walls
                    if (b === 1) { posX = -0.194; posZ = -0.294; }
                    else if (b === 2) { posX = 0.194; posZ = -0.294; }
                    else if (b === 3) { posX = 0.194; posZ = 0.294; }
                    else if (b === 4) { posX = -0.194; posZ = 0.294; }
                } else if (bagsPerLayer === 5) {
                    if (!isEvenLayer) {
                        if (b <= 3) { posX = (b - 2) * 0.24; posZ = -0.18; }
                        else { posX = (b === 4 ? -0.194 : 0.194); posZ = 0.27; }
                    } else {
                        if (b <= 2) { posX = (b === 1 ? -0.194 : 0.194); posZ = -0.27; }
                        else { posX = (b - 4) * 0.24; posZ = 0.18; }
                    }
                } else {
                    posX = (b % 2 === 0 ? 0.194 : -0.194);
                    posZ = (b > 2 ? 0.294 : -0.294);
                }

                const bagMesh = create3dBagMesh(
                    bagW,
                    bagHeight - 0.008,
                    bagL,
                    false,
                    isEvenLayer
                );

                bagMesh.position.set(posX, layerY, posZ);
                bagsGroup3d.add(bagMesh);
            }
        }

        // 2. RENDER INFEED CONVEYOR BAGS & STAGING (Strictly LIVE based on real-time sensors)
        const infeedZ = -0.78;
        const infeedY = 1.78 + (bagHeight / 2) + 0.02;

        const cwWeight = checkweigherData ? (checkweigherData.current_weight_kg || 0) : 0;
        const isBaggerProducing = Boolean(baggerData && baggerData.is_running && bpm > 0 && isLineRunning);
        const isJawsClosed = Boolean((baggerData && (baggerData.jaws_closed || baggerData.szczekiZamkniete)) || isBaggerJawsClosedAnim);
        const isScaleBagDetected = Boolean(checkweigherData && checkweigherData.bag_on_scale && isBaggerProducing);
        const isRejectActive = Boolean(checkweigherData && checkweigherData.reject_flap_open);
        const isTurnerActive = Boolean((palletizerData && (palletizerData.turner_active || palletizerData.obracakPraca || palletizerData.obracakAktywny)) || isTurnerActiveAnim);
        const isBufferOccupied = Boolean(palletizerData && (palletizerData.buffer_occupied || palletizerData.buforPelny));

        // 2a. SACK IN SEALING JAWS OF WAGOPAKOWACZKA (X: -6.20, Y: 0.82)
        // ONLY rendered while sealing jaws are actively closed (MQTT szczekiZamkniete)
        if (isJawsClosed) {
            const bagInJaws = create3dBagMesh(0.36, 0.50, 0.22, true, false);
            bagInJaws.position.set(-6.20, 0.82, infeedZ);
            upperBagsGroup3d.add(bagInJaws);
        }

        // 2b. SACK ON SHORT TAKEAWAY CONVEYOR (X: -5.55, Y: 0.42)
        // ONLY rendered when actively producing and a sack was just discharged from jaws
        if (isBaggerProducing && isJawsClosed) {
            const bagOnTakeaway = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, false, false);
            bagOnTakeaway.position.set(-5.55, 0.42, infeedZ);
            upperBagsGroup3d.add(bagOnTakeaway);
        }

        // 2c. SACK ON INCLINE CONVEYOR BELT (X: -4.45, Y: 1.125, Tilted +45.6°)
        // ONLY rendered when actively producing at nominal speed
        if (isBaggerProducing && bpm >= 6) {
            const bagOnIncline = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, false, false);
            bagOnIncline.position.set(-4.45, 1.125, infeedZ);
            bagOnIncline.rotation.z = 0.796;
            upperBagsGroup3d.add(bagOnIncline);
        }

        // 2d. SACK ON CHECKWEIGHER SCALE BED (X: -3.45)
        // ONLY rendered when actively producing and scale detects bag presence
        if (isScaleBagDetected && !isRejectActive) {
            const bagOnEntry = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, true, false);
            bagOnEntry.position.set(-3.45, infeedY, infeedZ);
            upperBagsGroup3d.add(bagOnEntry);
        }

        // 2e. Rejected bag dropping through chute if reject flap is active (X: -2.63)
        if (isRejectActive) {
            const rejectedBag = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, true, false);
            rejectedBag.rotation.z = -Math.PI / 4;
            rejectedBag.position.set(-2.63, 1.45, infeedZ);
            upperBagsGroup3d.add(rejectedBag);
        }

        // 2f. Intermediate extension belt (X: -1.75) - only if buffer sensor is active or continuous active flow
        if (isBufferOccupied || (bpm >= 10 && isBaggerProducing && (currentBag > 0 || currentLayer > 0))) {
            const bagOnMiddle = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, false, false);
            bagOnMiddle.position.set(-1.75, infeedY, infeedZ);
            upperBagsGroup3d.add(bagOnMiddle);
        }

        // 2g. Lead-in section (X: -1.40) - only in high throughput continuous flow
        if (bpm >= 14 && isBaggerProducing && currentBag > 0) {
            const bagOnLeadIn = create3dBagMesh(0.54, bagHeight - 0.008, 0.36, false, false);
            bagOnLeadIn.position.set(-1.40, infeedY, infeedZ);
            upperBagsGroup3d.add(bagOnLeadIn);
        }

        // Bag Turner with Overhead Clamping Jaws (X: -1.05) - strictly when turner is active
        if (isTurnerActive) {
            const isCurrentEven = (currentLayer % 2 === 0);
            const nextBagIdx = currentBag + 1;
            let turnerShouldRotate = false;
            if (bagsPerLayer === 4) {
                turnerShouldRotate = (!isCurrentEven && (nextBagIdx === 1 || nextBagIdx === 3)) || (isCurrentEven && (nextBagIdx === 2 || nextBagIdx === 4));
            }

            const bagOnTurner = create3dBagMesh(
                turnerShouldRotate ? 0.36 : 0.54,
                bagHeight - 0.008,
                turnerShouldRotate ? 0.54 : 0.36,
                currentBag === 0,
                turnerShouldRotate
            );
            bagOnTurner.position.set(-1.05, infeedY, infeedZ);
            upperBagsGroup3d.add(bagOnTurner);
        }

        // 3. RENDER BAGS ON RECEIVING CONVEYOR & SPLIT FORMATION PLATES
        if (currentLayer > 0 && currentBag > 0 && currentBag < maxBagsInCurrent) {
            const isTopLayer = (currentLayer > fullLayers);

            for (let b = 1; b <= currentBag; b++) {
                const isLatest = (b === currentBag);
                let posX = 0, posZ = 0;

                if (isTopLayer) {
                    posX = (b === 1 ? -0.194 : 0.194);
                    posZ = (b === currentBag ? infeedZ : 0.18);
                } else if (bagsPerLayer === 4) {
                    if (b === 1) { posX = -0.194; posZ = (currentBag === 1 ? infeedZ : -0.10); }
                    else if (b === 2) { posX = 0.194; posZ = (currentBag === 2 ? infeedZ : -0.10); }
                    else if (b === 3) { posX = 0.194; posZ = (currentBag === 3 ? infeedZ : 0.28); }
                    else if (b === 4) { posX = -0.194; posZ = (currentBag === 4 ? infeedZ : 0.28); }
                }

                const upperBag = create3dBagMesh(
                    bagW,
                    bagHeight - 0.008,
                    bagL,
                    isLatest,
                    isCurrentEven
                );

                upperBag.position.set(posX, upperY, posZ);
                upperBagsGroup3d.add(upperBag);
            }

            const isPushing = (currentBag === 2 || currentBag === 4);
            if (pusherPaddleMesh3d) pusherPaddleMesh3d.position.z = isPushing ? -0.15 : (infeedZ - 0.16);
            if (upperPlateLeft3d) upperPlateLeft3d.position.x = -0.25;
            if (upperPlateRight3d) upperPlateRight3d.position.x = 0.25;
        } else if (currentBag >= maxBagsInCurrent && currentLayer > 0) {
            if (pusherPaddleMesh3d) pusherPaddleMesh3d.position.z = infeedZ - 0.16;
            if (upperPlateLeft3d) upperPlateLeft3d.position.x = -0.52;
            if (upperPlateRight3d) upperPlateRight3d.position.x = 0.52;
        } else {
            if (pusherPaddleMesh3d) pusherPaddleMesh3d.position.z = infeedZ - 0.16;
            if (upperPlateLeft3d) upperPlateLeft3d.position.x = -0.25;
            if (upperPlateRight3d) upperPlateRight3d.position.x = 0.25;
        }
    }

    // ─────────────────────────────────────────────────────────────
    // 3D DIGITAL TWIN OWIJARKA (STRETCH WRAPPER, ROLLER CONVEYOR & TURNTABLE LIFT)
    // ─────────────────────────────────────────────────────────────
    let sceneWrapper3d, cameraWrapper3d, rendererWrapper3d, controlsWrapper3d;
    let turntableGroup3d, wrapperPalletGroup3d, mastGroup3d, carriageMesh3d, topSheetArmGroup3d;
    let foilCylinderMesh3d, topSheetCoverMesh3d, blokerGroup3d, turntableLiftPiston3d;
    let autoRotateWrapper3d = true;
    let wrapperSimInterval = null;
    let isWrapperRotating = false;
    let isWrapperElevated = false;
    let isBlokerLocked = false;

    function initWrapper3dScene() {
        const container = document.getElementById('wrapper3dCanvasContainer');
        if (!container || typeof THREE === 'undefined') return;

        const width = container.clientWidth || 360;
        const height = container.clientHeight || 230;

        sceneWrapper3d = new THREE.Scene();
        sceneWrapper3d.background = new THREE.Color(0x0b1120);

        cameraWrapper3d = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
        cameraWrapper3d.position.set(2.8, 2.4, 2.9);

        rendererWrapper3d = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        rendererWrapper3d.setSize(width, height);
        rendererWrapper3d.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        rendererWrapper3d.shadowMap.enabled = true;
        rendererWrapper3d.shadowMap.type = THREE.PCFSoftShadowMap;

        container.innerHTML = '';
        container.appendChild(rendererWrapper3d.domElement);

        if (typeof THREE.OrbitControls !== 'undefined') {
            controlsWrapper3d = new THREE.OrbitControls(cameraWrapper3d, rendererWrapper3d.domElement);
            controlsWrapper3d.enableDamping = true;
            controlsWrapper3d.dampingFactor = 0.05;
            controlsWrapper3d.maxPolarAngle = Math.PI / 2 + 0.05;
            controlsWrapper3d.minDistance = 1.0;
            controlsWrapper3d.maxDistance = 10.0;
            controlsWrapper3d.enablePan = true;
            controlsWrapper3d.screenSpacePanning = true;
            controlsWrapper3d.panSpeed = 1.2;
            controlsWrapper3d.mouseButtons = {
                LEFT: THREE.MOUSE.ROTATE,
                MIDDLE: THREE.MOUSE.DOLLY,
                RIGHT: THREE.MOUSE.PAN
            };
            controlsWrapper3d.touches = {
                ONE: THREE.TOUCH.ROTATE,
                TWO: THREE.TOUCH.DOLLY_PAN
            };
            controlsWrapper3d.target.set(0, 0.75, 0);
        }

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
        sceneWrapper3d.add(ambientLight);

        const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
        dirLight.position.set(4, 9, 4);
        dirLight.castShadow = true;
        sceneWrapper3d.add(dirLight);

        const emeraldFillLight = new THREE.DirectionalLight(0x10b981, 0.35);
        emeraldFillLight.position.set(-4, 3, -4);
        sceneWrapper3d.add(emeraldFillLight);

        const shadowPlaneGeo = new THREE.PlaneGeometry(6, 6);
        const shadowPlaneMat = new THREE.ShadowMaterial({ opacity: 0.15 });
        const shadowPlane = new THREE.Mesh(shadowPlaneGeo, shadowPlaneMat);
        shadowPlane.rotation.x = -Math.PI / 2;
        shadowPlane.position.y = -0.01;
        shadowPlane.receiveShadow = true;
        sceneWrapper3d.add(shadowPlane);

        turntableGroup3d = new THREE.Group();
        mastGroup3d = new THREE.Group();
        sceneWrapper3d.add(mastGroup3d);
        sceneWrapper3d.add(turntableGroup3d);

        build3dWrapperStationaryMast();
        build3dWrapperTurntable();
        // Note: Pallet on turntable will be rendered dynamically by renderWrapperSection based on ST4 telemetry

        function animateWrapper3d() {
            requestAnimationFrame(animateWrapper3d);
            if (controlsWrapper3d) {
                if (autoRotateWrapper3d && !isWrapperRotating) {
                    turntableGroup3d.rotation.y += 0.004;
                } else if (isWrapperRotating) {
                    turntableGroup3d.rotation.y += 0.035; // Wrapping rotation
                }
                controlsWrapper3d.update();
            }
            rendererWrapper3d.render(sceneWrapper3d, cameraWrapper3d);
        }
        animateWrapper3d();

        window.addEventListener('resize', onWrapper3dWindowResize);
    }

    function onWrapper3dWindowResize() {
        const container = document.getElementById('wrapper3dCanvasContainer');
        if (!container || !cameraWrapper3d || !rendererWrapper3d) return;
        const width = container.clientWidth;
        const height = container.clientHeight;
        cameraWrapper3d.aspect = width / height;
        cameraWrapper3d.updateProjectionMatrix();
        rendererWrapper3d.setSize(width, height);
    }

    // Build Vertical Mast Column, Full Continuous Roller Conveyor & Pneumatic Stopper (Bloker)
    function build3dWrapperStationaryMast() {
        if (!mastGroup3d) return;
        mastGroup3d.clear();

        const steelMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.5, metalness: 0.6 });
        const yellowMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.4, metalness: 0.3 });
        const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.2, metalness: 0.8 });
        const hazardMat = new THREE.MeshStandardMaterial({ color: 0xef4444, roughness: 0.3 });

        // Base Mast Column (Positioned at X: 0.85, Z: -0.75)
        const mastX = 0.85, mastZ = -0.75;
        const mastGeo = new THREE.BoxGeometry(0.16, 2.1, 0.16);
        const mastMesh = new THREE.Mesh(mastGeo, steelMat);
        mastMesh.position.set(mastX, 1.05, mastZ);
        mastMesh.castShadow = true;
        mastGroup3d.add(mastMesh);

        // Guide Rails
        const railGeo = new THREE.CylinderGeometry(0.015, 0.015, 2.0, 16);
        const rail1 = new THREE.Mesh(railGeo, chromeMat); rail1.position.set(mastX - 0.06, 1.05, mastZ + 0.08);
        const rail2 = new THREE.Mesh(railGeo, chromeMat); rail2.position.set(mastX + 0.06, 1.05, mastZ + 0.08);
        mastGroup3d.add(rail1, rail2);

        // Top Sheet Overhead Applicator Arm
        topSheetArmGroup3d = new THREE.Group();
        const armBeamGeo = new THREE.BoxGeometry(1.0, 0.06, 0.08);
        const armBeam = new THREE.Mesh(armBeamGeo, yellowMat);
        armBeam.position.set(mastX - 0.45, 1.95, mastZ + 0.65);
        armBeam.castShadow = true;
        topSheetArmGroup3d.add(armBeam);

        // Top Sheet Dispenser Roll
        const topRollGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.9, 16);
        const filmRollMat = new THREE.MeshStandardMaterial({
            color: 0x38bdf8,
            roughness: 0.3,
            metalness: 0.1,
            transparent: true,
            opacity: 0.85
        });
        const topRoll = new THREE.Mesh(topRollGeo, filmRollMat);
        topRoll.rotation.x = Math.PI / 2;
        topRoll.position.set(mastX - 0.45, 1.92, mastZ + 0.65);
        topSheetArmGroup3d.add(topRoll);
        mastGroup3d.add(topSheetArmGroup3d);

        // Movable Carriage with stretch film roll
        carriageMesh3d = new THREE.Group();
        const carriageBodyGeo = new THREE.BoxGeometry(0.24, 0.32, 0.22);
        const carriageBody = new THREE.Mesh(carriageBodyGeo, yellowMat);
        carriageBody.position.set(0, 0, 0);
        carriageBody.castShadow = true;
        carriageMesh3d.add(carriageBody);

        const filmRollGeo = new THREE.CylinderGeometry(0.065, 0.065, 0.5, 20);
        const filmRoll = new THREE.Mesh(filmRollGeo, filmRollMat);
        filmRoll.position.set(-0.12, 0, 0.08);
        filmRoll.castShadow = true;
        carriageMesh3d.add(filmRoll);

        const tensionRollerGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.5, 12);
        const tensionRoller = new THREE.Mesh(tensionRollerGeo, chromeMat);
        tensionRoller.position.set(-0.18, 0, 0.14);
        carriageMesh3d.add(tensionRoller);

        carriageMesh3d.position.set(mastX, 0.3, mastZ + 0.08);
        mastGroup3d.add(carriageMesh3d);

        // ─────────────────────────────────────────────────────────────
        // FULL CONTINUOUS ROLLER CONVEYOR (ROLKOWIEC: WJAZD • STACJA • WYJAZD)
        // ─────────────────────────────────────────────────────────────
        const rollerBedLeft = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 3.8), steelMat);
        rollerBedLeft.position.set(-0.64, 0.04, 0);
        const rollerBedRight = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 3.8), steelMat);
        rollerBedRight.position.set(0.64, 0.04, 0);
        mastGroup3d.add(rollerBedLeft, rollerBedRight);

        // Driven Rollers along the entire conveyor track
        const wrapRollerGeo = new THREE.CylinderGeometry(0.024, 0.024, 1.20, 16);
        const rollerPositionsZ = [
            -1.75, -1.55, -1.35, -1.15, -0.95, -0.75,
            -0.50, -0.25, 0.0, 0.25, 0.50,
            0.75, 0.95, 1.15, 1.35, 1.55, 1.75
        ];

        for (let rz of rollerPositionsZ) {
            const wRoller = new THREE.Mesh(wrapRollerGeo, chromeMat);
            wRoller.rotation.z = Math.PI / 2;
            wRoller.position.set(0, 0.065, rz);
            wRoller.castShadow = true;
            mastGroup3d.add(wRoller);
        }

        // ─────────────────────────────────────────────────────────────
        // PNEUMATIC STOPPER / BLOKER MECHANISM (BLOKER POZYCJI PALETY)
        // ─────────────────────────────────────────────────────────────
        blokerGroup3d = new THREE.Group();
        const pinGeo = new THREE.CylinderGeometry(0.025, 0.025, 0.12, 16);
        const pinL = new THREE.Mesh(pinGeo, hazardMat); pinL.position.set(-0.35, 0.06, 0.62);
        const pinR = new THREE.Mesh(pinGeo, hazardMat); pinR.position.set(0.35, 0.06, 0.62);
        const pinBar = new THREE.Mesh(new THREE.BoxGeometry(0.80, 0.02, 0.04), yellowMat);
        pinBar.position.set(0, 0.10, 0.62);
        blokerGroup3d.add(pinL, pinR, pinBar);
        blokerGroup3d.position.y = -0.06; // retracted by default
        mastGroup3d.add(blokerGroup3d);
    }

    // Build Turntable and Small Lift Mechanism (Winda stołu obrotowego unoszona spomiędzy rolek)
    function build3dWrapperTurntable() {
        if (!turntableGroup3d) return;
        turntableGroup3d.clear();

        const tableMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.4, metalness: 0.7 });
        const tableEdgeMat = new THREE.MeshStandardMaterial({ color: 0x10b981, roughness: 0.3, metalness: 0.5 });
        const steelMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.6 });
        const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.2, metalness: 0.8 });

        // Hydraulic Scissor / Piston Lift Column Under Turntable
        turntableLiftPiston3d = new THREE.Group();
        const pistonBase = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.04, 0.40), steelMat);
        pistonBase.position.y = 0.02;
        const pistonShaft = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.18, 24), chromeMat);
        pistonShaft.position.y = 0.08;
        turntableLiftPiston3d.add(pistonBase, pistonShaft);
        turntableGroup3d.add(turntableLiftPiston3d);

        // Turntable Platform (1.65m diameter)
        const tableGeo = new THREE.CylinderGeometry(0.82, 0.82, 0.05, 48);
        const tableMesh = new THREE.Mesh(tableGeo, tableMat);
        tableMesh.position.y = 0.07;
        tableMesh.receiveShadow = true;
        tableMesh.castShadow = true;
        turntableGroup3d.add(tableMesh);

        const ringGeo = new THREE.TorusGeometry(0.81, 0.015, 12, 48);
        const ringMesh = new THREE.Mesh(ringGeo, tableEdgeMat);
        ringMesh.rotation.x = Math.PI / 2;
        ringMesh.position.y = 0.095;
        turntableGroup3d.add(ringMesh);
    }

    // Build Realistic Pallet and Loaded Stack on Turntable
    function build3dPalletOnTurntable(layersCount, topBagsCount) {
        if (!turntableGroup3d) return;

        if (wrapperPalletGroup3d) {
            turntableGroup3d.remove(wrapperPalletGroup3d);
        }

        wrapperPalletGroup3d = new THREE.Group();
        const woodMat = new THREE.MeshStandardMaterial({ color: 0xc89d66, roughness: 0.8, metalness: 0.1 });
        const isIndustrial = !String(currentConfig.pallet_type || '').toUpperCase().includes('EURO');

        if (isIndustrial) {
            const topBoardWidths = [0.145, 0.100, 0.100, 0.145, 0.100, 0.100, 0.145];
            const topBoardX = [-0.4275, -0.285, -0.1425, 0, 0.1425, 0.285, 0.4275];
            for (let i = 0; i < 7; i++) {
                const boardGeo = new THREE.BoxGeometry(topBoardWidths[i], 0.022, 1.2);
                const board = new THREE.Mesh(boardGeo, woodMat);
                board.position.set(topBoardX[i], 0.133, 0);
                board.castShadow = true;
                wrapperPalletGroup3d.add(board);
            }
            for (let pos of [-0.5, 0, 0.5]) {
                const crossGeo = new THREE.BoxGeometry(1.0, 0.022, 0.145);
                const crossBoard = new THREE.Mesh(crossGeo, woodMat);
                crossBoard.position.set(0, 0.111, pos);
                crossBoard.castShadow = true;
                wrapperPalletGroup3d.add(crossBoard);
            }
            for (let bx of [-0.425, 0, 0.425]) {
                for (let bz of [-0.5, 0, 0.5]) {
                    const blockGeo = new THREE.BoxGeometry(0.145, 0.078, 0.145);
                    const block = new THREE.Mesh(blockGeo, woodMat);
                    block.position.set(bx, 0.061, bz);
                    block.castShadow = true;
                    wrapperPalletGroup3d.add(block);
                }
                const botGeo = new THREE.BoxGeometry(0.145, 0.022, 1.2);
                const botBoard = new THREE.Mesh(botGeo, woodMat);
                botBoard.position.set(bx, 0.011, 0);
                wrapperPalletGroup3d.add(botBoard);
            }
        } else {
            const topBoardWidths = [0.145, 0.100, 0.145, 0.100, 0.145];
            const topBoardX = [-0.3275, -0.175, 0, 0.175, 0.3275];
            for (let i = 0; i < 5; i++) {
                const boardGeo = new THREE.BoxGeometry(topBoardWidths[i], 0.022, 1.2);
                const board = new THREE.Mesh(boardGeo, woodMat);
                board.position.set(topBoardX[i], 0.133, 0);
                board.castShadow = true;
                wrapperPalletGroup3d.add(board);
            }
            for (let pos of [-0.5, 0, 0.5]) {
                const crossGeo = new THREE.BoxGeometry(0.8, 0.022, 0.145);
                const crossBoard = new THREE.Mesh(crossGeo, woodMat);
                crossBoard.position.set(0, 0.111, pos);
                crossBoard.castShadow = true;
                wrapperPalletGroup3d.add(crossBoard);
            }
            for (let bx of [-0.325, 0, 0.325]) {
                for (let bz of [-0.5, 0, 0.5]) {
                    const blockGeo = new THREE.BoxGeometry(0.145, 0.078, 0.145);
                    const block = new THREE.Mesh(blockGeo, woodMat);
                    block.position.set(bx, 0.061, bz);
                    block.castShadow = true;
                    wrapperPalletGroup3d.add(block);
                }
                const botGeo = new THREE.BoxGeometry(0.145, 0.022, 1.2);
                const botBoard = new THREE.Mesh(botGeo, woodMat);
                botBoard.position.set(bx, 0.011, 0);
                wrapperPalletGroup3d.add(botBoard);
            }
        }

        const bagHeight = 0.095;
        const baseHeight = 0.144;
        const fullLayers = (layersCount !== undefined && layersCount !== null) ? layersCount : (currentConfig.full_layers || 12);
        const bagsPerLayer = currentConfig.bags_per_layer || 4;
        const topLayerBags = (topBagsCount !== undefined && topBagsCount !== null) ? topBagsCount : (currentConfig.top_layer_bags !== undefined ? currentConfig.top_layer_bags : 2);

        // Exact Euro Pallet matching dimensions (0.80m x 1.20m)
        const bagW = 0.385;
        const bagL = 0.585;

        for (let l = 1; l <= fullLayers; l++) {
            const isEven = (l % 2 === 0);
            const layerY = baseHeight + (l - 1) * bagHeight + (bagHeight / 2);

            for (let b = 1; b <= bagsPerLayer; b++) {
                let posX = 0, posZ = 0;

                if (bagsPerLayer === 4) {
                    if (b === 1) { posX = -0.194; posZ = -0.294; }
                    else if (b === 2) { posX = 0.194; posZ = -0.294; }
                    else if (b === 3) { posX = 0.194; posZ = 0.294; }
                    else if (b === 4) { posX = -0.194; posZ = 0.294; }
                } else if (bagsPerLayer === 5) {
                    if (!isEven) {
                        if (b <= 3) { posX = (b - 2) * 0.24; posZ = -0.18; }
                        else { posX = (b === 4 ? -0.194 : 0.194); posZ = 0.27; }
                    } else {
                        if (b <= 2) { posX = (b === 1 ? -0.194 : 0.194); posZ = -0.27; }
                        else { posX = (b - 4) * 0.24; posZ = 0.18; }
                    }
                } else {
                    posX = (b % 2 === 0 ? 0.194 : -0.194);
                    posZ = (b > 2 ? 0.294 : -0.294);
                }

                const bagMesh = create3dBagMesh(
                    bagW,
                    bagHeight - 0.008,
                    bagL,
                    false,
                    isEven
                );
                bagMesh.position.set(posX, layerY, posZ);
                wrapperPalletGroup3d.add(bagMesh);
            }
        }

        if (topLayerBags > 0 && fullLayers > 0) {
            const topLayerY = baseHeight + fullLayers * bagHeight + (bagHeight / 2);
            for (let b = 1; b <= topLayerBags; b++) {
                const topBagMesh = create3dBagMesh(
                    bagW,
                    bagHeight - 0.008,
                    bagL,
                    false,
                    true
                );
                topBagMesh.position.set(b === 1 ? -0.194 : 0.194, topLayerY, 0);
                wrapperPalletGroup3d.add(topBagMesh);
            }
        }

        wrapperPalletGroup3d.position.y = 0.095;
        turntableGroup3d.add(wrapperPalletGroup3d);

        build3dWrapperFoilAndCap(fullLayers, topLayerBags);
    }

    // Build Translucent Stretch Foil Envelope Mesh and Top Sheet Cover Cap
    let currentWrapperStackHeight = 1.35;

    function build3dWrapperFoilAndCap(actualLayers, actualTopBags) {
        if (!turntableGroup3d) return;

        if (foilCylinderMesh3d) turntableGroup3d.remove(foilCylinderMesh3d);
        if (topSheetCoverMesh3d) turntableGroup3d.remove(topSheetCoverMesh3d);

        const bagHeight = 0.095;
        const baseHeight = 0.144;
        const layers = (actualLayers !== undefined && actualLayers !== null) ? actualLayers : (currentConfig.full_layers || 12);
        const topBags = (actualTopBags !== undefined && actualTopBags !== null) ? actualTopBags : (currentConfig.top_layer_bags || 0);

        const stackHeight = (layers * bagHeight) + (topBags > 0 ? bagHeight : 0);
        currentWrapperStackHeight = Math.max(0.40, baseHeight + stackHeight);

        const isIndustrial = !String(currentConfig.pallet_type || '').toUpperCase().includes('EURO');
        const foilWidth = isIndustrial ? 1.02 : 0.80;
        const capWidth = isIndustrial ? 1.04 : 0.82;

        const foilGeo = new THREE.BoxGeometry(foilWidth, currentWrapperStackHeight, 1.20);
        const foilMat = new THREE.MeshStandardMaterial({
            color: 0xa5f3fc,
            transparent: true,
            opacity: 0.0,
            roughness: 0.1,
            metalness: 0.2
        });
        foilCylinderMesh3d = new THREE.Mesh(foilGeo, foilMat);
        foilCylinderMesh3d.position.set(0, 0.095 + (currentWrapperStackHeight / 2), 0);
        foilCylinderMesh3d.scale.set(1.01, 0.01, 1.01);
        turntableGroup3d.add(foilCylinderMesh3d);

        const capGeo = new THREE.BoxGeometry(capWidth, 0.08, 1.22);
        const capMat = new THREE.MeshStandardMaterial({
            color: 0x0284c7,
            transparent: true,
            opacity: 0.0,
            roughness: 0.2,
            metalness: 0.3
        });
        topSheetCoverMesh3d = new THREE.Mesh(capGeo, capMat);
        topSheetCoverMesh3d.position.set(0, 0.095 + currentWrapperStackHeight + 0.02, 0);
        turntableGroup3d.add(topSheetCoverMesh3d);
    }

    function updateWrapper3dVisuals(progressPct, topSheetApplied, topSheetActive, carriageHeightPct, isWrapping, isElevated, isBlocked) {
        isWrapperRotating = isWrapping || (progressPct > 0 && progressPct < 100);
        isWrapperElevated = (isElevated !== undefined) ? isElevated : (isWrapperRotating || (progressPct > 0 && progressPct < 100));
        isBlokerLocked = (isBlocked !== undefined) ? isBlocked : (isWrapperElevated || progressPct > 0);

        // Update Turntable Lift Position (Mała winda unosi stół o +120mm ponad rolki)
        if (turntableGroup3d) {
            const targetY = isWrapperElevated ? 0.12 : 0.0;
            turntableGroup3d.position.y += (targetY - turntableGroup3d.position.y) * 0.15;
        }

        // Update Pneumatic Stopper (Bloker wysuwa się przy pozycji palety)
        if (blokerGroup3d) {
            const targetBlokerY = isBlokerLocked ? 0.0 : -0.06;
            blokerGroup3d.position.y += (targetBlokerY - blokerGroup3d.position.y) * 0.2;
        }

        // Update Carriage Vertical Position
        if (carriageMesh3d) {
            const mastX = 0.85, mastZ = -0.75;
            const minY = 0.25;
            const maxY = Math.min(2.0, currentWrapperStackHeight + 0.25);
            const targetY = minY + ((carriageHeightPct / 100.0) * (maxY - minY));
            carriageMesh3d.position.set(mastX, targetY, mastZ + 0.08);
        }

        // Update Top Sheet Applicator Arm Position
        if (topSheetArmGroup3d) {
            const defaultArmY = 1.95;
            const targetCapY = currentWrapperStackHeight + 0.10;
            if (topSheetActive) {
                topSheetArmGroup3d.position.y = Math.min(0, targetCapY - defaultArmY);
            } else {
                topSheetArmGroup3d.position.y = 0;
            }
        }

        // Update Stretch Film Wrap Mesh
        if (foilCylinderMesh3d) {
            const pct = Math.min(100, Math.max(0, progressPct));
            if (pct <= 0) {
                foilCylinderMesh3d.material.opacity = 0.0;
                foilCylinderMesh3d.scale.set(1.01, 0.01, 1.01);
            } else {
                foilCylinderMesh3d.material.opacity = Math.min(0.55, 0.15 + (pct / 100.0) * 0.4);
                const scaleY = Math.max(0.05, pct / 100.0);
                foilCylinderMesh3d.scale.set(1.01, scaleY, 1.01);
                foilCylinderMesh3d.position.y = 0.095 + (scaleY * currentWrapperStackHeight) / 2;
            }
        }

        // Update Top Sheet Cover Mesh
        if (topSheetCoverMesh3d) {
            if (topSheetApplied || topSheetActive) {
                topSheetCoverMesh3d.material.opacity = 0.65;
            } else {
                topSheetCoverMesh3d.material.opacity = 0.0;
            }
        }
    }

    // Wrapper 3D View Controls
    let isWrapper3dPanMode = false;

    window.toggleWrapper3dPanMode = function() {
        if (!controlsWrapper3d) return;
        isWrapper3dPanMode = !isWrapper3dPanMode;
        const btn = document.getElementById('btnWrapperTogglePan');
        if (isWrapper3dPanMode) {
            controlsWrapper3d.mouseButtons.LEFT = THREE.MOUSE.PAN;
            controlsWrapper3d.mouseButtons.RIGHT = THREE.MOUSE.ROTATE;
            if (btn) {
                btn.classList.add('active');
                btn.innerHTML = '<span class="material-icons">pan_tool</span> PRZESUŃ (LPM)';
            }
        } else {
            controlsWrapper3d.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
            controlsWrapper3d.mouseButtons.RIGHT = THREE.MOUSE.PAN;
            if (btn) {
                btn.classList.remove('active');
                btn.innerHTML = '<span class="material-icons">pan_tool</span> PRZESUŃ';
            }
        }
    };

    window.toggleWrapper3dAutoRotate = function() {
        autoRotateWrapper3d = !autoRotateWrapper3d;
        const btn = document.getElementById('btnWrapperAutoRotate');
        if (btn) btn.classList.toggle('active', autoRotateWrapper3d);
    };

    window.setWrapper3dCameraView = function(view) {
        if (!cameraWrapper3d || !controlsWrapper3d) return;
        autoRotateWrapper3d = false;
        const btn = document.getElementById('btnWrapperAutoRotate');
        if (btn) btn.classList.remove('active');

        if (view === 'iso') {
            cameraWrapper3d.position.set(2.8, 2.4, 2.9);
        } else if (view === 'top') {
            cameraWrapper3d.position.set(0, 4.5, 0.01);
        }
        controlsWrapper3d.target.set(0, 0.75, 0);
        controlsWrapper3d.update();
    };

    window.resetWrapper3dCamera = function() {
        window.setWrapper3dCameraView('iso');
        if (turntableGroup3d) turntableGroup3d.rotation.y = 0;
    };

    window.switchWrapperView = function(mode) {
        const v3d = document.getElementById('wrapper3dWrapper');
        const v2d = document.getElementById('wrapper2dWrapper');
        const t3d = document.getElementById('tabWrapperView3d');
        const t2d = document.getElementById('tabWrapperView2d');

        if (mode === '3d') {
            if (v3d) v3d.style.display = 'flex';
            if (v2d) v2d.style.display = 'none';
            if (t3d) t3d.classList.add('active');
            if (t2d) t2d.classList.remove('active');
            setTimeout(onWrapper3dWindowResize, 50);
        } else {
            if (v3d) v3d.style.display = 'none';
            if (v2d) v2d.style.display = 'block';
            if (t3d) t3d.classList.remove('active');
            if (t2d) t2d.classList.add('active');
        }
    };

    // Live Test Simulation of Wrapper 3D Cycle (Rolkowiec -> Bloker -> Mała Winda -> Owijanie -> Opuszczenie -> Odjazd)
    window.simulateWrapperTestCycle = function() {
        if (wrapperSimInterval) {
            clearInterval(wrapperSimInterval);
            wrapperSimInterval = null;
        }

        let simPct = 0;
        isPaused = true;
        const btnPause = document.getElementById('btnPauseTerm');
        if (btnPause) { btnPause.innerText = 'WZNÓW'; btnPause.style.color = '#ef4444'; }

        wrapperSimInterval = setInterval(() => {
            simPct += 4;
            let phaseCode = 'IDLE', phaseLabel = 'Wjazd palety na rolkowiec';
            let topApplied = false, topActive = false, carriageH = 0;
            let isElev = false, isBlock = false;

            if (simPct <= 10) {
                phaseCode = 'INFEED_CONVEYOR';
                phaseLabel = '📦 Rolkowiec: Wjazd palety ze stanowiska paletyzatora';
                isBlock = true;
                isElev = false;
            } else if (simPct <= 20) {
                phaseCode = 'BLOKER_LIFT';
                phaseLabel = '🛑 Bloker: Pozycja zablokowana • Winda unosi paletę (+120mm)';
                isBlock = true;
                isElev = true;
            } else if (simPct <= 35) {
                phaseCode = 'BOTTOM_WRAP';
                phaseLabel = '🌀 Owinięcie dolnej podstawy palety na uniesionym stole';
                isBlock = true;
                isElev = true;
                carriageH = 0;
            } else if (simPct <= 55) {
                phaseCode = 'ASCENDING';
                phaseLabel = 'Wznoszenie wózka z folią stretch';
                isBlock = true;
                isElev = true;
                carriageH = (simPct - 35) * 5.0;
            } else if (simPct <= 70) {
                phaseCode = 'TOP_SHEET';
                phaseLabel = '🛡️ Nakładanie kapturka foliowego (Top Sheet)';
                isBlock = true;
                isElev = true;
                topActive = true;
                topApplied = true;
                carriageH = 100;
            } else if (simPct <= 85) {
                phaseCode = 'TOP_WRAP';
                phaseLabel = 'Owinięcie szczytu i zabezpieczenie kapturka';
                isBlock = true;
                isElev = true;
                topApplied = true;
                topActive = false;
                carriageH = 100;
            } else if (simPct < 95) {
                phaseCode = 'DESCENDING';
                phaseLabel = 'Zjazd wózka, odcięcie folii • Winda opuszcza paletę na rolki';
                isBlock = true;
                isElev = false;
                topApplied = true;
                carriageH = (95 - simPct) * 10;
            } else {
                phaseCode = 'DONE';
                phaseLabel = '✅ Bloker zwolniony • Paleta owinięta odjeżdża na odbiór';
                isBlock = false;
                isElev = false;
                topApplied = true;
                carriageH = 0;
            }

            const simulatedWrapper = {
                status: simPct >= 95 ? 'GOTOWA' : 'OWIJANIE',
                progress_percent: simPct,
                phase_code: phaseCode,
                phase_label: phaseLabel,
                top_sheet_applied: topApplied,
                top_sheet_active: topActive,
                rotations_count: Math.floor(simPct * 0.18),
                carriage_height_percent: carriageH,
                is_wrapped: simPct >= 95,
                ready_for_pickup: simPct >= 95,
                is_elevated: isElev,
                is_blocked: isBlock
            };

            renderWrapperSection(simulatedWrapper);
            updateWrapper3dVisuals(simPct, topApplied, topActive, carriageH, (simPct > 20 && simPct < 92), isElev, isBlock);

            if (simPct >= 100) {
                clearInterval(wrapperSimInterval);
                wrapperSimInterval = null;
                setTimeout(() => {
                    isPaused = false;
                    if (btnPause) { btnPause.innerText = 'PAUZA'; btnPause.style.color = ''; }
                }, 3000);
            }
        }, 650);
    };

    // Live Simulation of Checkweigher Reject Event
    window.simulateRejectTest = async function() {
        try {
            const testWeight = (23.80 + Math.random() * 0.4).toFixed(2);
            await fetch('/api/machines/rejects/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    weight_kg: parseFloat(testWeight),
                    target_weight_kg: 25.0,
                    reason_code: 'UNDERWEIGHT',
                    recipe_name: (typeof currentConfig !== 'undefined' && currentConfig.preset_name) ? currentConfig.preset_name : 'Mieszanka Agro 25kg'
                })
            });

            // Trigger 3D Drop Flap animation for 2.5 seconds
            if (typeof rejectFlapMesh3d !== 'undefined' && rejectFlapMesh3d) {
                rejectFlapMesh3d.rotation.z = -Math.PI / 4;
                const cwFlapBadge = document.getElementById('cwFlapStatusBadge');
                const cwWeight = document.getElementById('cwLiveWeight');
                if (cwWeight) {
                    cwWeight.innerHTML = `${testWeight} <span class="unit">kg</span>`;
                    cwWeight.className = 'cw-val highlight-magenta';
                }
                if (cwFlapBadge) {
                    cwFlapBadge.innerText = '⚠️ ZRZUT OTWARTY';
                    cwFlapBadge.className = 'status-pill praca';
                }
                setTimeout(() => {
                    if (rejectFlapMesh3d) rejectFlapMesh3d.rotation.z = 0;
                    if (cwFlapBadge) {
                        cwFlapBadge.innerText = 'ZAMKNIĘTY (OK)';
                        cwFlapBadge.className = 'status-pill ready';
                    }
                    fetchTelemetry();
                }, 2500);
            } else {
                fetchTelemetry();
            }
        } catch (e) {
            console.warn('Reject test error', e);
        }
    };

    // ─────────────────────────────────────────────────────────────
    // 2D LAYER GRID VISUALIZER
    // ─────────────────────────────────────────────────────────────
    function buildLayerGrid(totalLayers, bagsPerLayer, topLayerBags) {
        if (!stackContainer) return;
        stackContainer.innerHTML = '';
        
        for (let l = 1; l <= totalLayers; l++) {
            const layerEl = document.createElement('div');
            layerEl.className = 'layer-bar';
            layerEl.id = 'layerBar_' + l;
            
            const isTop = (topLayerBags > 0 && l === totalLayers);
            const bagsInThisLayer = isTop ? topLayerBags : bagsPerLayer;
            for (let b = 1; b <= bagsInThisLayer; b++) {
                const dot = document.createElement('div');
                dot.className = 'layer-bag-dot';
                dot.id = `layerBag_${l}_${b}`;
                layerEl.appendChild(dot);
            }
            stackContainer.appendChild(layerEl);
        }
    }

    async function loadPalletConfig() {
        try {
            const res = await fetch('/api/machines/palletizer/config');
            if (!res.ok) return;
            const payload = await res.json();
            if (payload.success && payload.data) {
                currentConfig = payload.data.config || currentConfig;
                availablePresets = payload.data.presets || [];
                renderPresets();
                applyConfigToUI();
                build3dEuroPallet();
                rebuild3dBags(current3dLayer, current3dBag, false, 0, null);
                if (typeof lastWrapperHasPallet !== 'undefined' && lastWrapperHasPallet && typeof build3dPalletOnTurntable === 'function') {
                    build3dPalletOnTurntable();
                    build3dWrapperFoilAndCap();
                }
            }
        } catch (e) {
            console.warn('Failed to load pallet config', e);
        }
    }

    function renderPresets() {
        const container = document.getElementById('presetChipsContainer');
        if (!container) return;
        container.innerHTML = '';

        const filteredPresets = availablePresets.filter(p => {
            if (!p.pallet_type) return selectedModalPallet === 'INDUSTRIAL_100x120';
            return p.pallet_type === selectedModalPallet;
        });

        if (filteredPresets.length === 0) {
            container.innerHTML = '<div style="font-size: 11px; color: var(--theme-text-muted);">Brak zdefiniowanych presetów dla tego typu palety. Możesz wprowadzić własne parametry poniżej.</div>';
            return;
        }

        filteredPresets.forEach(preset => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'preset-chip';
            chip.innerText = preset.name;
            chip.onclick = () => {
                document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                document.getElementById('cfgPresetName').value = preset.name;
                document.getElementById('cfgTotalLayers').value = preset.full_layers || preset.total_layers;
                document.getElementById('cfgBagsPerLayer').value = preset.bags_per_layer;
                document.getElementById('cfgTopLayerBags').value = preset.top_layer_bags || 0;
                if (preset.bag_weight_kg) document.getElementById('cfgBagWeight').value = preset.bag_weight_kg;
                updateModalPreview();
            };
            container.appendChild(chip);
        });
    }

    function applyConfigToUI() {
        const fullL = currentConfig.full_layers || currentConfig.total_layers || 12;
        const bagsPerL = currentConfig.bags_per_layer || 4;
        const topBags = currentConfig.top_layer_bags || 0;
        const totalL = fullL + (topBags > 0 ? 1 : 0);
        const totalB = (fullL * bagsPerL) + topBags;
        const isInd = (currentConfig.pallet_type !== 'EURO_80x120');
        const palletIcon = isInd ? '🏭' : '🇪🇺';
        const palletShort = currentConfig.pallet_short_name || (isInd ? 'Przemysłowa 100×120' : 'EURO 80×120');

        buildLayerGrid(totalL, bagsPerL, topBags);
        
        const summaryBadge = document.getElementById('palletSchemaSummaryText');
        if (summaryBadge) {
            summaryBadge.innerText = `${palletIcon} ${palletShort} • ${fullL}W × ${bagsPerL}szt` + (topBags > 0 ? ` + ${topBags}szt szczyt` : '') + ` • Cel: ${totalB} worków`;
        }
    }

    // ─────────────────────────────────────────────────────────────
    // TELEMETRY & LIVE POLLING
    // ─────────────────────────────────────────────────────────────
    async function fetchTelemetry() {
        if (isPaused) return;

        try {
            const res = await fetch('/api/machines/telemetry/live');
            if (!res.ok) return;
            const payload = await res.json();
            if (!payload.success || !payload.data) return;

            renderDashboard(payload.data);
        } catch (e) {
            console.warn('Telemetry poll error', e);
        }
    }

    function renderDashboard(data) {
        const broker = data.broker || {};
        const machines = data.machines || {};
        const bagger = machines.bagger || {};
        const palletizer = machines.palletizer || {};
        const wrapper = machines.wrapper || {};

        // 1. BROKER STATUS
        const dot = document.getElementById('brokerDot');
        const stText = document.getElementById('brokerStatusText');
        const msgCount = document.getElementById('brokerMsgCount');
        const latText = document.getElementById('brokerLatencyText');

        if (dot && stText) {
            if (broker.is_connected) {
                dot.className = 'hud-dot online pulsing';
                stText.innerText = 'ONLINE (Hela)';
                stText.style.color = '#10b981';
            } else {
                dot.className = 'hud-dot';
                stText.innerText = 'OFFLINE / CZUWANIE';
                stText.style.color = '#ef4444';
            }
        }
        if (msgCount) msgCount.innerText = broker.messages_total || 0;
        if (latText) latText.innerText = (broker.time_since_update_sec > 900 ? '>15 min' : (broker.time_since_update_sec + 's temu'));

        // 2. BAGGER
        const baggerBpm = document.getElementById('baggerBpm');
        const baggerTph = document.getElementById('baggerTonsPerHour');
        const baggerGlob = document.getElementById('baggerCounterGlobal');
        const baggerLoc = document.getElementById('baggerCounterLocal');
        const baggerRec = document.getElementById('baggerRecipe');
        const baggerSt = document.getElementById('baggerStatusBadge');
        const baggerBar = document.getElementById('baggerThroughputBar');

        if (baggerBpm) baggerBpm.innerText = bagger.bpm.toFixed(1);
        if (baggerTph) baggerTph.innerHTML = `${bagger.tons_per_hour.toFixed(2)} <span class="unit">t/h</span>`;
        if (baggerGlob) baggerGlob.innerHTML = `${bagger.counter_global} <span class="unit">szt</span>`;
        if (baggerLoc) baggerLoc.innerHTML = `${bagger.counter_local} <span class="unit">szt</span>`;
        if (baggerRec) baggerRec.innerText = bagger.recipe_name || 'Brak danych';
        
        if (baggerSt) {
            baggerSt.innerText = bagger.status;
            baggerSt.className = 'status-pill' + (bagger.is_running ? ' praca' : '');
        }
        const baggerJawsBadge = document.getElementById('baggerJawsBadge');
        if (baggerJawsBadge) {
            if (bagger.jaws_closed) {
                baggerJawsBadge.innerText = 'SZCZĘKI: ZAMKNIĘTE (ZGRZEW)';
                baggerJawsBadge.className = 'status-pill warn';
            } else {
                baggerJawsBadge.innerText = 'SZCZĘKI: OTWARTE';
                baggerJawsBadge.className = 'status-pill ready';
            }
        }
        if (baggerBar) {
            const pct = Math.min(100, Math.max(0, (bagger.bpm / 20.0) * 100));
            baggerBar.style.width = pct + '%';
        }

        // Update 3D Wagopakowaczka Signal Tower Beacon & Jaws State
        isBaggerJawsClosedAnim = Boolean(bagger && (bagger.jaws_closed || bagger.szczekiZamkniete));
        if (baggerBeaconGreen3d && baggerBeaconGreen3d.material) {
            if (bagger.is_running || (bagger.bpm && bagger.bpm > 0)) {
                baggerBeaconGreen3d.material.color.setHex(0x10b981);
                baggerBeaconGreen3d.material.emissive.setHex(0x059669);
                baggerBeaconGreen3d.material.emissiveIntensity = 0.95;
            } else if (bagger.status && (bagger.status.includes('ALARM') || bagger.status.includes('AWARIA'))) {
                baggerBeaconGreen3d.material.color.setHex(0x334155);
                baggerBeaconGreen3d.material.emissive.setHex(0x000000);
            } else {
                baggerBeaconGreen3d.material.color.setHex(0x334155);
                baggerBeaconGreen3d.material.emissive.setHex(0x000000);
            }
        }

        // 2b. CHECKWEIGHER & REJECT DROP FLAP
        const checkweigher = machines.checkweigher || {};
        const cwWeight = document.getElementById('cwLiveWeight');
        const cwTol = document.getElementById('cwToleranceText');
        const cwRejectCnt = document.getElementById('cwRejectCount');
        const cwFlapBadge = document.getElementById('cwFlapStatusBadge');
        const scaleBagBadge = document.getElementById('scaleBagDetectedBadge');

        if (cwWeight) {
            const curW = checkweigher.current_weight_kg || 0;
            cwWeight.innerHTML = `${curW.toFixed(2)} <span class="unit">kg</span>`;
            if (checkweigher.is_in_tolerance) {
                cwWeight.className = 'cw-val highlight-cyan';
            } else {
                cwWeight.className = 'cw-val highlight-magenta';
            }
        }
        if (cwTol) {
            cwTol.innerText = `${checkweigher.min_tolerance_kg || 24.75} - ${checkweigher.max_tolerance_kg || 25.25} kg`;
        }
        if (cwRejectCnt) {
            cwRejectCnt.innerHTML = `${checkweigher.reject_count_total || 0} <span class="unit">szt</span>`;
        }
        if (cwFlapBadge) {
            if (checkweigher.reject_flap_open) {
                cwFlapBadge.innerText = '⚠️ ZRZUT OTWARTY';
                cwFlapBadge.className = 'status-pill praca';
            } else {
                cwFlapBadge.innerText = 'ZAMKNIĘTY (OK)';
                cwFlapBadge.className = 'status-pill ready';
            }
        }
        if (scaleBagBadge) {
            const curW = checkweigher.current_weight_kg || 0;
            if (checkweigher.bag_on_scale || curW > 0.5) {
                scaleBagBadge.innerText = `WAGA: WYKRYTO (${curW.toFixed(2)} kg)`;
                scaleBagBadge.className = 'status-pill ready';
            } else {
                scaleBagBadge.innerText = 'WAGA: BRAK WORKA';
                scaleBagBadge.className = 'status-pill';
            }
        }

        // Animate 3D Reject Flap Trapdoor
        if (typeof rejectFlapMesh3d !== 'undefined' && rejectFlapMesh3d) {
            if (checkweigher.reject_flap_open) {
                rejectFlapMesh3d.rotation.z = -Math.PI / 4; // Drop down 45 degrees
            } else {
                rejectFlapMesh3d.rotation.z = 0; // Flat closed
            }
        }

        // 3. PALLETIZER 3D & 2D
        const palSt = document.getElementById('palletizerStatusBadge');
        const palProg = document.getElementById('palletizerProgressText');
        const palCount = document.getElementById('palletizerCounter');
        const palAccum = document.getElementById('palletizerAccumulatedCount');
        const curLayer = document.getElementById('valCurrentLayer');
        const curBag = document.getElementById('valCurrentBag');
        const emptySt = document.getElementById('valEmptyingStatus');
        const live3dText = document.getElementById('pallet3dLiveStatus');

        const fullLayers = palletizer.full_layers || currentConfig.full_layers || 12;
        const bagsPerLayer = palletizer.bags_per_layer || currentConfig.bags_per_layer || 4;
        const topLayerBags = palletizer.top_layer_bags !== undefined ? palletizer.top_layer_bags : (currentConfig.top_layer_bags || 0);
        const totalLayers = palletizer.total_layers || (fullLayers + (topLayerBags > 0 ? 1 : 0));
        const targetBags = palletizer.total_target_bags || ((fullLayers * bagsPerLayer) + topLayerBags);

        // 2c. ACTIVE BAGGING ORDER & 3D SACK TEXTURES (AGRONETZWERK & DYNAMIC PRODUCT)
        if (data.active_order && data.active_order.product_name) {
            const orderChanged = !currentActiveOrder ||
                currentActiveOrder.product_name !== data.active_order.product_name ||
                currentActiveOrder.batch_number !== data.active_order.batch_number ||
                currentActiveOrder.production_date !== data.active_order.production_date ||
                currentActiveOrder.expiry_date !== data.active_order.expiry_date;

            if (orderChanged) {
                currentActiveOrder = data.active_order;
                resetSackTextureCache();
            }
        }

        const newLayer = palletizer.current_layer || 0;
        const newBag = palletizer.current_bag || 0;
        const currentBpm = (bagger && bagger.bpm) ? bagger.bpm : 0;
        const isBaggerRunning = Boolean(bagger && bagger.is_running && currentBpm > 0);
        const isPalletizerRunning = Boolean(palletizer && palletizer.status === 'PRACA');
        const isLineRunning = Boolean(isBaggerRunning || isPalletizerRunning);
        const cw = machines.checkweigher || {};
        const cwHasBag = Boolean(cw.bag_on_scale && isBaggerRunning);
        const cwRejectOpen = Boolean(cw.reject_flap_open);
        const turnerActive = Boolean(palletizer.turner_active || palletizer.obracakPraca || palletizer.obracakAktywny);
        const pusherActive = Boolean(palletizer.pusher_active || palletizer.popychaczPraca || palletizer.popychaczAktywny);
        const baggerJawsClosed = Boolean(bagger && (bagger.jaws_closed || bagger.szczekiZamkniete));
        const scaleBagDetected = Boolean(cw && cw.bag_on_scale && isBaggerRunning);

        const currentPalletizerStateKey = `${newLayer}_${newBag}_${palletizer.status}_${currentBpm}_${cwHasBag ? 1 : 0}_${cwRejectOpen ? 1 : 0}_${turnerActive ? 1 : 0}_${pusherActive ? 1 : 0}_${palletizer.accumulated_bags}_${baggerJawsClosed ? 1 : 0}_${scaleBagDetected ? 1 : 0}_${isLineRunning ? 1 : 0}`;

        // Update 3D model if layer, bag, status, checkweigher or machine movements changed
        if (typeof lastPalletizer3dState === 'undefined' || currentPalletizerStateKey !== lastPalletizer3dState) {
            lastPalletizer3dState = currentPalletizerStateKey;
            current3dLayer = newLayer;
            current3dBag = newBag;
            rebuild3dBags(current3dLayer, current3dBag, isLineRunning, currentBpm, palletizer, cw, bagger);
        }

        if (live3dText) {
            const isTop = (current3dLayer > fullLayers);
            const maxB = isTop ? topLayerBags : bagsPerLayer;
            const infeedCount = (cwHasBag ? 1 : 0) + (turnerActive ? 1 : 0) + (isBaggerRunning && currentBpm >= 6 ? 1 : 0);
            const infeedText = infeedCount > 0 ? `${infeedCount} szt` : 'PUSTA';
            const elevMm = Math.round(currentPalletY * 1000);
            const elevLabel = currentPalletY > 1.2 ? `GÓRA (${elevMm}mm)` : (currentPalletY < 0.2 ? `DÓŁ (${elevMm}mm)` : `${elevMm}mm`);
            const stText = palletizer.status || 'CZUWANIE';
            const outfeedText = (currentPalletX > 0.3) ? ' • WYJAZD NA ROLOTOK' : '';
            live3dText.innerText = `STAN: ${stText}${outfeedText} • TAŚMA: ${infeedText} • WINDA: ${elevLabel} • STÓŁ: ${current3dBag}/${maxB} • PALETA: ${palletizer.accumulated_bags || 0}/${targetBags} (${palletizer.pallet_progress_percent || 0}%) • W: ${current3dLayer}/${totalLayers}`;
        }

        if (stackContainer && stackContainer.children.length !== totalLayers) {
            buildLayerGrid(totalLayers, bagsPerLayer, topLayerBags);
        }

        if (palSt) {
            palSt.innerText = palletizer.status;
            palSt.className = 'status-pill' + (palletizer.status === 'PRACA' ? ' praca' : '');
        }
        if (palProg) palProg.innerText = palletizer.pallet_progress_percent + '%';
        if (palAccum) palAccum.innerText = `${palletizer.accumulated_bags || 0} / ${targetBags} worków`;
        if (palCount) palCount.innerHTML = `${palletizer.pallets_completed_global} <span class="unit">pal</span>`;
        if (curLayer) curLayer.innerText = `${palletizer.current_layer} / ${totalLayers}`;
        
        const isTop = (palletizer.current_layer > fullLayers);
        const maxBagInThisLayer = isTop ? topLayerBags : bagsPerLayer;
        if (curBag) curBag.innerText = `${palletizer.current_bag} / ${maxBagInThisLayer}`;
        if (emptySt) emptySt.innerText = palletizer.is_emptying ? 'OPRÓŻNIANIE...' : 'NORMALNE';

        // Update 2D layer dots
        for (let l = 1; l <= totalLayers; l++) {
            const isTopL = (l > fullLayers);
            const maxB = isTopL ? topLayerBags : bagsPerLayer;
            for (let b = 1; b <= maxB; b++) {
                const dotEl = document.getElementById(`layerBag_${l}_${b}`);
                if (!dotEl) continue;
                if (l < palletizer.current_layer) {
                    dotEl.className = 'layer-bag-dot filled';
                } else if (l === palletizer.current_layer && b <= palletizer.current_bag) {
                    dotEl.className = 'layer-bag-dot filled';
                } else {
                    dotEl.className = 'layer-bag-dot';
                }
            }
        }

        // 4. WRAPPER (3D DIGITAL TWIN & TELEMETRY)
        renderWrapperSection(wrapper, data.pallet_stations || []);

        // 5. PALLET LOGISTICS (5-STATION PIPELINE)
        renderPalletStations(data.pallet_stations || []);

        // ── MQTT PROCESS FLOW REAL-TIME STATE TRACKING (MQTT_PROCESS_FLOW.md) ──
        isBaggerJawsClosedAnim = Boolean(bagger && (bagger.jaws_closed || bagger.szczekiZamkniete));
        if (baggerBeaconGreen3d && baggerBeaconGreen3d.material) {
            baggerBeaconGreen3d.material.emissiveIntensity = (bagger.is_running ? 0.9 : 0.1);
        }
        isTurnerActiveAnim = Boolean(palletizer.turner_active || palletizer.obracakPraca || palletizer.obracakAktywny);
        isPusherActiveAnim = Boolean(palletizer.pusher_active || palletizer.popychaczPraca || palletizer.popychaczAktywny);
        isTransferActiveAnim = Boolean(palletizer.wrapper_start_signal || palletizer.sygnalDoOwijarkiStart || palletizer.is_emptying || palletizer.oproznianie);

        updateMqttProcessFlowStepper(broker, bagger, machines.checkweigher || {}, palletizer, wrapper);

        // 6. ERROR LOGS & MQTT MESSAGES
        renderErrors(data.recent_errors || data.error_logs || []);
        renderLogs(data.recent_messages || []);
    }

    function updateMqttProcessFlowStepper(broker, bagger, checkweigher, palletizer, wrapper) {
        const isConn = broker.is_connected !== false && (broker.time_since_update_sec <= 30);

        // K0: Heartbeat
        setMfsStepState('mfsStep0', isConn ? 'completed' : 'active');

        // K1: Waga Dynamiczna & Zrzut (Pakowaczka -> Mała taśma -> Taśma skośna -> Waga dynamiczna)
        const k1Active = Boolean(bagger.is_running || checkweigher.reject_flap_open || (bagger.bpm > 0) || bagger.jaws_closed || checkweigher.bag_on_scale);
        setMfsStepState('mfsStep1', k1Active ? 'active' : (isConn ? 'ready' : ''));

        // K2: Obracak Worka
        const k2Active = Boolean(palletizer.turner_active || palletizer.obracakPraca || palletizer.obracakAktywny);
        setMfsStepState('mfsStep2', k2Active ? 'active' : (isConn && palletizer.current_layer > 0 ? 'completed' : ''));

        // K3: Przepychacz Rzędów
        const k3Active = Boolean(palletizer.pusher_active || palletizer.popychaczPraca || palletizer.popychaczAktywny);
        setMfsStepState('mfsStep3', k3Active ? 'active' : (isConn && palletizer.current_layer > 0 ? 'completed' : ''));

        // K4: Magazynek Palet
        const k4Active = Boolean(palletizer.dispenser_active || palletizer.podawaniePalety);
        setMfsStepState('mfsStep4', k4Active ? 'active' : (isConn ? 'ready' : ''));

        // K5: Winda / Kompletowanie / Opróżnianie
        const k5Active = Boolean(palletizer.is_emptying || palletizer.oproznianie || (palletizer.current_layer > 0));
        setMfsStepState('mfsStep5', palletizer.is_emptying ? 'active' : (palletizer.current_layer >= (palletizer.total_layers || 13) ? 'completed' : (k5Active ? 'active' : '')));

        // K6: Transfer do Owijarki
        const k6Active = Boolean(palletizer.wrapper_start_signal || palletizer.sygnalDoOwijarkiStart);
        setMfsStepState('mfsStep6', k6Active ? 'active' : '');

        // K7: Owijanie Stretch & Kapturek Top-Sheet
        const wrapPct = wrapper.progress_percent || 0;
        const k7Active = Boolean(wrapper.status === 'OWIJANIE' || (wrapPct > 0 && wrapPct < 100));
        setMfsStepState('mfsStep7', k7Active ? 'active' : (wrapPct >= 100 ? 'completed' : ''));

        // K8: Wyjazd Palety
        const k8Active = Boolean(wrapper.is_wrapped || wrapper.wyjazdPaletaOwinieta || wrapPct >= 100);
        setMfsStepState('mfsStep8', k8Active ? 'completed' : '');

        // K9: Bufor Odbiorczy (Rolki)
        const k9Active = Boolean(palletizer.roller_1_occupied || palletizer.roller_2_occupied || palletizer.buffer_full || palletizer.rolki1zajete || palletizer.rolki2zajete || palletizer.buforPelny);
        setMfsStepState('mfsStep9', k9Active ? 'active' : (isConn ? 'ready' : ''));

        // 5-point Checklist from Section 6 of MQTT_PROCESS_FLOW.md
        setMfsCheckTag('chk1Tag', Boolean(bagger.status && bagger.status !== 'OFFLINE'));
        setMfsCheckTag('chk2Tag', Boolean(palletizer.current_layer !== undefined && palletizer.current_bag !== undefined));
        setMfsCheckTag('chk3Tag', Boolean(palletizer.wrapper_start_signal !== undefined));
        setMfsCheckTag('chk4Tag', Boolean(wrapper.progress_percent !== undefined || wrapper.phase_code));
        setMfsCheckTag('chk5Tag', Boolean(palletizer.roller_1_occupied !== undefined || palletizer.buffer_full !== undefined));
    }

    function setMfsStepState(stepId, state) {
        const el = document.getElementById(stepId);
        if (!el) return;
        el.classList.remove('active', 'completed', 'ready');
        if (state) el.classList.add(state);
    }

    function setMfsCheckTag(tagId, isOk) {
        const el = document.getElementById(tagId);
        if (!el) return;
        el.className = `mfs-check-tag ${isOk ? 'ok' : 'wait'}`;
    }

    function renderPalletStations(stations) {
        if (!stations || !stations.length) return;
        stations.forEach((st, idx) => {
            const num = idx + 1;
            const cardEl = document.getElementById(`stCard${num}`);
            const descEl = document.getElementById(`stDesc${num}`);
            const countEl = document.getElementById(`stCount${num}`);
            const statusEl = document.getElementById(`stStatus${num}`);

            if (descEl) descEl.innerText = st.description || '';
            if (countEl) {
                if (num === 1) countEl.innerText = `${st.count || 0} szt`;
                else if (num === 2) countEl.innerText = `${st.count || 0} worków`;
                else if (num === 3) countEl.innerText = st.status === 'TRANSFER' ? 'W ruchu' : 'Wolny';
                else if (num === 4) countEl.innerText = `${st.count || 0} obr`;
                else if (num === 5) countEl.innerText = st.pallet_present ? 'Paleta czeka' : 'Wolny';
            }
            if (statusEl) {
                statusEl.innerText = st.status || 'CZUWANIE';
                statusEl.className = st.badge_class || 'status-pill';
            }
            if (cardEl) {
                const isPraca = (st.status === 'PODAWANIE' || st.status === 'OPRÓŻNIANIE' || st.status === 'TRANSFER' || st.status === 'OWIJANIE');
                const isReady = (st.status === 'DO ODBIORU' || st.status === 'GOTOWA');
                cardEl.className = 'station-card' + (isPraca ? ' praca' : (isReady ? ' ready' : (st.pallet_present ? ' active' : ' off')));
            }
        });
    }

    let lastRenderedWrapperLayers = -1;
    let lastRenderedWrapperTop = -1;
    let lastWrapperHasPallet = null;

    function renderWrapperSection(wrapper, stations) {
        if (!wrapper) return;

        const st4 = (stations && stations.length >= 4) ? stations[3] : null;
        const pct = wrapper.progress_percent || 0;
        const isWrapping = (wrapper.status === 'OWIJANIE' || (pct > 0 && pct < 100));
        const hasPallet = Boolean((st4 && st4.pallet_present) || isWrapping || (wrapper.current_layers && wrapper.current_layers > 0));

        // Dynamic Layer Count on Wrapper Pallet
        const wrapLayers = (wrapper.current_layers !== undefined && wrapper.current_layers !== null && wrapper.current_layers > 0) 
            ? wrapper.current_layers 
            : (currentConfig.full_layers || 12);
        const wrapTop = (wrapper.top_layer_bags !== undefined && wrapper.top_layer_bags !== null)
            ? wrapper.top_layer_bags
            : (currentConfig.top_layer_bags || 0);

        if (!hasPallet) {
            if (lastWrapperHasPallet !== false || wrapperPalletGroup3d) {
                lastWrapperHasPallet = false;
                lastRenderedWrapperLayers = -1;
                lastRenderedWrapperTop = -1;
                if (wrapperPalletGroup3d && turntableGroup3d) {
                    turntableGroup3d.remove(wrapperPalletGroup3d);
                    wrapperPalletGroup3d = null;
                }
                if (foilCylinderMesh3d && turntableGroup3d) {
                    turntableGroup3d.remove(foilCylinderMesh3d);
                    foilCylinderMesh3d = null;
                }
                if (topSheetCoverMesh3d && turntableGroup3d) {
                    turntableGroup3d.remove(topSheetCoverMesh3d);
                    topSheetCoverMesh3d = null;
                }
            }
        } else {
            if (!wrapperPalletGroup3d || lastWrapperHasPallet !== true || lastRenderedWrapperLayers !== wrapLayers || lastRenderedWrapperTop !== wrapTop) {
                lastWrapperHasPallet = true;
                lastRenderedWrapperLayers = wrapLayers;
                lastRenderedWrapperTop = wrapTop;
                build3dPalletOnTurntable(wrapLayers, wrapTop);
            }
        }

        const wrapSt = document.getElementById('wrapperStatusBadge');
        const wrapProgress = document.getElementById('valWrapperProgress');
        const wrapTopSheet = document.getElementById('valTopSheetStatus');
        const wrapRotations = document.getElementById('valWrapperRotations');
        const wrapPhase = document.getElementById('valWrapperPhase');
        const wrapTopBadge = document.getElementById('wrapperTopSheetBadge');
        const wrapTopText = document.getElementById('wrapperTopSheetText');
        const live3dText = document.getElementById('wrapper3dLiveStatus');
        const progFill2d = document.getElementById('wrapperProgressFill');
        const progText2d = document.getElementById('wrapperProgressText2d');
        const phaseBanner = document.getElementById('wrapperPhaseBanner');

        const pctVal = wrapper.progress_percent || 0;

        // Update 3D Visualizer
        updateWrapper3dVisuals(
            pctVal,
            wrapper.top_sheet_applied,
            wrapper.top_sheet_active,
            wrapper.carriage_height_percent || 0,
            isWrapping
        );

        if (wrapSt) {
            wrapSt.innerText = wrapper.status;
            wrapSt.className = 'status-pill' + (wrapper.status === 'PRACA' || isWrapping || wrapper.status === 'GOTOWA' ? ' praca' : '');
        }

        if (wrapProgress) wrapProgress.innerHTML = `${pctVal} <span class="unit">%</span>`;
        if (wrapRotations) wrapRotations.innerHTML = `${wrapper.rotations_count || 0} <span class="unit">obr</span>`;
        if (wrapPhase) wrapPhase.innerText = wrapper.phase_code || 'CZUWANIE';

        if (wrapTopSheet) {
            if (wrapper.top_sheet_applied) {
                wrapTopSheet.innerHTML = '<span style="color: #10b981;">✅ NAŁOŻONY</span>';
            } else if (wrapper.top_sheet_active) {
                wrapTopSheet.innerHTML = '<span style="color: var(--neon-cyan);">⏳ NAKŁADANIE</span>';
            } else {
                wrapTopSheet.innerHTML = '<span style="color: var(--theme-text-muted);">BRAK</span>';
            }
        }

        if (wrapTopBadge && wrapTopText) {
            if (wrapper.top_sheet_applied) {
                wrapTopBadge.classList.add('active');
                wrapTopText.innerText = 'Kapturek nawierzchniowy (Top Sheet): NAŁOŻONY (Wodoszczelny)';
            } else if (wrapper.top_sheet_active) {
                wrapTopBadge.classList.add('active');
                wrapTopText.innerText = 'Kapturek nawierzchniowy (Top Sheet): NAKŁADANIE W TOKU...';
            } else {
                wrapTopBadge.classList.remove('active');
                wrapTopText.innerText = 'Kapturek nawierzchniowy (Top Sheet): BRAK';
            }
        }

        if (live3dText) {
            if (!hasPallet) {
                live3dText.innerText = `STÓŁ: PUSTY • STATUS: ${wrapper.status || 'CZUWANIE'} • BLOKER: OTWARTY`;
            } else {
                live3dText.innerText = `ETAP: ${wrapper.phase_label || 'CZUWANIE'} • WÓZEK: ${wrapper.carriage_height_percent || 0}% • OWINIĘCIE: ${pctVal}%`;
            }
        }

        if (progFill2d) progFill2d.style.width = pct + '%';
        if (progText2d) progText2d.innerText = pct + '%';
        if (phaseBanner) phaseBanner.innerText = wrapper.phase_label || 'Oczekiwanie na paletę';

        // Update 2D Milestones
        const mBottom = document.getElementById('mStepBottom');
        const mTopSheet = document.getElementById('mStepTopSheet');
        const mTop = document.getElementById('mStepTop');
        const mDone = document.getElementById('mStepDone');

        if (mBottom) mBottom.classList.toggle('active', pct >= 25);
        if (mTopSheet) mTopSheet.classList.toggle('active', wrapper.top_sheet_applied || pct >= 50);
        if (mTop) mTop.classList.toggle('active', pct >= 75);
        if (mDone) mDone.classList.toggle('active', pct >= 100);
    }

    // ─────────────────────────────────────────────────────────────
    // ERROR JOURNAL RENDERER
    // ─────────────────────────────────────────────────────────────
    function renderErrors(errors) {
        if (!errorsContainer) return;
        
        const badge = document.getElementById('errorCounterBadge');
        if (badge) badge.innerText = `${errors.length} zdarzeń`;

        const filtered = errors.filter(e => {
            if (activeErrFilter === 'ALL') return true;
            return (e.machine || '').toUpperCase() === activeErrFilter.toUpperCase();
        });

        if (filtered.length === 0) {
            errorsContainer.innerHTML = `
                <div class="error-empty-state">
                    <span class="material-icons" style="font-size: 32px; color: var(--neon-emerald); margin-bottom: 6px;">check_circle</span>
                    <div>Brak zarejestrowanych błędów lub alarmów maszyn. Linia pracuje stabilnie.</div>
                </div>
            `;
            return;
        }

        errorsContainer.innerHTML = '';
        filtered.forEach(err => {
            const row = document.createElement('div');
            const sevClass = (err.severity || '').toLowerCase();
            row.className = `error-item-row ${sevClass}`;
            row.innerHTML = `
                <div class="err-left">
                    <div class="err-title-row">
                        <span class="err-machine-tag">${err.machine || 'SYSTEM'}</span>
                        <span class="err-code-badge">[${err.code || 'ERR'}]</span>
                    </div>
                    <div class="err-msg-text">${err.description || 'Błąd maszyny'}</div>
                </div>
                <div class="err-time-text">${err.timestamp_iso || ''}</div>
            `;
            errorsContainer.appendChild(row);
        });
    }

    window.filterErrorLogs = function(filter, btn) {
        activeErrFilter = filter;
        document.querySelectorAll('[data-err-filter]').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        fetchTelemetry();
    };

    window.clearMachineErrors = async function() {
        if (!confirm('Czy na pewno chcesz wyczyścić historię błędów maszyn?')) return;
        try {
            await fetch('/api/machines/errors/clear', { method: 'POST' });
            fetchTelemetry();
        } catch(e) {}
    };

    // ─────────────────────────────────────────────────────────────
    // TERMINAL LOG STREAM
    // ─────────────────────────────────────────────────────────────
    function renderLogs(messages) {
        if (!terminalEl || isPaused) return;
        
        const filtered = messages.filter(m => {
            if (activeFilter === 'ALL') return true;
            return (m.topic || '').includes(activeFilter);
        });

        if (filtered.length === 0) return;

        terminalEl.innerHTML = '';
        filtered.forEach(m => {
            const row = document.createElement('div');
            row.className = 'term-row';
            const payloadStr = typeof m.payload === 'object' ? JSON.stringify(m.payload) : String(m.payload);
            row.innerHTML = `<span class="term-time">[${m.received_at_iso || ''}]</span><span class="term-topic">${m.topic || ''}</span><span class="term-payload">${payloadStr}</span>`;
            terminalEl.appendChild(row);
        });

        terminalEl.scrollTop = terminalEl.scrollHeight;
    }

    window.filterLogs = function(filter, btn) {
        activeFilter = filter;
        document.querySelectorAll('.terminal-filters [data-filter]').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
    };

    window.togglePauseTerminal = function() {
        isPaused = !isPaused;
        const btn = document.getElementById('btnPauseTerm');
        if (btn) {
            btn.innerText = isPaused ? 'WZNÓW' : 'PAUZA';
            btn.style.color = isPaused ? '#ef4444' : '';
        }
    };

    window.simulateSignal = async function() {
        try {
            await fetch('/api/machines/telemetry/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ add_counter: 5, add_pallets: 0, status: 'PRACA' })
            });
            fetchTelemetry();
        } catch(e){}
    };

    // ─────────────────────────────────────────────────────────────
    // PALLET MODAL & RECIPE MANAGEMENT
    // ─────────────────────────────────────────────────────────────
    let selectedModalPallet = 'INDUSTRIAL_100x120';

    window.selectModalPalletType = function(type) {
        selectedModalPallet = type;
        const isInd = !String(type || '').toUpperCase().includes('EURO');
        const cardInd = document.getElementById('modalCardInd');
        const cardEuro = document.getElementById('modalCardEuro');

        if (cardInd && cardEuro) {
            cardInd.classList.toggle('active', isInd);
            cardEuro.classList.toggle('active', !isInd);
        }

        // Filter presets for the chosen pallet type
        renderPresets();

        // Auto-select first preset for this pallet type if available
        const firstPreset = availablePresets.find(p => isInd ? !String(p.pallet_type || '').toUpperCase().includes('EURO') : String(p.pallet_type || '').toUpperCase().includes('EURO'));
        if (firstPreset) {
            document.getElementById('cfgPresetName').value = firstPreset.name;
            document.getElementById('cfgTotalLayers').value = firstPreset.full_layers || firstPreset.total_layers;
            document.getElementById('cfgBagsPerLayer').value = firstPreset.bags_per_layer;
            document.getElementById('cfgTopLayerBags').value = firstPreset.top_layer_bags || 0;
            if (firstPreset.bag_weight_kg) document.getElementById('cfgBagWeight').value = firstPreset.bag_weight_kg;
            
            const firstChip = document.querySelector('.preset-chip');
            if (firstChip) firstChip.classList.add('active');
        }

        updateModalPreview();
    };

    window.openPalletConfigModal = function() {
        selectedModalPallet = currentConfig.pallet_type || 'INDUSTRIAL_100X120';
        const isInd = !String(selectedModalPallet || '').toUpperCase().includes('EURO');
        
        const cardInd = document.getElementById('modalCardInd');
        const cardEuro = document.getElementById('modalCardEuro');
        if (cardInd && cardEuro) {
            cardInd.classList.toggle('active', isInd);
            cardEuro.classList.toggle('active', !isInd);
        }

        document.getElementById('cfgPresetName').value = currentConfig.preset_name || '';
        document.getElementById('cfgTotalLayers').value = currentConfig.full_layers || currentConfig.total_layers || 12;
        document.getElementById('cfgBagsPerLayer').value = currentConfig.bags_per_layer || 4;
        document.getElementById('cfgTopLayerBags').value = currentConfig.top_layer_bags !== undefined ? currentConfig.top_layer_bags : 2;
        document.getElementById('cfgBagWeight').value = currentConfig.bag_weight_kg || 25.0;

        renderPresets();
        updateModalPreview();
        document.getElementById('palletConfigModalOverlay').style.display = 'flex';
    };

    window.closePalletConfigModal = function() {
        document.getElementById('palletConfigModalOverlay').style.display = 'none';
    };

    window.updateModalPreview = function() {
        const fullLayers = parseInt(document.getElementById('cfgTotalLayers').value) || 1;
        const bagsPerLayer = parseInt(document.getElementById('cfgBagsPerLayer').value) || 1;
        const topBags = parseInt(document.getElementById('cfgTopLayerBags').value) || 0;
        const weight = parseFloat(document.getElementById('cfgBagWeight').value) || 25.0;

        const isInd = !String(selectedModalPallet || '').toUpperCase().includes('EURO');
        const tagEl = document.getElementById('cfgPreviewPalletTypeTag');
        if (tagEl) {
            tagEl.innerText = isInd 
                ? 'PALETA PRZEMYSŁOWA (1000 × 1200 mm, 7 DESEK) • PODSUMOWANIE RECEPTURY:' 
                : 'PALETA EURO / EPAL 1 (800 × 1200 mm, 5 DESEK) • PODSUMOWANIE RECEPTURY:';
        }

        const totalBags = (fullLayers * bagsPerLayer) + topBags;
        let formulaStr = '';
        if (topBags > 0) {
            formulaStr = `(${fullLayers} pełnych warstw × ${bagsPerLayer} szt) + (szczyt ${topBags} szt) = <span class="highlight-magenta">${totalBags} worków</span>`;
        } else {
            formulaStr = `${fullLayers} pełnych warstw × ${bagsPerLayer} szt = <span class="highlight-magenta">${totalBags} worków</span>`;
        }

        const totalKg = totalBags * weight;
        const totalTons = (totalKg / 1000.0).toFixed(2);

        document.getElementById('cfgPreviewFormulaText').innerHTML = formulaStr;
        document.getElementById('cfgPreviewWeightText').innerHTML = `Łączna masa netto palety: <strong>${totalKg.toLocaleString()} kg</strong> (${totalTons} t) • Wymiary: ${isInd ? '100 × 120 cm' : '80 × 120 cm'}`;
    };

    window.savePalletConfig = async function() {
        const btn = document.getElementById('btnSavePalletConfig');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="material-icons">hourglass_empty</span> Aktywowanie...';
        btn.disabled = true;

        const fullL = parseInt(document.getElementById('cfgTotalLayers').value) || 12;
        const bagsPerL = parseInt(document.getElementById('cfgBagsPerLayer').value) || 4;
        const topL = parseInt(document.getElementById('cfgTopLayerBags').value) || 0;
        const presetName = document.getElementById('cfgPresetName').value.trim();

        const payload = {
            preset_name: presetName,
            pallet_type: selectedModalPallet,
            full_layers: fullL,
            total_layers: fullL + (topL > 0 ? 1 : 0),
            bags_per_layer: bagsPerL,
            top_layer_bags: topL,
            bag_weight_kg: parseFloat(document.getElementById('cfgBagWeight').value) || 25.0,
            sync_to_machine: document.getElementById('cfgSyncToMachine').checked
        };

        try {
            const res = await fetch('/api/machines/palletizer/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await res.json();
            if (result.success) {
                currentConfig = result.data;
                applyConfigToUI();

                // Rebuild 3D geometries for Palletizer & Wrapper twins
                build3dEuroPallet();
                rebuild3dBags(current3dLayer, current3dBag, false, 0, null);
                if (typeof lastWrapperHasPallet !== 'undefined' && lastWrapperHasPallet && typeof build3dPalletOnTurntable === 'function') {
                    build3dPalletOnTurntable();
                    build3dWrapperFoilAndCap();
                }

                closePalletConfigModal();
                fetchTelemetry();
            } else {
                alert('Błąd zapisu: ' + (result.message || 'Nieznany błąd'));
            }
        } catch (e) {
            alert('Wystąpił błąd komunikacji: ' + e);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    };

    // Fullscreen 3D Viewport Toggle
    window.toggle3dFullscreen = function(wrapperId, btn) {
        const wrapper = document.getElementById(wrapperId);
        if (!wrapper) return;

        const isFull = wrapper.classList.toggle('is-fullscreen');
        if (btn) {
            btn.innerHTML = `<span class="material-icons">${isFull ? 'fullscreen_exit' : 'fullscreen'}</span> ${isFull ? 'ZAMKNIJ' : 'EKRAN'}`;
            btn.classList.toggle('active', isFull);
        }

        // Trigger renderer and camera resize
        function trigger3dResize() {
            if (wrapperId === 'pallet3dWrapper') {
                on3dWindowResize();
            } else if (wrapperId === 'wrapper3dWrapper') {
                onWrapper3dWindowResize();
            }
        }

        requestAnimationFrame(trigger3dResize);
        setTimeout(trigger3dResize, 50);
        setTimeout(trigger3dResize, 150);
        setTimeout(trigger3dResize, 350);
    };

    // ESC key listener to exit 3D Fullscreen
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.pallet-3d-wrapper.is-fullscreen').forEach(el => {
                el.classList.remove('is-fullscreen');
                const btn = el.querySelector('[id*="Fullscreen"]');
                if (btn) {
                    btn.classList.remove('active');
                    btn.innerHTML = '<span class="material-icons">fullscreen</span> EKRAN';
                }
                if (el.id === 'pallet3dWrapper') on3dWindowResize();
                if (el.id === 'wrapper3dWrapper') onWrapper3dWindowResize();
            });
        }
    });

    // Initialize
    initTheme();
    loadPalletConfig();
    setTimeout(init3dScene, 100);
    setTimeout(initWrapper3dScene, 150);
    fetchTelemetry();
    if (window.__maszynyTelemetryInterval) {
        clearInterval(window.__maszynyTelemetryInterval);
    }
    window.__maszynyTelemetryInterval = setInterval(fetchTelemetry, 1000);
})();
