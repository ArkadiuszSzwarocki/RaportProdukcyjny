/**
 * Warehouse 3D - Procedural 3D Mesh & Geometry Builders
 */

let sharedGeos = {};
let sharedMats = {};

function initSharedResources() {
    sharedMats.steel = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.4, metalness: 0.7 });
    sharedMats.beam = new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.5, metalness: 0.4 });
    sharedMats.wood = new THREE.MeshStandardMaterial({ color: 0xc89d66, roughness: 0.8, metalness: 0.1 });
    sharedMats.blocked = new THREE.MeshStandardMaterial({ color: 0xef4444, roughness: 0.5, metalness: 0.3 });
    sharedMats.emptySlot = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.9, transparent: true, opacity: 0.25 });
    sharedMats.highlight = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    sharedMats.dropValid = new THREE.MeshStandardMaterial({ color: 0x10b981, emissive: 0x059669, emissiveIntensity: 0.7, transparent: true, opacity: 0.65 });
    sharedMats.dropInvalid = new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0xb91c1c, emissiveIntensity: 0.7, transparent: true, opacity: 0.65 });

    // Dedicated materials for shelving racks (R09 / SHELVING)
    sharedMats.shelfPanel = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.45, metalness: 0.55 });
    sharedMats.shelfDivider = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.5, metalness: 0.4 });
    sharedMats.shelfSteel = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.4, metalness: 0.75 });
    sharedMats.cartonBody = new THREE.MeshStandardMaterial({ color: 0xbfa175, roughness: 0.85, metalness: 0.05 });

    sharedGeos.palletBase = new THREE.BoxGeometry(1.2, 0.14, 0.8);
}

function createPillowSackGeometry(w, h, l) {
    const geo = new THREE.BoxGeometry(w, h, l, 8, 4, 8);
    const pos = geo.attributes.position;
    const halfW = w / 2, halfH = h / 2, halfL = l / 2;

    for (let i = 0; i < pos.count; i++) {
        let x = pos.getX(i);
        let y = pos.getY(i);
        let z = pos.getZ(i);

        const nx = x / halfW, ny = y / halfH, nz = z / halfL;
        if (ny > 0.4) {
            const centerBulge = Math.cos(nx * Math.PI * 0.46) * Math.cos(nz * Math.PI * 0.46);
            y += centerBulge * (h * 0.32);
        }
        pos.setXYZ(i, x, y, z);
    }
    geo.computeVertexNormals();
    return geo;
}

function createRealisticPalletGroup(isIndustrial) {
    const pGroup = new THREE.Group();
    const woodMat = sharedMats.wood;
    const pLength = 1.2;

    if (isIndustrial) {
        const topBoardWidths = [0.145, 0.100, 0.100, 0.145, 0.100, 0.100, 0.145];
        const topBoardX = [-0.4275, -0.285, -0.1425, 0, 0.1425, 0.285, 0.4275];
        for (let i = 0; i < 7; i++) {
            const board = new THREE.Mesh(new THREE.BoxGeometry(topBoardWidths[i], 0.022, pLength), woodMat);
            board.position.set(topBoardX[i], 0.133, 0);
            board.castShadow = true;
            pGroup.add(board);
        }
        for (let pos of [-0.5, 0, 0.5]) {
            const cross = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.022, 0.145), woodMat);
            cross.position.set(0, 0.111, pos);
            cross.castShadow = true;
            pGroup.add(cross);
        }
        for (let bx of [-0.425, 0, 0.425]) {
            for (let bz of [-0.5, 0, 0.5]) {
                const block = new THREE.Mesh(new THREE.BoxGeometry(0.145, 0.078, 0.145), woodMat);
                block.position.set(bx, 0.061, bz);
                block.castShadow = true;
                pGroup.add(block);
            }
            const bot = new THREE.Mesh(new THREE.BoxGeometry(0.145, 0.022, pLength), woodMat);
            bot.position.set(bx, 0.011, 0);
            pGroup.add(bot);
        }
    } else {
        const topBoardWidths = [0.145, 0.100, 0.145, 0.100, 0.145];
        const topBoardX = [-0.3275, -0.175, 0, 0.175, 0.3275];
        for (let i = 0; i < 5; i++) {
            const board = new THREE.Mesh(new THREE.BoxGeometry(topBoardWidths[i], 0.022, pLength), woodMat);
            board.position.set(topBoardX[i], 0.133, 0);
            board.castShadow = true;
            pGroup.add(board);
        }
        for (let pos of [-0.5, 0, 0.5]) {
            const cross = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.022, 0.145), woodMat);
            cross.position.set(0, 0.111, pos);
            cross.castShadow = true;
            pGroup.add(cross);
        }
        for (let bx of [-0.325, 0, 0.325]) {
            for (let bz of [-0.5, 0, 0.5]) {
                const block = new THREE.Mesh(new THREE.BoxGeometry(0.145, 0.078, 0.145), woodMat);
                block.position.set(bx, 0.061, bz);
                block.castShadow = true;
                pGroup.add(block);
            }
            const bot = new THREE.Mesh(new THREE.BoxGeometry(0.145, 0.022, pLength), woodMat);
            bot.position.set(bx, 0.011, 0);
            pGroup.add(bot);
        }
    }
    return pGroup;
}

