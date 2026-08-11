/* ==========================================================================
   heatmap.js — 加权点目权重热力图（交互）
   依赖：scoring.js（parseWeightTable / N）、weight_data.js（WEIGHT_TABLE_TEXT）
   - 19×19 SVG 棋盘，每点按其权重 W 着色（diverging colormap：<1 冷蓝、>1 暖红、1.0 中性）
   - 悬停显示 GTP 坐标 + W 值；点击固定显示
   - 图例显示色阶
   ========================================================================== */
(function () {
    "use strict";

    var N = 19;
    var GTP_COLS = "ABCDEFGHJKLMNOPQRST";  // 跳过 I

    // ── 权重解析（复用 RULES scoring.js）──
    var weights = null;
    try {
        weights = parseWeightTable(window.WEIGHT_TABLE_TEXT, N);  // 2D [r][c]
    } catch (e) {
        console.error("[heatmap] 权重解析失败:", e);
    }

    // ── 色阶（与 GUI 一致的 diverging colormap）──
    function weightColor(w) {
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
        return "rgb(" + r + "," + g + "," + b + ")";
    }

    // ── 坐标 ──
    function coordLabel(r, c) {
        return GTP_COLS[c] + (N - r);   // r=0 顶部 → 行号 N-r（底部为 1）
    }

    // ── 渲染 ──
    function build() {
        var svg = document.getElementById("heatmap-svg");
        if (!svg || !weights) return;

        var NS = "http://www.w3.org/2000/svg";
        var size = 640, margin = 36;
        var cell = (size - 2 * margin) / (N - 1);
        var X = function (c) { return margin + c * cell; };
        var Y = function (r) { return margin + r * cell; };

        svg.setAttribute("viewBox", "0 0 " + size + " " + size);

        // 每个交叉点：背景色块（权重颜色）
        for (var r = 0; r < N; r++) {
            for (var c = 0; c < N; c++) {
                var w = weights[r][c];
                var cellNode = document.createElementNS(NS, "rect");
                cellNode.setAttribute("x", X(c) - cell / 2);
                cellNode.setAttribute("y", Y(r) - cell / 2);
                cellNode.setAttribute("width", cell);
                cellNode.setAttribute("height", cell);
                cellNode.setAttribute("fill", weightColor(w));
                cellNode.setAttribute("class", "heat-cell");
                cellNode.setAttribute("data-r", r);
                cellNode.setAttribute("data-c", c);
                cellNode.setAttribute("data-w", w.toFixed(4));
                cellNode.addEventListener("click", function () { pin(this); });
                svg.appendChild(cellNode);
            }
        }

        // 网格线
        var lineColor = "#3d2f14";
        for (var r2 = 0; r2 < N; r2++) {
            var hl = document.createElementNS(NS, "line");
            hl.setAttribute("x1", margin); hl.setAttribute("y1", Y(r2));
            hl.setAttribute("x2", size - margin); hl.setAttribute("y2", Y(r2));
            hl.setAttribute("stroke", lineColor); hl.setAttribute("stroke-width", 1);
            svg.appendChild(hl);
        }
        for (var c2 = 0; c2 < N; c2++) {
            var vl = document.createElementNS(NS, "line");
            vl.setAttribute("x1", X(c2)); vl.setAttribute("y1", margin);
            vl.setAttribute("x2", X(c2)); vl.setAttribute("y2", size - margin);
            vl.setAttribute("stroke", lineColor); vl.setAttribute("stroke-width", 1);
            svg.appendChild(vl);
        }

        // 星位
        var stars = [[3,3],[3,9],[3,15],[9,3],[9,9],[9,15],[15,3],[15,9],[15,15]];
        for (var si = 0; si < stars.length; si++) {
            var s = document.createElementNS(NS, "circle");
            s.setAttribute("cx", X(stars[si][1])); s.setAttribute("cy", Y(stars[si][0]));
            s.setAttribute("r", 4); s.setAttribute("fill", lineColor);
            svg.appendChild(s);
        }

        // 坐标标签（列）
        var labelNS = NS;
        for (var c3 = 0; c3 < N; c3++) {
            var lt = document.createElementNS(labelNS, "text");
            lt.setAttribute("x", X(c3)); lt.setAttribute("y", 16);
            lt.setAttribute("class", "coord-label"); lt.textContent = GTP_COLS[c3];
            svg.appendChild(lt);
            var lb = document.createElementNS(labelNS, "text");
            lb.setAttribute("x", X(c3)); lb.setAttribute("y", size - 8);
            lb.setAttribute("class", "coord-label"); lb.textContent = GTP_COLS[c3];
            svg.appendChild(lb);
        }
        for (var r3 = 0; r3 < N; r3++) {
            var rl = document.createElementNS(labelNS, "text");
            rl.setAttribute("x", 14); rl.setAttribute("y", Y(r3) + 4);
            rl.setAttribute("class", "coord-label"); rl.textContent = N - r3;
            svg.appendChild(rl);
            var rr = document.createElementNS(labelNS, "text");
            rr.setAttribute("x", size - 8); rr.setAttribute("y", Y(r3) + 4);
            rr.setAttribute("class", "coord-label"); rr.textContent = N - r3;
            svg.appendChild(rr);
        }
    }

    // ── 悬停（cell 上 mousemove 由事件委托处理）──
    function showInfo(r, c, w) {
        var box = document.getElementById("info-box");
        box.innerHTML =
            "<span class='coord'>" + coordLabel(r, c) + "</span>" +
            "<span class='wt'>W = " + w.toFixed(4) + "</span>";
    }

    function pin(cell) {
        var existing = document.querySelectorAll(".heat-cell.pinned");
        for (var i = 0; i < existing.length; i++) existing[i].classList.remove("pinned");
        cell.classList.add("pinned");
        var r = +cell.getAttribute("data-r");
        var c = +cell.getAttribute("data-c");
        var w = +cell.getAttribute("data-w");
        showInfo(r, c, w);
    }

    function attachEvents() {
        var svg = document.getElementById("heatmap-svg");
        if (!svg) return;
        svg.addEventListener("mouseover", function (e) {
            var cell = e.target.closest ? e.target.closest(".heat-cell") : null;
            if (cell) {
                var r = +cell.getAttribute("data-r");
                var c = +cell.getAttribute("data-c");
                var w = +cell.getAttribute("data-w");
                showInfo(r, c, w);
            }
        });
    }

    // ── 图例 ──
    function buildLegend() {
        var legend = document.getElementById("legend-gradient");
        if (!legend) return;
        legend.style.background =
            "linear-gradient(to right, " +
            weightColor(0.53) + ", " +
            weightColor(0.75) + ", " +
            weightColor(1.0) + ", " +
            weightColor(1.5) + ", " +
            weightColor(2.76) + ")";
    }

    function showSummary() {
        if (!weights) return;
        var sum = 0, mn = Infinity, mx = -Infinity;
        for (var r = 0; r < N; r++) for (var c = 0; c < N; c++) {
            sum += weights[r][c];
            if (weights[r][c] < mn) mn = weights[r][c];
            if (weights[r][c] > mx) mx = weights[r][c];
        }
        var el = document.getElementById("heatmap-stat");
        if (el) {
            el.innerHTML =
                "ΣW = " + sum.toFixed(2) + " &nbsp;·&nbsp; 范围 [" + mn.toFixed(3) + ", " + mx.toFixed(3) + "]" +
                " &nbsp;·&nbsp; 天元 K10 = " + weights[9][9].toFixed(3) +
                " &nbsp;·&nbsp; 星位 D16 = " + weights[3][3].toFixed(3);
        }
    }

    if (weights) {
        build();
        buildLegend();
        showSummary();
        attachEvents();
    }
})();