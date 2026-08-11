/* ==========================================================================
   heatmap3d.js — 加权点目权重热力图（3D 视图）
   加载方式：<script type="module">，经由 importmap 从 CDN 引入 Three.js r160
   依赖（同页经典脚本）：scoring.js（window.parseWeightTable）、
                       weight_data.js（window.WEIGHT_TABLE_TEXT）
   复用：2D 的 same diverging 色阶（weightColor 公式一致），保证 2D/3D 颜色完全一致
   - 19×19 柱状图：柱高 = 该点权重 W（映射到 [0.15, 3.2]，数据 min→短、max→高）
   - 柱色 = weightColor 色阶（<1 冷蓝、>1 暖红、1.0 中性）
   - 鼠标拖拽旋转（OrbitControls）+ 滚轮缩放
   - hover/click 柱 → #info-box 显示 GTP 坐标 + W（与 2D 共用同一信息框）
   - 棋盘网格线 + 星位标记 + 坐标标签（canvas sprite）
   - 与 2D 同页切换（#view-switch），默认 2D，首次切 3D 时惰性初始化
   ========================================================================== */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

(function () {
    "use strict";

    var N = 19;
    var GTP_COLS = "ABCDEFGHJKLMNOPQRST";  // 跳过 I

    // ── 权重解析（复用 RULES scoring.js / weight_data.js 全局）──
    var weights = null;
    try {
        weights = window.parseWeightTable(window.WEIGHT_TABLE_TEXT, N);
    } catch (e) {
        console.error("[heatmap3d] 权重解析失败:", e);
    }

    var container = document.getElementById("heatmap-3d");
    var btn2d = document.getElementById("view-2d");
    var btn3d = document.getElementById("view-3d");
    if (!weights || !container) return;

    // ── 色阶：与 heatmap.js weightColor() 同一公式，返回 [r,g,b]（3D 用）──
    function weightColorRGB(w) {
        var t = Math.log2(w > 0 ? w : 1e-9);
        t = Math.max(-1, Math.min(1, t));
        var r, g, b;
        if (t >= 0) {
            r = Math.round(238 + (200 - 238) * t);
            g = Math.round(232 + (50 - 232) * t);
            b = Math.round(196 + (40 - 196) * t);
        } else {
            var tt = -t;
            r = Math.round(238 + (50 - 238) * tt);
            g = Math.round(232 + (110 - 232) * tt);
            b = Math.round(196 + (190 - 196) * tt);
        }
        return [r, g, b];
    }

    // ── 坐标 ──
    function coordLabel(r, c) {
        return GTP_COLS[c] + (N - r);   // r=0 顶部 → 行号 N-r（底部为 1）
    }

    function showInfo(r, c, w) {
        var box = document.getElementById("info-box");
        if (!box) return;
        box.innerHTML =
            "<span class='coord'>" + coordLabel(r, c) + "</span>" +
            "<span class='wt'>W = " + w.toFixed(4) + "</span>";
    }

    // ── 三维布局 ──
    var OFF = -(N - 1) / 2;   // -9，棋盘居中
    var H_MIN = 0.15, H_MAX = 3.2;   // 柱高映射范围
    var BARSQ = 0.82;                // 柱底边宽/深

    var scene, camera, renderer, controls, barGroup;
    var pinnedMesh = null;
    var raycaster, mouse;
    var inited = false;

    function computeRange() {
        var mn = Infinity, mx = -Infinity;
        for (var r = 0; r < N; r++) for (var c = 0; c < N; c++) {
            if (weights[r][c] < mn) mn = weights[r][c];
            if (weights[r][c] > mx) mx = weights[r][c];
        }
        return { mn: mn, mx: mx };
    }

    function init() {
        var width = container.clientWidth || 640;
        var height = container.clientHeight || 560;

        scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf3ead8);

        camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
        camera.position.set(22, 30, 32);
        camera.lookAt(0, 1, 0);

        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(width, height);
        renderer.setPixelRatio(window.devicePixelRatio || 1);
        container.appendChild(renderer.domElement);

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.12;
        controls.target.set(0, 1.2, 0);
        controls.minDistance = 6;
        controls.maxDistance = 90;
        controls.maxPolarAngle = Math.PI / 2 - 0.06;   // 不移到棋盘下方
        controls.update();

        // 光照
        scene.add(new THREE.AmbientLight(0xffffff, 0.62));
        var d1 = new THREE.DirectionalLight(0xffffff, 0.85);
        d1.position.set(24, 44, 24);
        scene.add(d1);
        var d2 = new THREE.DirectionalLight(0xffffff, 0.30);
        d2.position.set(-26, 18, -22);
        scene.add(d2);

        buildBoard();

        raycaster = new THREE.Raycaster();
        mouse = new THREE.Vector2();

        renderer.domElement.addEventListener("mousemove", onHover);
        renderer.domElement.addEventListener("click", onClick);
        window.addEventListener("resize", onResize);

        inited = true;
        animate();
    }

    function buildBoard() {
        var range = computeRange();
        var span = (range.mx - range.mn) || 1;
        var wood = new THREE.Color(0x5a4631);

        barGroup = new THREE.Group();

        // 19×19 柱
        for (var r = 0; r < N; r++) {
            for (var c = 0; c < N; c++) {
                var w = weights[r][c];
                var h = H_MIN + ((w - range.mn) / span) * H_MAX;
                var geo = new THREE.BoxGeometry(BARSQ, h, BARSQ);
                var rgb = weightColorRGB(w);
                var mat = new THREE.MeshStandardMaterial({
                    color: new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255),
                    roughness: 0.45,
                    metalness: 0.05,
                    emissive: 0x000000,
                });
                var mesh = new THREE.Mesh(geo, mat);
                mesh.position.set(c + OFF, h / 2, r + OFF);
                mesh.userData = { r: r, c: c, w: w };
                barGroup.add(mesh);
            }
        }
        scene.add(barGroup);

        // 棋盘网格线（地面）
        var linePts = [];
        for (var i = 0; i < N; i++) {   // 横线（z 恒定）
            linePts.push(i + OFF, 0.002, OFF, i + OFF, 0.002, N - 1 + OFF);
        }
        for (var j = 0; j < N; j++) {   // 竖线（x 恒定）
            linePts.push(OFF, 0.002, j + OFF, N - 1 + OFF, 0.002, j + OFF);
        }
        var lineGeo = new THREE.BufferGeometry();
        lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePts, 3));
        var lineMat = new THREE.LineBasicMaterial({ color: wood });
        scene.add(new THREE.LineSegments(lineGeo, lineMat));

        // 星位
        var stars = [[3, 3], [3, 9], [3, 15], [9, 3], [9, 9], [9, 15], [15, 3], [15, 9], [15, 15]];
        var starGeo = new THREE.CylinderGeometry(0.30, 0.30, 0.07, 20);
        var starMat = new THREE.MeshBasicMaterial({ color: wood });
        for (var si = 0; si < stars.length; si++) {
            var sm = new THREE.Mesh(starGeo, starMat);
            sm.position.set(stars[si][1] + OFF, 0.035, stars[si][0] + OFF);
            scene.add(sm);
        }

        // 坐标标签（sprite）
        for (var c2 = 0; c2 < N; c2++) {
            var lt = makeLabel(GTP_COLS[c2]);
            lt.position.set(c2 + OFF, 0.05, N - 1 + OFF + 1.05);
            scene.add(lt);
        }
        for (var r2 = 0; r2 < N; r2++) {
            var rl = makeLabel(String(N - r2));
            rl.position.set(OFF - 1.05, 0.05, r2 + OFF);
            scene.add(rl);
        }
    }

    function makeLabel(text) {
        var canvas = document.createElement("canvas");
        canvas.width = 128;
        canvas.height = 64;
        var ctx = canvas.getContext("2d");
        ctx.font = "600 40px 'Consolas','Courier New',monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#5a4631";
        ctx.fillText(text, 64, 34);
        var tex = new THREE.CanvasTexture(canvas);
        tex.minFilter = THREE.LinearFilter;
        var mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
        var sprite = new THREE.Sprite(mat);
        sprite.scale.set(1.1, 0.55, 1);
        return sprite;
    }

    // ── 拾取（hover / click）──
    function pick(event) {
        var rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);
        var hits = raycaster.intersectObjects(barGroup.children, false);
        if (hits.length) return hits[0].object;
        return null;
    }

    function setHighlight(mesh, colorHex) {
        if (mesh) mesh.material.emissive.setHex(colorHex);
    }

    function onHover(event) {
        var hit = pick(event);
        if (hit) {
            setHighlight(pinnedMesh, 0x000000);
            if (pinnedMesh !== hit) setHighlight(pinnedMesh, pinnedMesh.userData.pinnedHex || 0x000000);
            hit.userData.pinnedHex = hit.material.emissive.getHex();
            setHighlight(hit, 0x665533);
            showInfo(hit.userData.r, hit.userData.c, hit.userData.w);
        } else {
            setHighlight(pinnedMesh, pinnedMesh ? (pinnedMesh.userData.pinnedHex || 0x000000) : 0x000000);
        }
    }

    function onClick(event) {
        var hit = pick(event);
        if (!hit) return;
        if (pinnedMesh === hit) {   // 取消 pin
            pinnedMesh.material.emissive.setHex(0x000000);
            pinnedMesh.userData.pinnedHex = 0x000000;
            pinnedMesh = null;
            return;
        }
        if (pinnedMesh) {
            pinnedMesh.material.emissive.setHex(0x000000);
            pinnedMesh.userData.pinnedHex = 0x000000;
        }
        pinnedMesh = hit;
        hit.material.emissive.setHex(0xa08040);
        hit.userData.pinnedHex = 0xa08040;
        showInfo(hit.userData.r, hit.userData.c, hit.userData.w);
    }

    function onResize() {
        if (!inited) return;
        var w = container.clientWidth || 640;
        var h = container.clientHeight || 560;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
    }

    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }

    // ── 2D / 3D 切换 ──
    var svg = document.getElementById("heatmap-svg");

    function setView(view) {
        var is3d = view === "3d";
        btn2d.classList.toggle("active", !is3d);
        btn3d.classList.toggle("active", is3d);
        container.classList.toggle("active", is3d);
        if (svg) svg.style.display = is3d ? "none" : "";
        if (is3d && !inited) {
            setTimeout(function () {   // 确保容器已可见再测量宽高
                init();
                onResize();
            }, 0);
        } else if (is3d && inited) {
            onResize();
        }
    }

    if (btn2d && btn3d) {
        btn2d.addEventListener("click", function () { setView("2d"); });
        btn3d.addEventListener("click", function () { setView("3d"); });
    }
})();