function createRealisticPinwheelStack(productName, batch, weightText) {
    const stackGroup = new THREE.Group();
    const bagHeight = 0.095;
    const baseHeight = 0.144;
    const layers = 5;

    const bagW = 0.385;
    const bagL = 0.585;

    const texNormal = getOrCreateSackTexture(productName, batch, false, weightText);
    const texRotated = getOrCreateSackTexture(productName, batch, true, weightText);

    for (let l = 1; l <= layers; l++) {
        const isEven = (l % 2 === 0);
        const layerY = baseHeight + (l - 1) * bagHeight + (bagHeight / 2);

        const positions = [
            { x: -0.194, z: -0.294 },
            { x: 0.194, z: -0.294 },
            { x: 0.194, z: 0.294 },
            { x: -0.194, z: 0.294 }
        ];

        for (let b = 0; b < 4; b++) {
            const pos = positions[b];
            const sGeo = createPillowSackGeometry(bagW, bagHeight - 0.008, bagL);
            const sMat = new THREE.MeshStandardMaterial({
                map: isEven ? texRotated : texNormal,
                roughness: 0.78,
                metalness: 0.05
            });
            const sackMesh = new THREE.Mesh(sGeo, sMat);
            sackMesh.position.set(pos.x, layerY, pos.z);
            sackMesh.castShadow = true;
            stackGroup.add(sackMesh);
        }
    }

    const foilGeo = new THREE.BoxGeometry(0.80, layers * bagHeight + 0.01, 1.20);
    const foilMat = new THREE.MeshStandardMaterial({
        color: 0xa5f3fc,
        transparent: true,
        opacity: 0.18,
        roughness: 0.1,
        metalness: 0.25
    });
    const foilMesh = new THREE.Mesh(foilGeo, foilMat);
    foilMesh.position.set(0, baseHeight + (layers * bagHeight) / 2, 0);
    stackGroup.add(foilMesh);

    return stackGroup;
}

