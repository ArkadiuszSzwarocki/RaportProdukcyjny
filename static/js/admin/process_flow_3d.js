// File: static/js/admin/process_flow_3d.js
/**
 * 3D Process Flow Digital Twin - Three.js WebGL Engine
 * End-to-end MQTT Process Flow visualization based on MQTT_PROCESS_FLOW.md
 * Author: Antigravity MES Architecture
 */

(function () {
    'use strict';

    // Scene variables
    let scene = null;
    let camera = null;
    let renderer = null;
    let controls = null;
    let autoRotate = false;
    let activeCameraMode = 'iso';

    // Scene groups
    let mainGroup = null;
    let conveyorRollers = [];
    let bagMeshInfeed = null;
    let rejectFlapMesh = null;
    let turnerTableMesh = null;
    let turnerBagMesh = null;
    let pusherPaddleMesh = null;
    let dropPlatesGroup = null;
    let elevatorPistonMesh = null;
    let palletOnElevator = null;
    let bagsOnElevatorGroup = null;
    let wrapperTurntableMesh = null;
    let wrapperPalletGroup = null;
    let wrapperCarriageMesh = null;
    let wrapperFoilWrapMesh = null;
    let topSheetArmMesh = null;
    let bufferR1SensorMesh = null;
    let bufferR2SensorMesh = null;
    let bufferBeaconMesh = null;
    let palletOnBufferGroup = null;

    // Simulation & Live State
    let liveData = {
        connected: false,
        lastSeenSec: 999,
        bagger: { status: 'OFFLINE', bpm: 0, tonsPerHour: 0, counter: 0, recipe: '-' },
        checkweigher: { currentWeight: 25.04, targetWeight: 25.0, flapOpen: false, rejects: 0 },
        palletizer: {
            status: 'OFFLINE',
            currentLayer: 0,
            currentBag: 0,
            totalLayers: 13,
            fullLayers: 12,
            bagsPerLayer: 4,
            topBags: 2,
            totalTargetBags: 50,
            progressPct: 0,
            is处的: false,
            isTransferring: false,
            turnerActive: false,
            turnerAngle: 0,
            pusherActive: false,
            dispenserCount: 8,
            roller1Occupied: false,
            roller2Occupied: false,
            bufferFull: false
        },
        wrapper: {
            status: 'OFFLINE',
            progressPct: 0,
            phaseCode: 'IDLE',
            rotations: 0,
            carriageHeightPct: 0,
            topSheetApplied: false,
            isWrapped: false
        }
    };

    // Animation internal state variables
    let animBaggerTime = 0;
    let infeedBagX = -10.0;
    let turnerAngleCurrent = 0;
    let pusherZCurrent = 0;
    let elevatorHeightCurrent = 1.35;
    let targetElevatorHeight = 1.35;
    let transferPalletX = 0;
    let isTransferAnimRunning = false;
    let wrapperAngleCurrent = 0;
    let wrapperCarriageYCurrent = 0.6;
    let targetCarriageY = 0.6;

    // Material helper
    function createMaterial(colorHex, roughness = 0.4, metalness = 0.6, emissiveHex = 0x000000, emissiveIntensity = 0.0) {
        return new THREE.MeshStandardMaterial({
            color: colorHex,
            roughness: roughness,
            metalness: metalness,
            emissive: emissiveHex,
            emissiveIntensity: emissiveIntensity
        });
    }

    // Material palette
    const materials = {
        steelDark: createMaterial(0x1e293b, 0.6, 0.7),
        steelLight: createMaterial(0x94a3b8, 0.3, 0.8),
        chrome: createMaterial(0xe2e8f0, 0.15, 0.95),
        hazardYellow: createMaterial(0xf59e0b, 0.35, 0.3),
        conveyorBelt: createMaterial(0x0f172a, 0.85, 0.1),
        cyanNeon: createMaterial(0x38bdf8, 0.2, 0.8, 0x0284c7, 0.6),
        emeraldNeon: createMaterial(0x10b981, 0.2, 0.8, 0x059669, 0.6),
        roseNeon: createMaterial(0xf43f5e, 0.2, 0.8, 0xbe123c, 0.7),
        woodPallet: createMaterial(0xb45309, 0.85, 0.05),
        bagPaperWhite: createMaterial(0xf8fafc, 0.7, 0.05),
        bagActiveCyan: createMaterial(0x38bdf8, 0.5, 0.2, 0x0284c7, 0.4),
        foilStretch: new THREE.MeshStandardMaterial({
            color: 0x93c5fd,
            roughness: 0.1,
            metalness: 0.2,
            transparent: true,
            opacity: 0.42,
            side: THREE.DoubleSide
        })
    };

    // Initialize 3D Engine
    function init3dScene() {
        const container = document.getElementById('processFlow3dContainer');
        if (!container || typeof THREE === 'undefined') return;

        const width = container.clientWidth || 1200;
        const height = container.clientHeight || 640;

        scene = new THREE.Scene();
        scene.background = new THREE.Color(0x040914);

        camera = new THREE.PerspectiveCamera(45, width / height, 0.2, 200);
        camera.position.set(4.5, 12.0, 22.0);

        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(width, height);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        container.innerHTML = '';
        container.appendChild(renderer.domElement);

        if (typeof THREE.OrbitControls !== 'undefined') {
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.maxPolarAngle = Math.PI / 2 + 0.02;
            controls.minDistance = 3.0;
            controls.maxDistance = 60.0;
            controls.target.set(3.5, 1.2, 0);
        }

        // Scene Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
        scene.add(ambientLight);

        const mainDirLight = new THREE.DirectionalLight(0xffffff, 0.95);
        mainDirLight.position.set(10, 22, 14);
        mainDirLight.castShadow = true;
        mainDirLight.shadow.mapSize.width = 2048;
        mainDirLight.shadow.mapSize.height = 2048;
        mainDirLight.shadow.camera.near = 0.5;
        mainDirLight.shadow.camera.far = 80;
        mainDirLight.shadow.camera.left = -25;
        mainDirLight.shadow.camera.right = 25;
        mainDirLight.shadow.camera.top = 20;
        mainDirLight.shadow.camera.bottom = -20;
        scene.add(mainDirLight);

        const cyanFillLight = new THREE.DirectionalLight(0x0284c7, 0.4);
        cyanFillLight.position.set(-14, 10, -10);
        scene.add(cyanFillLight);

        // Ground Floor Grid
        const floorGrid = new THREE.GridHelper(60, 60, 0x1e293b, 0x0f172a);
        floorGrid.position.y = 0;
        scene.add(floorGrid);

        const shadowPlaneGeo = new THREE.PlaneGeometry(60, 30);
        const shadowPlaneMat = new THREE.ShadowMaterial({ opacity: 0.22 });
        const shadowPlane = new THREE.Mesh(shadowPlaneGeo, shadowPlaneMat);
        shadowPlane.rotation.x = -Math.PI / 2;
        shadowPlane.position.y = -0.01;
        shadowPlane.receiveShadow = true;
        scene.add(shadowPlane);

        mainGroup = new THREE.Group();
        scene.add(mainGroup);

        // Build all Physical Stations along the Flow
        buildStation1Checkweigher();
        buildStation2BagTurner();
        buildStation3RowPusher();
        buildStation4PalletDispenser();
        buildStation5PalletizerElevator();
        buildStation6TransferConveyor();
        buildStation7StretchWrapper();
        buildStation8OutfeedBuffer();

        // Setup Event Listeners & Camera Controls
        setupCameraControls();
        setupToolbarButtons();

        // Run Animation Loop
        animate();

        window.addEventListener('resize', onWindowResize);
    }

    function onWindowResize() {
        const container = document.getElementById('processFlow3dContainer');
        if (!container || !camera || !renderer) return;
        const width = container.clientWidth;
        const height = container.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    }

    // ==========================================
    // STATION 1: WAGA DYNAMICZNA & ZRZUT (KROK 1)
    // ==========================================
    function buildStation1Checkweigher() {
        const st1Group = new THREE.Group();
        st1Group.position.set(-11.5, 0, 0);

        // Support frame
        const legGeo = new THREE.BoxGeometry(0.08, 1.0, 0.08);
        [[-0.8, -0.4], [-0.8, 0.4], [0.8, -0.4], [0.8, 0.4]].forEach(([lx, lz]) => {
            const leg = new THREE.Mesh(legGeo, materials.steelDark);
            leg.position.set(lx, 0.5, lz);
            leg.castShadow = true;
            st1Group.add(leg);
        });

        // Infeed Conveyor Bed
        const bedGeo = new THREE.BoxGeometry(1.8, 0.12, 0.88);
        const bed = new THREE.Mesh(bedGeo, materials.steelDark);
        bed.position.set(0, 1.0, 0);
        st1Group.add(bed);

        const beltGeo = new THREE.BoxGeometry(1.7, 0.02, 0.72);
        const belt = new THREE.Mesh(beltGeo, materials.conveyorBelt);
        belt.position.set(0, 1.07, 0);
        st1Group.add(belt);

        // Metal Detector Arch
        const archPostGeo = new THREE.BoxGeometry(0.08, 0.7, 0.08);
        const archL = new THREE.Mesh(archPostGeo, materials.chrome);
        archL.position.set(-0.3, 1.42, 0.42);
        const archR = new THREE.Mesh(archPostGeo, materials.chrome);
        archR.position.set(-0.3, 1.42, -0.42);
        const archTopGeo = new THREE.BoxGeometry(0.1, 0.08, 0.92);
        const archTop = new THREE.Mesh(archTopGeo, materials.chrome);
        archTop.position.set(-0.3, 1.77, 0);
        st1Group.add(archL);
        st1Group.add(archR);
        st1Group.add(archTop);

        // Dynamic Weighing Scale Plate
        const scalePlateGeo = new THREE.BoxGeometry(0.58, 0.03, 0.7);
        const scalePlate = new THREE.Mesh(scalePlateGeo, materials.cyanNeon);
        scalePlate.position.set(0.2, 1.085, 0);
        st1Group.add(scalePlate);

        // Actuated Reject Flap
        const flapGeo = new THREE.BoxGeometry(0.48, 0.03, 0.68);
        rejectFlapMesh = new THREE.Mesh(flapGeo, materials.roseNeon);
        rejectFlapMesh.position.set(0.74, 1.085, 0);
        st1Group.add(rejectFlapMesh);

        // Reject Chute (Zsuwnia zrzutowa)
        const chuteGeo = new THREE.BoxGeometry(0.55, 0.04, 0.65);
        const chute = new THREE.Mesh(chuteGeo, materials.steelDark);
        chute.rotation.z = Math.PI / 4;
        chute.position.set(0.85, 0.75, 0);
        st1Group.add(chute);

        // Reject Catch Box
        const boxGeo = new THREE.BoxGeometry(0.7, 0.45, 0.75);
        const box = new THREE.Mesh(boxGeo, materials.hazardYellow);
        box.position.set(1.15, 0.22, 0);
        st1Group.add(box);

        // Infeed Moving Bag
        const bagGeo = new THREE.BoxGeometry(0.42, 0.16, 0.32);
        bagMeshInfeed = new THREE.Mesh(bagGeo, materials.bagPaperWhite);
        bagMeshInfeed.position.set(-0.6, 1.16, 0);
        bagMeshInfeed.castShadow = true;
        st1Group.add(bagMeshInfeed);

        mainGroup.add(st1Group);
    }

    // ==========================================
    // STATION 2: OBRACAK WORKA (KROK 2)
    // ==========================================
    function buildStation2BagTurner() {
        const st2Group = new THREE.Group();
        st2Group.position.set(-7.2, 0, 0);

        // Conveyor section
        buildConveyorSegment(st2Group, 0, 1.0, 0, 2.6, 0.88);

        // Rotating turntable disk
        const discGeo = new THREE.CylinderGeometry(0.55, 0.55, 0.06, 36);
        turnerTableMesh = new THREE.Mesh(discGeo, materials.steelLight);
        turnerTableMesh.position.set(0, 1.1, 0);

        const ringGeo = new THREE.TorusGeometry(0.56, 0.02, 16, 48);
        const ring = new THREE.Mesh(ringGeo, materials.cyanNeon);
        ring.rotation.x = Math.PI / 2;
        turnerTableMesh.add(ring);

        // Bag on turntable
        const bagGeo = new THREE.BoxGeometry(0.44, 0.16, 0.3);
        turnerBagMesh = new THREE.Mesh(bagGeo, materials.bagActiveCyan);
        turnerBagMesh.position.set(0, 0.1, 0);
        turnerTableMesh.add(turnerBagMesh);

        st2Group.add(turnerTableMesh);
        mainGroup.add(st2Group);
    }

    // ==========================================
    // STATION 3: PRZEPYCHACZ & FORMOWANIE (KROK 3)
    // ==========================================
    function buildStation3RowPusher() {
        const st3Group = new THREE.Group();
        st3Group.position.set(-3.2, 0, 0);

        buildConveyorSegment(st3Group, -0.6, 1.0, 0, 1.8, 0.88);

        // Split Formation Bed / Table
        dropPlatesGroup = new THREE.Group();
        dropPlatesGroup.position.set(0.6, 1.08, 0);

        const plateL = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.03, 0.55), materials.chrome);
        plateL.position.set(0, 0, -0.28);
        const plateR = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.03, 0.55), materials.chrome);
        plateR.position.set(0, 0, 0.28);
        dropPlatesGroup.add(plateL);
        dropPlatesGroup.add(plateR);
        st3Group.add(dropPlatesGroup);

        // Pusher Gantry Beam & Paddle
        const gantryBeam = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 1.8), materials.steelDark);
        gantryBeam.position.set(0.6, 1.65, 0);
        st3Group.add(gantryBeam);

        const paddleArm = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.45, 0.06), materials.steelLight);
        paddleArm.position.set(0.6, 1.4, -0.7);

        const paddleGeo = new THREE.BoxGeometry(0.85, 0.2, 0.05);
        pusherPaddleMesh = new THREE.Mesh(paddleGeo, materials.hazardYellow);
        pusherPaddleMesh.position.set(0.6, 1.2, -0.68);
        st3Group.add(pusherPaddleMesh);

        mainGroup.add(st3Group);
    }

    // ==========================================
    // STATION 4: MAGAZYNEK PALET (KROK 4)
    // ==========================================
    function buildStation4PalletDispenser() {
        const dispGroup = new THREE.Group();
        dispGroup.position.set(0.8, 0, -2.4);

        // Frame columns for pallet stack
        const colGeo = new THREE.BoxGeometry(0.08, 2.5, 0.08);
        [[-0.6, -0.5], [-0.6, 0.5], [0.6, -0.5], [0.6, 0.5]].forEach(([cx, cz]) => {
            const col = new THREE.Mesh(colGeo, materials.hazardYellow);
            col.position.set(cx, 1.25, cz);
            dispGroup.add(col);
        });

        // Stack of empty Euro pallets
        for (let i = 0; i < 7; i++) {
            const pal = buildSingleEuroPalletMesh(false);
            pal.position.set(0, 0.15 + i * 0.16, 0);
            dispGroup.add(pal);
        }

        // Dispenser push bar
        const feederBar = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.08, 0.1), materials.chrome);
        feederBar.position.set(0, 0.18, 0.7);
        dispGroup.add(feederBar);

        mainGroup.add(dispGroup);
    }

    // ==========================================
    // STATION 5: WINDA PALETYZATORA (KROK 5)
    // ==========================================
    function buildStation5PalletizerElevator() {
        const palGroup = new THREE.Group();
        palGroup.position.set(0.8, 0, 0);

        // Heavy Machine Columns
        const mastGeo = new THREE.BoxGeometry(0.12, 3.8, 0.12);
        [[-0.85, -0.75], [-0.85, 0.75], [0.85, -0.75], [0.85, 0.75]].forEach(([mx, mz]) => {
            const mast = new THREE.Mesh(mastGeo, materials.steelDark);
            mast.position.set(mx, 1.9, mz);
            palGroup.add(mast);
        });

        // Overhead crossbeams
        const beamXGeo = new THREE.BoxGeometry(1.82, 0.1, 0.1);
        const b1 = new THREE.Mesh(beamXGeo, materials.steelDark);
        b1.position.set(0, 3.75, -0.75);
        const b2 = new THREE.Mesh(beamXGeo, materials.steelDark);
        b2.position.set(0, 3.75, 0.75);
        palGroup.add(b1);
        palGroup.add(b2);

        // Hydraulic / Telescopic elevator piston beneath
        const pistonGeo = new THREE.CylinderGeometry(0.06, 0.06, 1.8, 20);
        elevatorPistonMesh = new THREE.Mesh(pistonGeo, materials.chrome);
        elevatorPistonMesh.position.set(0, 0.9, 0);
        palGroup.add(elevatorPistonMesh);

        // Elevator carriage with Pallet Base
        palletOnElevator = new THREE.Group();
        palletOnElevator.position.set(0, elevatorHeightCurrent, 0);

        const palletMesh = buildSingleEuroPalletMesh(true);
        palletOnElevator.add(palletMesh);

        bagsOnElevatorGroup = new THREE.Group();
        palletOnElevator.add(bagsOnElevatorGroup);

        rebuildStackedBags(0, 0);

        palGroup.add(palletOnElevator);
        mainGroup.add(palGroup);
    }

    // ==========================================
    // STATION 6: ROLOTOK TRANSFEROWY (KROK 6)
    // ==========================================
    function buildStation6TransferConveyor() {
        const transGroup = new THREE.Group();
        transGroup.position.set(4.0, 0, 0);

        buildConveyorSegment(transGroup, 0, 0.55, 0, 4.2, 1.1);

        mainGroup.add(transGroup);
    }

    // ==========================================
    // STATION 7: OWIJARKA AUTOMATYCZNA (KROK 7 & 8)
    // ==========================================
    function buildStation7StretchWrapper() {
        const wrapGroup = new THREE.Group();
        wrapGroup.position.set(8.2, 0, 0);

        // Rotating Turntable
        const ttGeo = new THREE.CylinderGeometry(1.35, 1.35, 0.12, 48);
        wrapperTurntableMesh = new THREE.Mesh(ttGeo, materials.steelDark);
        wrapperTurntableMesh.position.set(0, 0.56, 0);

        const ttRing = new THREE.Mesh(new THREE.TorusGeometry(1.36, 0.03, 16, 64), materials.emeraldNeon);
        ttRing.rotation.x = Math.PI / 2;
        wrapperTurntableMesh.add(ttRing);

        // Pallet on turntable
        wrapperPalletGroup = new THREE.Group();
        wrapperPalletGroup.position.set(0, 0.08, 0);
        const palOnTT = buildSingleEuroPalletMesh(false);
        wrapperPalletGroup.add(palOnTT);

        // Stacked bags block on wrapper
        const stackGeo = new THREE.BoxGeometry(1.05, 1.4, 0.85);
        const stackMesh = new THREE.Mesh(stackGeo, materials.bagPaperWhite);
        stackMesh.position.set(0, 0.85, 0);
        wrapperPalletGroup.add(stackMesh);

        // Stretch Foil Envelope around pallet
        const foilGeo = new THREE.CylinderGeometry(0.78, 0.78, 1.45, 32, 1, true);
        wrapperFoilWrapMesh = new THREE.Mesh(foilGeo, materials.foilStretch);
        wrapperFoilWrapMesh.position.set(0, 0.85, 0);
        wrapperFoilWrapMesh.visible = false;
        wrapperPalletGroup.add(wrapperFoilWrapMesh);

        wrapperTurntableMesh.add(wrapperPalletGroup);
        wrapGroup.add(wrapperTurntableMesh);

        // Vertical Wrapper Mast
        const mastGeo = new THREE.BoxGeometry(0.24, 3.6, 0.24);
        const mast = new THREE.Mesh(mastGeo, materials.steelDark);
        mast.position.set(1.7, 1.8, -0.9);
        wrapGroup.add(mast);

        // Film Roll Carriage moving up and down
        wrapperCarriageMesh = new THREE.Group();
        wrapperCarriageMesh.position.set(1.7, wrapperCarriageYCurrent, 0);

        const carriageBody = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.35, 0.2), materials.hazardYellow);
        wrapperCarriageMesh.add(carriageBody);

        const filmRoll = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.42, 20), materials.chrome);
        filmRoll.position.set(-0.25, 0, 0);
        wrapperCarriageMesh.add(filmRoll);

        wrapGroup.add(wrapperCarriageMesh);

        // Top Sheet Applicator Arm
        topSheetArmMesh = new THREE.Group();
        topSheetArmMesh.position.set(0, 2.55, -1.2);

        const armBeam = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.1, 1.5), materials.chrome);
        armBeam.position.set(0, 0, 0.75);
        topSheetArmMesh.add(armBeam);

        const capCover = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.05, 0.95), materials.foilStretch);
        capCover.position.set(0, -0.15, 1.2);
        topSheetArmMesh.add(capCover);

        wrapGroup.add(topSheetArmMesh);

        mainGroup.add(wrapGroup);
    }

    // ==========================================
    // STATION 8 & 9: BUFOR ODBIORCZY (KROK 9)
    // ==========================================
    function buildStation8OutfeedBuffer() {
        const bufGroup = new THREE.Group();
        bufGroup.position.set(13.2, 0, 0);

        buildConveyorSegment(bufGroup, 0, 0.55, 0, 4.4, 1.1);

        // Roller 1 Optical Sensor (Rolka 1)
        const sensor1Post = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.7, 0.06), materials.steelDark);
        sensor1Post.position.set(-1.0, 0.85, 0.65);
        bufferR1SensorMesh = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 16), materials.cyanNeon);
        bufferR1SensorMesh.position.set(-1.0, 1.18, 0.65);
        bufGroup.add(sensor1Post);
        bufGroup.add(bufferR1SensorMesh);

        // Roller 2 Optical Sensor (Rolka 2)
        const sensor2Post = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.7, 0.06), materials.steelDark);
        sensor2Post.position.set(1.0, 0.85, 0.65);
        bufferR2SensorMesh = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 16), materials.cyanNeon);
        bufferR2SensorMesh.position.set(1.0, 1.18, 0.65);
        bufGroup.add(sensor2Post);
        bufGroup.add(bufferR2SensorMesh);

        // Buffer Full Alarm Beacon
        const beaconPost = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.8, 0.08), materials.steelDark);
        beaconPost.position.set(2.1, 0.9, 0.65);
        bufferBeaconMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.18, 16), materials.roseNeon);
        bufferBeaconMesh.position.set(2.1, 1.85, 0.65);
        bufGroup.add(beaconPost);
        bufGroup.add(bufferBeaconMesh);

        // Ready Pallet standing on outfeed buffer
        palletOnBufferGroup = new THREE.Group();
        palletOnBufferGroup.position.set(1.0, 0.62, 0);
        palletOnBufferGroup.visible = false;

        const bufPallet = buildSingleEuroPalletMesh(false);
        palletOnBufferGroup.add(bufPallet);

        const bufStack = new THREE.Mesh(new THREE.BoxGeometry(1.05, 1.4, 0.85), materials.bagPaperWhite);
        bufStack.position.set(0, 0.85, 0);
        palletOnBufferGroup.add(bufStack);

        const bufFoil = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 1.45, 32, 1, true), materials.foilStretch);
        bufFoil.position.set(0, 0.85, 0);
        palletOnBufferGroup.add(bufFoil);

        bufGroup.add(palletOnBufferGroup);

        mainGroup.add(bufGroup);
    }

    // ==========================================
    // HELPER: BUILD CONVEYOR WITH ROLLERS
    // ==========================================
    function buildConveyorSegment(parentGroup, x, y, z, length, width) {
        const segGroup = new THREE.Group();
        segGroup.position.set(x, y, z);

        // Side Rails
        const railGeo = new THREE.BoxGeometry(length, 0.1, 0.05);
        const railL = new THREE.Mesh(railGeo, materials.steelDark);
        railL.position.set(0, 0.05, -width / 2);
        const railR = new THREE.Mesh(railGeo, materials.steelDark);
        railR.position.set(0, 0.05, width / 2);
        segGroup.add(railL);
        segGroup.add(railR);

        // Support Legs
        const legGeo = new THREE.BoxGeometry(0.08, y, 0.08);
        const halfL = length / 2 - 0.2;
        [[-halfL, -width / 2], [-halfL, width / 2], [halfL, -width / 2], [halfL, width / 2]].forEach(([lx, lz]) => {
            const leg = new THREE.Mesh(legGeo, materials.steelDark);
            leg.position.set(lx, -y / 2, lz);
            segGroup.add(leg);
        });

        // Spinning Rollers
        const rollerCount = Math.floor(length / 0.22);
        const rGeo = new THREE.CylinderGeometry(0.038, 0.038, width - 0.08, 16);
        for (let i = 0; i < rollerCount; i++) {
            const rx = -length / 2 + 0.15 + i * 0.22;
            const roller = new THREE.Mesh(rGeo, materials.chrome);
            roller.rotation.x = Math.PI / 2;
            roller.position.set(rx, 0.06, 0);
            segGroup.add(roller);
            conveyorRollers.push(roller);
        }

        parentGroup.add(segGroup);
    }

    // ==========================================
    // HELPER: DETAILED WOODEN EURO PALLET MESH
    // ==========================================
    function buildSingleEuroPalletMesh(isCastShadow = true) {
        const palGroup = new THREE.Group();

        // 3 Bottom skid boards
        const skidGeo = new THREE.BoxGeometry(1.2, 0.022, 0.14);
        [-0.43, 0, 0.43].forEach(z => {
            const skid = new THREE.Mesh(skidGeo, materials.woodPallet);
            skid.position.set(0, 0.011, z);
            skid.castShadow = isCastShadow;
            palGroup.add(skid);
        });

        // 9 Wooden blocks
        const blockGeo = new THREE.BoxGeometry(0.14, 0.078, 0.14);
        [-0.53, 0, 0.53].forEach(x => {
            [-0.43, 0, 0.43].forEach(z => {
                const block = new THREE.Mesh(blockGeo, materials.woodPallet);
                block.position.set(x, 0.061, z);
                block.castShadow = isCastShadow;
                palGroup.add(block);
            });
        });

        // 3 Stringer crossboards
        const stringerGeo = new THREE.BoxGeometry(0.14, 0.022, 1.0);
        [-0.53, 0, 0.53].forEach(x => {
            const stringer = new THREE.Mesh(stringerGeo, materials.woodPallet);
            stringer.position.set(x, 0.111, 0);
            stringer.castShadow = isCastShadow;
            palGroup.add(stringer);
        });

        // 5 Top deck boards
        const topDeckGeo = new THREE.BoxGeometry(1.2, 0.022, 0.14);
        [-0.43, -0.22, 0, 0.22, 0.43].forEach(z => {
            const deck = new THREE.Mesh(topDeckGeo, materials.woodPallet);
            deck.position.set(0, 0.133, z);
            deck.castShadow = isCastShadow;
            palGroup.add(deck);
        });

        return palGroup;
    }

    // ==========================================
    // REBUILD STACKED BAGS ON PALLETIZER ELEVATOR
    // ==========================================
    function rebuildStackedBags(currentLayer, currentBag) {
        if (!bagsOnElevatorGroup) return;
        bagsOnElevatorGroup.clear();

        const maxLayers = Math.min(currentLayer, 13);
        const bagHeight = 0.11;
        const baseOffsetY = 0.15;

        // Realistic bag geometry
        const bagGeo = new THREE.BoxGeometry(0.48, bagHeight - 0.01, 0.38);

        for (let l = 1; l <= maxLayers; l++) {
            const layerY = baseOffsetY + (l - 1) * bagHeight + bagHeight / 2;
            const isCurrentLayer = l === currentLayer;
            const isTopLayer = l === 13;
            const bagsInThisLayer = isTopLayer ? 2 : (isCurrentLayer ? Math.min(currentBag, 4) : 4);

            const isEven = l % 2 === 0;

            // 4 bags arrangement (interlocked pattern)
            const offsets = isEven ? [
                { x: -0.26, z: -0.22, ry: 0 },
                { x: 0.26, z: -0.22, ry: 0 },
                { x: -0.26, z: 0.22, ry: 0 },
                { x: 0.26, z: 0.22, ry: 0 }
            ] : [
                { x: -0.22, z: -0.26, ry: Math.PI / 2 },
                { x: -0.22, z: 0.26, ry: Math.PI / 2 },
                { x: 0.22, z: -0.26, ry: Math.PI / 2 },
                { x: 0.22, z: 0.26, ry: Math.PI / 2 }
            ];

            for (let b = 0; b < bagsInThisLayer; b++) {
                const isCurrentBag = isCurrentLayer && (b + 1 === currentBag);
                const mat = isCurrentBag ? materials.bagActiveCyan : materials.bagPaperWhite;
                const bag = new THREE.Mesh(bagGeo, mat);
                const pos = offsets[b % offsets.length];
                bag.position.set(pos.x, layerY, pos.z);
                bag.rotation.y = pos.ry;
                bag.castShadow = true;
                bagsOnElevatorGroup.add(bag);
            }
        }

        // Adjust target elevator height (descends as layers are filled)
        if (currentLayer <= 0) {
            targetElevatorHeight = 1.35;
        } else if (liveData.palletizer.is處) {
            targetElevatorHeight = 0.55; // Outfeed rolling height
        } else {
            targetElevatorHeight = Math.max(0.55, 1.35 - currentLayer * 0.065);
        }
    }

    // ==========================================
    // ANIMATION TICK LOOP
    // ==========================================
    function animate() {
        requestAnimationFrame(animate);

        animBaggerTime += 0.016;

        // 1. Infeed Bag Flow on Belt
        if (liveData.bagger.status === 'PRACA' || liveData.bagger.bpm > 0) {
            infeedBagX += 0.025;
            if (infeedBagX > 0.6) {
                infeedBagX = -0.8;
            }
            if (bagMeshInfeed) {
                bagMeshInfeed.position.x = infeedBagX;
                // If underweight/reject flap active, tilt bag downwards into chute
                if (liveData.checkweigher.flapOpen && infeedBagX > 0.3) {
                    bagMeshInfeed.position.y = 1.16 - (infeedBagX - 0.3) * 1.2;
                    bagMeshInfeed.rotation.z = -(infeedBagX - 0.3) * 1.5;
                } else {
                    bagMeshInfeed.position.y = 1.16;
                    bagMeshInfeed.rotation.z = 0;
                }
            }
        }

        // Reject Flap actuation
        if (rejectFlapMesh) {
            const targetRotZ = liveData.checkweigher.flapOpen ? Math.PI / 4 : 0;
            rejectFlapMesh.rotation.z += (targetRotZ - rejectFlapMesh.rotation.z) * 0.15;
        }

        // 2. Bag Turner Turntable Rotation
        if (liveData.palletizer.turnerActive && turnerTableMesh) {
            turnerAngleCurrent += 0.06;
            turnerTableMesh.rotation.y = turnerAngleCurrent;
        }

        // 3. Row Pusher Paddle Movement
        if (pusherPaddleMesh) {
            if (liveData.palletizer.pusherActive) {
                pusherZCurrent = Math.sin(animBaggerTime * 6) * 0.45;
            } else {
                pusherZCurrent += (0 - pusherZCurrent) * 0.1;
            }
            pusherPaddleMesh.position.z = -0.68 + pusherZCurrent;
        }

        // 5. Palletizer Elevator Smooth Height Adjustment
        elevatorHeightCurrent += (targetElevatorHeight - elevatorHeightCurrent) * 0.08;
        if (palletOnElevator) {
            palletOnElevator.position.y = elevatorHeightCurrent;
        }
        if (elevatorPistonMesh) {
            elevatorPistonMesh.scale.y = Math.max(0.1, elevatorHeightCurrent / 1.35);
            elevatorPistonMesh.position.y = elevatorHeightCurrent / 2;
        }

        // 6. Pallet Outfeed Transfer Rolling Animation
        if (liveData.palletizer.isTransferring || isTransferAnimRunning) {
            conveyorRollers.forEach(r => { r.rotation.z += 0.08; });
        }

        // 7. Stretch Wrapper Turntable & Film Carriage
        if (liveData.wrapper.status === 'OWIJANIE' || (liveData.wrapper.progressPct > 0 && liveData.wrapper.progressPct < 100)) {
            wrapperAngleCurrent += 0.045;
            if (wrapperTurntableMesh) {
                wrapperTurntableMesh.rotation.y = wrapperAngleCurrent;
            }

            // Carriage vertical movement based on height percent
            targetCarriageY = 0.6 + (liveData.wrapper.carriageHeightPct / 100) * 1.5;
            if (wrapperFoilWrapMesh) {
                wrapperFoilWrapMesh.visible = true;
                wrapperFoilWrapMesh.material.opacity = 0.35 + (liveData.wrapper.progressPct / 100) * 0.4;
            }
        } else {
            if (liveData.wrapper.isWrapped && wrapperFoilWrapMesh) {
                wrapperFoilWrapMesh.visible = true;
                wrapperFoilWrapMesh.material.opacity = 0.75;
            }
        }

        wrapperCarriageYCurrent += (targetCarriageY - wrapperCarriageYCurrent) * 0.08;
        if (wrapperCarriageMesh) {
            wrapperCarriageMesh.position.y = wrapperCarriageYCurrent;
        }

        // Top-Sheet Arm
        if (topSheetArmMesh) {
            const isTopSheetActive = liveData.wrapper.phaseCode === 'TOP_SHEET' || liveData.wrapper.topSheetApplied;
            const targetArmY = isTopSheetActive ? 2.3 : 2.7;
            topSheetArmMesh.position.y += (targetArmY - topSheetArmMesh.position.y) * 0.08;
        }

        // 8. Outfeed Buffer Ready Pallet Visibility
        if (palletOnBufferGroup) {
            palletOnBufferGroup.visible = liveData.palletizer.roller1Occupied || liveData.palletizer.roller2Occupied;
        }

        // Buffer full alarm flashing
        if (bufferBeaconMesh) {
            if (liveData.palletizer.bufferFull) {
                bufferBeaconMesh.material.emissiveIntensity = 0.5 + Math.sin(animBaggerTime * 10) * 0.5;
            } else {
                bufferBeaconMesh.material.emissiveIntensity = 0.1;
            }
        }

        // Sensor lights
        if (bufferR1SensorMesh) {
            bufferR1SensorMesh.material.color.setHex(liveData.palletizer.roller1Occupied ? 0x10b981 : 0x64748b);
        }
        if (bufferR2SensorMesh) {
            bufferR2SensorMesh.material.color.setHex(liveData.palletizer.roller2Occupied ? 0x10b981 : 0x64748b);
        }

        // OrbitControls update & auto-rotate
        if (controls) {
            if (autoRotate && mainGroup) {
                mainGroup.rotation.y += 0.003;
            }
            controls.update();
        }

        renderer.render(scene, camera);
    }

    // ==========================================
    // TELEMETRY POLLING & UI SYNC
    // ==========================================
    async function fetchLiveTelemetry() {
        try {
            const resp = await fetch('/machines/telemetry/live', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!resp.ok) return;
            const res = await resp.json();
            if (res.success && res.data) {
                applyTelemetryData(res.data);
            }
        } catch (err) {
            console.warn('Telemetry poll error:', err);
        }
    }

    function applyTelemetryData(d) {
        const bagger = d.bagger || {};
        const pal = d.palletizer || {};
        const wrap = d.wrapper || {};
        const cw = d.checkweigher || {};

        liveData.connected = d.is_connected !== false;
        liveData.lastSeenSec = d.time_since_update || 0;

        // Bagger
        liveData.bagger.status = bagger.status || 'OFFLINE';
        liveData.bagger.bpm = bagger.bpm || 0;
        liveData.bagger.tonsPerHour = bagger.tons_per_hour || 0;
        liveData.bagger.counter = bagger.counter_global || 0;
        liveData.bagger.recipe = bagger.recipe_name || '-';

        // Checkweigher
        liveData.checkweigher.currentWeight = cw.current_weight_kg || 25.04;
        liveData.checkweigher.targetWeight = cw.target_weight_kg || 25.0;
        liveData.checkweigher.flapOpen = cw.reject_flap_open || false;
        liveData.checkweigher.rejects = cw.reject_count_total || 0;

        // Palletizer
        liveData.palletizer.status = pal.status || 'OFFLINE';
        liveData.palletizer.currentLayer = pal.current_layer || 0;
        liveData.palletizer.currentBag = pal.current_bag || 0;
        liveData.palletizer.totalLayers = pal.total_layers || 13;
        liveData.palletizer.fullLayers = pal.full_layers || 12;
        liveData.palletizer.bagsPerLayer = pal.bags_per_layer || 4;
        liveData.palletizer.topBags = pal.top_layer_bags || 2;
        liveData.palletizer.totalTargetBags = pal.total_target_bags || 50;
        liveData.palletizer.progressPct = pal.pallet_progress_percent || 0;
        liveData.palletizer.is處 = pal.is_emptying || false;
        liveData.palletizer.isTransferring = pal.wrapper_start_signal || false;
        liveData.palletizer.turnerActive = pal.turner_active || false;
        liveData.palletizer.pusherActive = pal.pusher_active || false;
        liveData.palletizer.roller1Occupied = pal.roller_1_occupied || false;
        liveData.palletizer.roller2Occupied = pal.roller_2_occupied || false;
        liveData.palletizer.bufferFull = pal.buffer_full || false;

        // Wrapper
        liveData.wrapper.status = wrap.status || 'OFFLINE';
        liveData.wrapper.progressPct = wrap.progress_percent || 0;
        liveData.wrapper.phaseCode = wrap.phase_code || 'IDLE';
        liveData.wrapper.rotations = wrap.rotations_count || 0;
        liveData.wrapper.carriageHeightPct = wrap.carriage_height_percent || 0;
        liveData.wrapper.topSheetApplied = wrap.top_sheet_applied || false;
        liveData.wrapper.isWrapped = wrap.is_wrapped || false;

        // Rebuild 3D layers on change
        rebuildStackedBags(liveData.palletizer.currentLayer, liveData.palletizer.currentBag);

        // Update DOM Elements
        updateDomHud();
        updateProcessStepHighlight();
    }

    function updateDomHud() {
        const brokerDot = document.getElementById('pfBrokerDot');
        const brokerText = document.getElementById('pfBrokerText');
        const latencyText = document.getElementById('pfLatencyText');

        if (brokerDot && brokerText) {
            if (liveData.connected) {
                brokerDot.className = 'pf-dot online';
                brokerText.textContent = 'ONLINE';
            } else {
                brokerDot.className = 'pf-dot';
                brokerText.textContent = 'OFFLINE';
            }
        }
        if (latencyText) {
            latencyText.textContent = `${liveData.lastSeenSec}s temu`;
        }

        // Bagger Card
        const baggerBpm = document.getElementById('pfValBpm');
        const baggerTph = document.getElementById('pfValTph');
        const baggerCnt = document.getElementById('pfValCounter');
        const baggerStatus = document.getElementById('pfStatusBagger');
        if (baggerBpm) baggerBpm.textContent = liveData.bagger.bpm.toFixed(1);
        if (baggerTph) baggerTph.textContent = liveData.bagger.tonsPerHour.toFixed(2);
        if (baggerCnt) baggerCnt.textContent = liveData.bagger.counter;
        if (baggerStatus) {
            baggerStatus.textContent = liveData.bagger.status;
            baggerStatus.className = `pf-card-status ${liveData.bagger.status === 'PRACA' ? 'praca' : ''}`;
        }

        // Checkweigher
        const cwWeight = document.getElementById('pfValWeight');
        const cwRejects = document.getElementById('pfValRejects');
        const cwFlap = document.getElementById('pfStatusFlap');
        if (cwWeight) cwWeight.textContent = `${liveData.checkweigher.currentWeight.toFixed(2)} kg`;
        if (cwRejects) cwRejects.textContent = `${liveData.checkweigher.rejects} szt`;
        if (cwFlap) {
            cwFlap.textContent = liveData.checkweigher.flapOpen ? 'ZRZUT OTWARTY' : 'ZAMKNIĘTY';
            cwFlap.className = `pf-card-status ${liveData.checkweigher.flapOpen ? 'alarm' : ''}`;
        }

        // Palletizer Card
        const palProgress = document.getElementById('pfValPalProgress');
        const palLayerBag = document.getElementById('pfValLayerBag');
        const palBar = document.getElementById('pfPalProgressBar');
        const palStatus = document.getElementById('pfStatusPalletizer');
        if (palProgress) palProgress.textContent = `${liveData.palletizer.progressPct}%`;
        if (palLayerBag) palLayerBag.textContent = `W: ${liveData.palletizer.currentLayer}/${liveData.palletizer.totalLayers} • B: ${liveData.palletizer.currentBag}/${liveData.palletizer.bagsPerLayer}`;
        if (palBar) palBar.style.width = `${liveData.palletizer.progressPct}%`;
        if (palStatus) {
            palStatus.textContent = liveData.palletizer.status;
            palStatus.className = `pf-card-status ${liveData.palletizer.status === 'PRACA' ? 'praca' : ''}`;
        }

        // Wrapper Card
        const wrapProgress = document.getElementById('pfValWrapProgress');
        const wrapPhase = document.getElementById('pfValWrapPhase');
        const wrapRotations = document.getElementById('pfValRotations');
        const wrapBar = document.getElementById('pfWrapProgressBar');
        const wrapStatus = document.getElementById('pfStatusWrapper');
        if (wrapProgress) wrapProgress.textContent = `${liveData.wrapper.progressPct}%`;
        if (wrapPhase) wrapPhase.textContent = liveData.wrapper.phaseCode;
        if (wrapRotations) wrapRotations.textContent = liveData.wrapper.rotations;
        if (wrapBar) wrapBar.style.width = `${liveData.wrapper.progressPct}%`;
        if (wrapStatus) {
            wrapStatus.textContent = liveData.wrapper.status;
            wrapStatus.className = `pf-card-status ${liveData.wrapper.status === 'OWIJANIE' ? 'praca' : ''}`;
        }

        // Outfeed Buffer Card
        const bufR1 = document.getElementById('pfValR1');
        const bufR2 = document.getElementById('pfValR2');
        const bufAlarm = document.getElementById('pfStatusBuffer');
        if (bufR1) bufR1.textContent = liveData.palletizer.roller1Occupied ? 'ZAJĘTA' : 'WOLNA';
        if (bufR2) bufR2.textContent = liveData.palletizer.roller2Occupied ? 'ZAJĘTA' : 'WOLNA';
        if (bufAlarm) {
            bufAlarm.textContent = liveData.palletizer.bufferFull ? 'BUFOR PEŁNY' : 'GOTOWY';
            bufAlarm.className = `pf-card-status ${liveData.palletizer.bufferFull ? 'alarm' : 'praca'}`;
        }

        // Viewport Bottom HUD text
        const liveHudText = document.getElementById('pf3dLiveText');
        if (liveHudText) {
            liveHudText.innerHTML = `WARSTWA: <strong>${liveData.palletizer.currentLayer}/${liveData.palletizer.totalLayers}</strong> • WOREK: <strong>${liveData.palletizer.currentBag}/${liveData.palletizer.bagsPerLayer}</strong> • FAZA OWIJARKI: <strong>${liveData.wrapper.phaseCode}</strong> • ROLKI: <strong>R1:${liveData.palletizer.roller1Occupied ? '1' : '0'} R2:${liveData.palletizer.roller2Occupied ? '1' : '0'}</strong>`;
        }
    }

    // ==========================================
    // HIGHLIGHT ACTIVE PROCESS STEP (KROK 0 - 9)
    // ==========================================
    function updateProcessStepHighlight() {
        for (let k = 0; k <= 9; k++) {
            const stepEl = document.getElementById(`pfStep${k}`);
            if (!stepEl) continue;
            stepEl.classList.remove('active', 'completed');
        }

        // Step 0: Broker
        const s0 = document.getElementById('pfStep0');
        if (s0) {
            if (liveData.connected) s0.classList.add('completed');
            else s0.classList.add('active');
        }

        // Step 1: Checkweigher
        const s1 = document.getElementById('pfStep1');
        if (s1 && (liveData.bagger.status === 'PRACA' || liveData.checkweigher.flapOpen)) {
            s1.classList.add('active');
        }

        // Step 2: Turner
        const s2 = document.getElementById('pfStep2');
        if (s2 && liveData.palletizer.turnerActive) {
            s2.classList.add('active');
        }

        // Step 3: Pusher
        const s3 = document.getElementById('pfStep3');
        if (s3 && liveData.palletizer.pusherActive) {
            s3.classList.add('active');
        }

        // Step 4: Dispenser
        const s4 = document.getElementById('pfStep4');
        if (s4 && liveData.palletizer.currentLayer === 0) {
            s4.classList.add('active');
        }

        // Step 5: Elevator Stacking & Emptying
        const s5 = document.getElementById('pfStep5');
        if (s5 && (liveData.palletizer.currentLayer > 0 || liveData.palletizer.is處)) {
            s5.classList.add('active');
        }

        // Step 6: Transfer Signal
        const s6 = document.getElementById('pfStep6');
        if (s6 && liveData.palletizer.isTransferring) {
            s6.classList.add('active');
        }

        // Step 7: Wrapping
        const s7 = document.getElementById('pfStep7');
        if (s7 && (liveData.wrapper.status === 'OWIJANIE' || (liveData.wrapper.progressPct > 0 && liveData.wrapper.progressPct < 100))) {
            s7.classList.add('active');
        }

        // Step 8: Finished Wrapped
        const s8 = document.getElementById('pfStep8');
        if (s8 && (liveData.wrapper.isWrapped || liveData.wrapper.progressPct >= 100)) {
            s8.classList.add('completed');
        }

        // Step 9: Outfeed Buffer
        const s9 = document.getElementById('pfStep9');
        if (s9 && (liveData.palletizer.roller1Occupied || liveData.palletizer.roller2Occupied || liveData.palletizer.bufferFull)) {
            s9.classList.add('active');
        }
    }

    // ==========================================
    // CAMERA PRESETS & CONTROLS
    // ==========================================
    function setCameraView(mode, targetX = 3.5, targetY = 1.2, targetZ = 0) {
        activeCameraMode = mode;
        if (!camera || !controls) return;

        // Update button active state
        document.querySelectorAll('.pf-cam-btn').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById(`camBtn_${mode}`);
        if (btn) btn.classList.add('active');

        switch (mode) {
            case 'iso':
                camera.position.set(targetX + 6, 11.0, targetZ + 18);
                break;
            case 'top':
                camera.position.set(targetX, 24.0, targetZ + 0.1);
                break;
            case 'front':
                camera.position.set(targetX, 2.8, targetZ + 16);
                break;
            case 'bagger':
                camera.position.set(-10.5, 3.2, 5.5);
                targetX = -10.5; targetY = 1.1; targetZ = 0;
                break;
            case 'palletizer':
                camera.position.set(0.8, 4.2, 6.2);
                targetX = 0.8; targetY = 1.3; targetZ = 0;
                break;
            case 'wrapper':
                camera.position.set(8.2, 3.8, 6.0);
                targetX = 8.2; targetY = 1.2; targetZ = 0;
                break;
            case 'buffer':
                camera.position.set(13.5, 3.5, 5.5);
                targetX = 13.5; targetY = 0.8; targetZ = 0;
                break;
            default:
                camera.position.set(4.5, 12.0, 22.0);
        }

        controls.target.set(targetX, targetY, targetZ);
        controls.update();
    }

    function setupCameraControls() {
        const btnIso = document.getElementById('camBtn_iso');
        const btnTop = document.getElementById('camBtn_top');
        const btnFront = document.getElementById('camBtn_front');
        const btnReset = document.getElementById('camBtn_reset');
        const btnRotate = document.getElementById('btnAutoRotate3d');
        const btnFull = document.getElementById('btnFullscreen3d');

        if (btnIso) btnIso.addEventListener('click', () => setCameraView('iso'));
        if (btnTop) btnTop.addEventListener('click', () => setCameraView('top'));
        if (btnFront) btnFront.addEventListener('click', () => setCameraView('front'));
        if (btnReset) btnReset.addEventListener('click', () => setCameraView('iso'));

        if (btnRotate) {
            btnRotate.addEventListener('click', () => {
                autoRotate = !autoRotate;
                btnRotate.classList.toggle('active', autoRotate);
                btnRotate.style.background = autoRotate ? 'rgba(56, 189, 248, 0.4)' : '';
            });
        }

        if (btnFull) {
            btnFull.addEventListener('click', toggleFullscreen);
        }

        // Station specific focus buttons
        const stBtns = {
            'btnFocusBagger': 'bagger',
            'btnFocusPalletizer': 'palletizer',
            'btnFocusWrapper': 'wrapper',
            'btnFocusBuffer': 'buffer'
        };
        Object.entries(stBtns).forEach(([id, mode]) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', () => setCameraView(mode));
        });

        // Clickable Steps in Stepper
        const stepFocusMap = {
            'pfStep0': 'iso',
            'pfStep1': 'bagger',
            'pfStep2': 'palletizer',
            'pfStep3': 'palletizer',
            'pfStep4': 'palletizer',
            'pfStep5': 'palletizer',
            'pfStep6': 'palletizer',
            'pfStep7': 'wrapper',
            'pfStep8': 'wrapper',
            'pfStep9': 'buffer'
        };
        Object.entries(stepFocusMap).forEach(([id, mode]) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', () => setCameraView(mode));
        });
    }

    function toggleFullscreen() {
        const card = document.getElementById('pfViewportCard');
        if (!card) return;
        if (!document.fullscreenElement) {
            card.requestFullscreen().catch(err => console.warn(err));
        } else {
            document.exitFullscreen().catch(err => console.warn(err));
        }
        setTimeout(onWindowResize, 200);
    }

    function setupToolbarButtons() {
        // Theme switcher
        const themeBtn = document.getElementById('pfThemeBtn');
        if (themeBtn) {
            themeBtn.addEventListener('click', () => {
                document.body.classList.toggle('theme-light-mode');
                const isLight = document.body.classList.contains('theme-light-mode');
                if (scene) {
                    scene.background.setHex(isLight ? 0xe2e8f0 : 0x040914);
                }
            });
        }
    }

    // ==========================================
    // INTERACTIVE PROCESS SIMULATION (FOR TESTING)
    // ==========================================
    window.pfSimulateStep = function (stepName) {
        switch (stepName) {
            case 'bag_ok':
                liveData.bagger.status = 'PRACA';
                liveData.bagger.bpm = 12.5;
                liveData.checkweigher.currentWeight = 25.02;
                liveData.checkweigher.flapOpen = false;
                infeedBagX = -0.8;
                break;
            case 'reject_test':
                liveData.checkweigher.currentWeight = 24.10;
                liveData.checkweigher.flapOpen = true;
                liveData.checkweigher.rejects += 1;
                infeedBagX = 0.2;
                setTimeout(() => {
                    liveData.checkweigher.flapOpen = false;
                    liveData.checkweigher.currentWeight = 25.04;
                    updateDomHud();
                }, 2800);
                break;
            case 'turner_cycle':
                liveData.palletizer.turnerActive = true;
                turnerAngleCurrent = 0;
                setTimeout(() => { liveData.palletizer.turnerActive = false; }, 2200);
                break;
            case 'pusher_cycle':
                liveData.palletizer.pusherActive = true;
                setTimeout(() => { liveData.palletizer.pusherActive = false; }, 2000);
                break;
            case 'layer_inc':
                liveData.palletizer.currentBag += 1;
                if (liveData.palletizer.currentBag > 4) {
                    liveData.palletizer.currentBag = 1;
                    liveData.palletizer.currentLayer += 1;
                    if (liveData.palletizer.currentLayer > 13) liveData.palletizer.currentLayer = 1;
                }
                liveData.palletizer.progressPct = Math.round((liveData.palletizer.currentLayer / 13) * 100);
                rebuildStackedBags(liveData.palletizer.currentLayer, liveData.palletizer.currentBag);
                break;
            case 'transfer_start':
                liveData.palletizer.isTransferring = true;
                isTransferAnimRunning = true;
                setTimeout(() => {
                    liveData.palletizer.isTransferring = false;
                    isTransferAnimRunning = false;
                    liveData.wrapper.status = 'OWIJANIE';
                    liveData.wrapper.progressPct = 25;
                    liveData.wrapper.phaseCode = 'ASCENDING';
                    updateDomHud();
                }, 3500);
                break;
            case 'wrapper_cycle':
                liveData.wrapper.status = 'OWIJANIE';
                let p = 0;
                const wrapInterval = setInterval(() => {
                    p += 5;
                    liveData.wrapper.progressPct = p;
                    if (p < 20) {
                        liveData.wrapper.phaseCode = 'BOTTOM_WRAP';
                        liveData.wrapper.carriageHeightPct = 0;
                    } else if (p < 45) {
                        liveData.wrapper.phaseCode = 'ASCENDING';
                        liveData.wrapper.carriageHeightPct = (p - 20) * 4;
                    } else if (p < 65) {
                        liveData.wrapper.phaseCode = 'TOP_SHEET';
                        liveData.wrapper.carriageHeightPct = 100;
                        liveData.wrapper.topSheetApplied = true;
                    } else if (p < 85) {
                        liveData.wrapper.phaseCode = 'TOP_WRAP';
                        liveData.wrapper.carriageHeightPct = 100;
                    } else if (p < 100) {
                        liveData.wrapper.phaseCode = 'DESCENDING';
                        liveData.wrapper.carriageHeightPct = (100 - p) * 6;
                    } else {
                        liveData.wrapper.phaseCode = 'DONE';
                        liveData.wrapper.status = 'GOTOWA';
                        liveData.wrapper.isWrapped = true;
                        liveData.palletizer.roller1Occupied = true;
                        clearInterval(wrapInterval);
                    }
                    liveData.wrapper.rotations = Math.floor(p * 0.16);
                    updateDomHud();
                    updateProcessStepHighlight();
                }, 300);
                break;
            case 'buffer_toggle':
                liveData.palletizer.roller1Occupied = !liveData.palletizer.roller1Occupied;
                liveData.palletizer.roller2Occupied = liveData.palletizer.roller1Occupied;
                liveData.palletizer.bufferFull = liveData.palletizer.roller1Occupied;
                break;
        }

        updateDomHud();
        updateProcessStepHighlight();
    };

    // Auto-poll telemetry interval
    document.addEventListener('DOMContentLoaded', () => {
        init3dScene();
        fetchLiveTelemetry();
        setInterval(fetchLiveTelemetry, 1500);
    });

})();