function createRealisticBigBagGroup(productName, batch, weightText) {
    const bbGroup = new THREE.Group();
    const baseHeight = 0.144;

    const botChuteGroup = new THREE.Group();
    const funnelGeo = new THREE.CylinderGeometry(0.42, 0.16, 0.14, 16);
    const funnelMat = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.85, metalness: 0.05 });
    const funnel = new THREE.Mesh(funnelGeo, funnelMat);
    funnel.position.set(0, baseHeight + 0.07, 0);
    funnel.castShadow = true;
    botChuteGroup.add(funnel);

    const botSpoutGeo = new THREE.CylinderGeometry(0.14, 0.14, 0.06, 16);
    const botSpoutMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.8 });
    const botSpout = new THREE.Mesh(botSpoutGeo, botSpoutMat);
    botSpout.position.set(0, baseHeight + 0.03, 0);
    botChuteGroup.add(botSpout);

    const botCordGeo = new THREE.TorusGeometry(0.145, 0.012, 8, 20);
    const botCordMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
    const botCord = new THREE.Mesh(botCordGeo, botCordMat);
    botCord.rotation.x = Math.PI / 2;
    botCord.position.set(0, baseHeight + 0.035, 0);
    botChuteGroup.add(botCord);
    bbGroup.add(botChuteGroup);

    const bodyHeight = 1.00;
    const bodyY = baseHeight + 0.14 + (bodyHeight / 2);
    const bbGeo = new THREE.BoxGeometry(0.92, bodyHeight, 0.92, 12, 10, 12);
    const pos = bbGeo.attributes.position;
    const halfW = 0.46, halfH = bodyHeight / 2, halfD = 0.46;
    for (let i = 0; i < pos.count; i++) {
        let x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
        const nx = x / halfW, ny = y / halfH, nz = z / halfD;
        if (Math.abs(ny) < 0.92) {
            const belly = Math.cos(ny * Math.PI * 0.48);
            x += nx * belly * 0.08;
            z += nz * belly * 0.08;
        }
        pos.setXYZ(i, x, y, z);
    }
    bbGeo.computeVertexNormals();

    const bbTex = getOrCreateBigBagTexture(productName, batch, weightText);
    const bbMat = new THREE.MeshStandardMaterial({
        map: bbTex,
        roughness: 0.78,
        metalness: 0.05
    });
    const body = new THREE.Mesh(bbGeo, bbMat);
    body.position.set(0, bodyY, 0);
    body.castShadow = true;
    bbGroup.add(body);

    const topSpoutY = baseHeight + 0.14 + bodyHeight;
    const topSpoutGeo = new THREE.CylinderGeometry(0.16, 0.21, 0.18, 16);
    const topSpoutMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.75 });
    const topSpout = new THREE.Mesh(topSpoutGeo, topSpoutMat);
    topSpout.position.set(0, topSpoutY + 0.09, 0);
    topSpout.castShadow = true;
    bbGroup.add(topSpout);

    const topCordGeo = new THREE.TorusGeometry(0.175, 0.014, 8, 24);
    const topCordMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
    const topCord = new THREE.Mesh(topCordGeo, topCordMat);
    topCord.rotation.x = Math.PI / 2;
    topCord.position.set(0, topSpoutY + 0.08, 0);
    bbGroup.add(topCord);

    const strapMat = new THREE.MeshStandardMaterial({ color: 0xea580c, roughness: 0.5, metalness: 0.15 });
    const patchMat = new THREE.MeshStandardMaterial({ color: 0x0369a1, roughness: 0.7 });

    const cornerCoords = [
        [-0.37, -0.37],
        [0.37, -0.37],
        [0.37, 0.37],
        [-0.37, 0.37]
    ];

    cornerCoords.forEach(([cx, cz]) => {
        const seamStrapGeo = new THREE.BoxGeometry(0.045, bodyHeight, 0.045);
        const seamStrap = new THREE.Mesh(seamStrapGeo, strapMat);
        seamStrap.position.set(cx, bodyY, cz);
        bbGroup.add(seamStrap);

        const patchGeo = new THREE.BoxGeometry(0.075, 0.14, 0.075);
        const patch = new THREE.Mesh(patchGeo, patchMat);
        patch.position.set(cx, topSpoutY - 0.07, cz);
        bbGroup.add(patch);

        const loopGroup = new THREE.Group();
        loopGroup.position.set(cx, topSpoutY, cz);

        const loopHeight = 0.28;
        const loopWidth = 0.11;
        const legGeo = new THREE.BoxGeometry(0.025, loopHeight, 0.025);
        const topArchGeo = new THREE.BoxGeometry(loopWidth, 0.025, 0.025);

        const leg1 = new THREE.Mesh(legGeo, strapMat);
        leg1.position.set(-loopWidth / 2, loopHeight / 2, 0);
        leg1.castShadow = true;

        const leg2 = new THREE.Mesh(legGeo, strapMat);
        leg2.position.set(loopWidth / 2, loopHeight / 2, 0);
        leg2.castShadow = true;

        const topCross = new THREE.Mesh(topArchGeo, strapMat);
        topCross.position.set(0, loopHeight, 0);
        topCross.castShadow = true;

        loopGroup.add(leg1, leg2, topCross);

        const angle = Math.atan2(cz, cx);
        loopGroup.rotation.y = -angle + Math.PI / 4;

        bbGroup.add(loopGroup);
    });

    return bbGroup;
}

function getAssortmentColor(productName) {
    const p = String(productName || '').toLowerCase();
    if (p.includes('czerwon')) return '#ef4444';
    if (p.includes('żółt') || p.includes('zolt')) return '#eab308';
    if (p.includes('biał') || p.includes('bial')) return '#f8fafc';
    if (p.includes('fiolet')) return '#a855f7';
    if (p.includes('brąz') || p.includes('braz')) return '#b45309';
    if (p.includes('kalka')) return '#06b6d4';
    if (p.includes('włókn') || p.includes('wlokn') || p.includes('sms')) return '#10b981';
    if (p.includes('opakow')) return '#f97316';
    return '#0284c7';
}

function createRealisticShelfAssortmentGroup(slotPallets, bayW, depth, lvlH) {
    const group = new THREE.Group();
    if (!slotPallets || slotPallets.length === 0) return group;

    const count = slotPallets.length;
    const baseH = 0.024;

    if (count === 1) {
        const item = slotPallets[0];
        const pName = item.product_name || item.nazwa || 'ASORTYMENT';
        const batch = item.batch || item.nr_partii || '-';
        const nrPal = item.nr_palety || item.display_id || `ID #${item.id}`;
        let amtStr = '1 szt';
        if (item.amount !== undefined && item.amount !== null) {
            amtStr = `${item.amount} ${item.unit || 'szt'}`;
        }
        const accent = getAssortmentColor(pName);

        const boxW = Math.min(bayW * 0.44, 0.54);
        const boxH = Math.min(lvlH * 0.48, 0.38);
        const boxD = Math.min(depth * 0.72, 0.65);

        for (let i = 0; i < 2; i++) {
            const bx = (i === 0 ? -0.16 : 0.16);
            const bGeo = new THREE.BoxGeometry(boxW * 0.78, boxH, boxD);
            const tex = getShelfItemCardboardTexture(pName, batch, amtStr, nrPal, accent);
            const matFront = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.75, metalness: 0.05 });
            const matSide = sharedMats.cartonBody;
            const mats = [matSide, matSide, matSide, matSide, matFront, matSide];
            const boxMesh = new THREE.Mesh(bGeo, mats);
            boxMesh.position.set(bx, baseH + boxH / 2, 0);
            boxMesh.castShadow = true;
            group.add(boxMesh);
        }
    } else if (count === 2) {
        const halfBay = (bayW * 0.92) / 2;
        const boxW = Math.min(halfBay * 0.88, 0.52);
        const boxH = Math.min(lvlH * 0.50, 0.40);
        const boxD = Math.min(depth * 0.76, 0.68);

        const divGeo = new THREE.BoxGeometry(0.015, boxH * 1.05, depth * 0.82);
        const divMesh = new THREE.Mesh(divGeo, sharedMats.shelfDivider);
        divMesh.position.set(0, baseH + (boxH * 1.05) / 2, 0);
        group.add(divMesh);

        slotPallets.forEach((item, idx) => {
            const pName = item.product_name || item.nazwa || 'ASORTYMENT';
            const batch = item.batch || item.nr_partii || '-';
            const nrPal = item.nr_palety || item.display_id || `ID #${item.id}`;
            let amtStr = '1 szt';
            if (item.amount !== undefined && item.amount !== null) {
                amtStr = `${item.amount} ${item.unit || 'szt'}`;
            }
            const accent = getAssortmentColor(pName);
            const posX = (idx === 0 ? -halfBay * 0.52 : halfBay * 0.52);

            const bGeo = new THREE.BoxGeometry(boxW, boxH, boxD);
            const tex = getShelfItemCardboardTexture(pName, batch, amtStr, nrPal, accent);
            const matFront = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.75, metalness: 0.05 });
            const matSide = sharedMats.cartonBody;
            const mats = [matSide, matSide, matSide, matSide, matFront, matSide];

            const boxMesh = new THREE.Mesh(bGeo, mats);
            boxMesh.position.set(posX, baseH + boxH / 2, 0);
            boxMesh.castShadow = true;
            group.add(boxMesh);
        });
    } else {
        const boxW = Math.min((bayW * 0.88) / count, 0.36);
        const boxH = Math.min(lvlH * 0.46, 0.36);
        const boxD = Math.min(depth * 0.74, 0.65);

        const startX = -((count - 1) * boxW * 1.15) / 2;
        slotPallets.forEach((item, idx) => {
            const pName = item.product_name || item.nazwa || 'ASORTYMENT';
            const batch = item.batch || item.nr_partii || '-';
            const nrPal = item.nr_palety || item.display_id || `ID #${item.id}`;
            let amtStr = '1 szt';
            if (item.amount !== undefined && item.amount !== null) {
                amtStr = `${item.amount} ${item.unit || 'szt'}`;
            }
            const accent = getAssortmentColor(pName);
            const posX = startX + idx * boxW * 1.15;

            const bGeo = new THREE.BoxGeometry(boxW, boxH, boxD);
            const tex = getShelfItemCardboardTexture(pName, batch, amtStr, nrPal, accent);
            const matFront = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.75, metalness: 0.05 });
            const matSide = sharedMats.cartonBody;
            const mats = [matSide, matSide, matSide, matSide, matFront, matSide];

            const boxMesh = new THREE.Mesh(bGeo, mats);
            boxMesh.position.set(posX, baseH + boxH / 2, 0);
            boxMesh.castShadow = true;
            group.add(boxMesh);

            if (idx < count - 1) {
                const divGeo = new THREE.BoxGeometry(0.012, boxH * 0.95, depth * 0.75);
                const divMesh = new THREE.Mesh(divGeo, sharedMats.shelfDivider);
                divMesh.position.set(posX + (boxW * 1.15) / 2, baseH + (boxH * 0.95) / 2, 0);
                group.add(divMesh);
            }
        });
    }

    if (count > 1) {
        const multiTex = getShelfMultiItemBadgeTexture(count);
        const multiMat = new THREE.SpriteMaterial({ map: multiTex, depthTest: false, transparent: true });
        const multiSprite = new THREE.Sprite(multiMat);
        const spriteY = Math.min(lvlH * 0.85, 0.62);
        multiSprite.position.set(0, spriteY, 0);
        multiSprite.scale.set(0.70, 0.20, 1);
        multiSprite.renderOrder = 998;
        group.add(multiSprite);
    }

    return group;
}
