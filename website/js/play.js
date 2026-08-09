/* ==========================================================================
   play.js — 20路Ban选围棋 在线对弈（人vs人本地双人）
   依赖：ban-engine.js（window.BanGoEngine）、main.js（导航高亮）
   状态机：setup → ban → play → dead → over
   ========================================================================== */
(function () {
    "use strict";

    var ENG = window.BanGoEngine;
    var SVG_NS = "http://www.w3.org/2000/svg";

    /* ── 常量 ──────────────────────────────────────────────────────────── */
    var CELL = 30;          // SVG 单位每格
    var MARGIN = 24;        // SVG 边距（坐标标签空间）
    var STONE_R = 13;       // 棋子半径
    var KOMI = 4.25;

    /* ── 状态 ──────────────────────────────────────────────────────────── */
    var state = {
        phase: "setup",         // setup | ban | play | dead | over
        rows: 20,
        cols: 20,
        bc: null,               // BanController
        board: null,            // ReplayBoard
        banned: null,           // Set<"row,col">（ban 阶段后冻结）
        currentColor: "B",      // 正式对局当前轮（B/W）
        moves: [],              // [{color, gtp}]
        lastMove: null,         // {row, col} | null
        passes: 0,
        captures: { B: 0, W: 0 },   // B 提白子数 / W 提黑子数
        deadStones: new Set(),      // Set<"row,col"> 标记的死子
        resignWinner: null,        // 认输时的胜方
        result: null,              // scoreGame 结果
    };

    /* ── DOM 引用 ──────────────────────────────────────────────────────── */
    var elBoard, elSetupBar, elStatusPanel, elControls, elToast, elResultModal;

    /* ── 工具：坐标转换 ────────────────────────────────────────────────── */
    // 引擎 1-based (row, col)，row=1 底部 → SVG (i, j)，i=0 顶部
    function rowToI(row, rows) { return rows - row; }
    function colToJ(col) { return col - 1; }
    function iToRow(i, rows) { return rows - i; }
    function jToCol(j) { return j + 1; }

    function svgX(j) { return MARGIN + j * CELL; }
    function svgY(i) { return MARGIN + i * CELL; }

    function ptKey(r, c) { return r + "," + c; }

    /* ── 星位计算（0-indexed SVG 坐标）────────────────────────────────── */
    function starPoints(rows, cols) {
        var pts = [];
        if (rows === cols) {
            // 四角星位（4路点）
            pts.push([3, 3], [3, cols - 4], [rows - 4, 3], [rows - 4, cols - 4]);
            // 天元（奇数路才有正中心）
            if (rows % 2 === 1) pts.push([Math.floor(rows / 2), Math.floor(cols / 2)]);
        } else {
            pts.push([Math.floor(rows / 2), Math.floor(cols / 2)]);
        }
        return pts.filter(function (p) {
            return p[0] >= 0 && p[0] < rows && p[1] >= 0 && p[1] < cols;
        });
    }

    /* ── SVG 元素创建辅助 ──────────────────────────────────────────────── */
    function svgEl(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            for (var k in attrs) {
                if (attrs.hasOwnProperty(k)) el.setAttribute(k, attrs[k]);
            }
        }
        return el;
    }

    /* ── 棋盘渲染（每次状态变化重建 SVG）───────────────────────────────── */
    function renderBoard() {
        var rows = state.rows, cols = state.cols;
        var pxW = 2 * MARGIN + CELL * (cols - 1);
        var pxH = 2 * MARGIN + CELL * (rows - 1);

        // 清空
        while (elBoard.firstChild) elBoard.removeChild(elBoard.firstChild);
        elBoard.setAttribute("viewBox", "0 0 " + pxW + " " + pxH);
        elBoard.setAttribute("preserveAspectRatio", "xMidYMid meet");

        var banned = state.banned || new Set();
        var isBannedSvg = function (i, j) {
            return banned.has(ptKey(iToRow(i, rows), jToCol(j)));
        };

        // 1. 棋盘背景
        elBoard.appendChild(svgEl("rect", {
            x: 0, y: 0, width: pxW, height: pxH,
            fill: "var(--card)",
        }));

        // 2. 网格线逐段画（涉及禁点的段跳过）
        // 横向 (i,j)→(i,j+1)
        for (var i = 0; i < rows; i++) {
            for (var j = 0; j < cols - 1; j++) {
                if (isBannedSvg(i, j) || isBannedSvg(i, j + 1)) continue;
                elBoard.appendChild(svgEl("line", {
                    x1: svgX(j), y1: svgY(i), x2: svgX(j + 1), y2: svgY(i),
                    class: "grid-line",
                }));
            }
        }
        // 纵向 (i,j)→(i+1,j)
        for (var i2 = 0; i2 < rows - 1; i2++) {
            for (var j2 = 0; j2 < cols; j2++) {
                if (isBannedSvg(i2, j2) || isBannedSvg(i2 + 1, j2)) continue;
                elBoard.appendChild(svgEl("line", {
                    x1: svgX(j2), y1: svgY(i2), x2: svgX(j2), y2: svgY(i2 + 1),
                    class: "grid-line",
                }));
            }
        }

        // 3. 星位（跳过禁点）
        var stars = starPoints(rows, cols);
        for (var s = 0; s < stars.length; s++) {
            var si = stars[s][0], sj = stars[s][1];
            if (isBannedSvg(si, sj)) continue;
            elBoard.appendChild(svgEl("circle", {
                cx: svgX(sj), cy: svgY(si), r: 3, class: "star-point",
            }));
        }

        // 4. 坐标标签
        for (var cj = 0; cj < cols; cj++) {
            var letter = ENG.colToLetter(jToCol(cj));
            elBoard.appendChild(svgEl("text", {
                x: svgX(cj), y: 10, class: "coord-label", textContent: letter,
            })).textContent = letter;
            elBoard.appendChild(svgEl("text", {
                x: svgX(cj), y: pxH - 10, class: "coord-label",
            })).textContent = letter;
        }
        for (var ri = 0; ri < rows; ri++) {
            var num = String(iToRow(ri, rows));
            elBoard.appendChild(svgEl("text", {
                x: 10, y: svgY(ri), class: "coord-label",
            })).textContent = num;
            elBoard.appendChild(svgEl("text", {
                x: pxW - 10, y: svgY(ri), class: "coord-label",
            })).textContent = num;
        }

        // 5. 棋子
        var stones = state.board ? state.board.grid : new Map();
        var deadSet = state.deadStones;
        stones.forEach(function (color, key) {
            var parts = key.split(",");
            var r = parseInt(parts[0], 10), c = parseInt(parts[1], 10);
            var si2 = rowToI(r, rows), sj2 = colToJ(c);
            var isDead = deadSet.has(key);
            var cls = (color === "B" ? "stone-black" : "stone-white") + (isDead ? " dead-stone" : "");
            elBoard.appendChild(svgEl("circle", {
                cx: svgX(sj2), cy: svgY(si2), r: STONE_R, class: cls,
            }));
        });

        // 6. 最后一手标记
        if (state.lastMove) {
            var li = rowToI(state.lastMove.row, rows);
            var lj = colToJ(state.lastMove.col);
            elBoard.appendChild(svgEl("circle", {
                cx: svgX(lj), cy: svgY(li), r: 4, class: "last-mark",
            }));
        }

        // 7. 死子标记（phase=dead 时，在棋子上画叉）
        if (state.phase === "dead") {
            deadSet.forEach(function (key) {
                var parts = key.split(",");
                var r = parseInt(parts[0], 10), c = parseInt(parts[1], 10);
                var di = rowToI(r, rows), dj = colToJ(c);
                var d = 9;
                elBoard.appendChild(svgEl("line", {
                    x1: svgX(dj) - d, y1: svgY(di) - d,
                    x2: svgX(dj) + d, y2: svgY(di) + d, class: "dead-mark",
                }));
                elBoard.appendChild(svgEl("line", {
                    x1: svgX(dj) - d, y1: svgY(di) + d,
                    x2: svgX(dj) + d, y2: svgY(di) - d, class: "dead-mark",
                }));
            });
        }

        // 8. 透明热区（每个交叉点一个 rect，绑定 click）
        var interactive = (state.phase === "ban" || state.phase === "play" || state.phase === "dead");
        for (var hi = 0; hi < rows; hi++) {
            for (var hj = 0; hj < cols; hj++) {
                (function (i, j) {
                    var rect = svgEl("rect", {
                        x: svgX(j) - CELL / 2, y: svgY(i) - CELL / 2,
                        width: CELL, height: CELL,
                        class: "hover-cell" + (interactive ? "" : " disabled"),
                    });
                    rect.addEventListener("click", function () { onCellClick(i, j); });
                    elBoard.appendChild(rect);
                })(hi, hj);
            }
        }
    }

    /* ── 交叉点点击分发 ────────────────────────────────────────────────── */
    function onCellClick(i, j) {
        var row = iToRow(i, state.rows);
        var col = jToCol(j);
        if (state.phase === "ban") {
            handleBanClick(row, col);
        } else if (state.phase === "play") {
            handlePlayClick(row, col);
        } else if (state.phase === "dead") {
            handleDeadClick(row, col);
        }
    }

    /* ── Ban 阶段点击 ──────────────────────────────────────────────────── */
    function handleBanClick(row, col) {
        var gtp = ENG.pointToGtp(row, col);
        var res = state.bc.submitLabel(gtp);
        if (res.valid) {
            renderBoard();
            updateStatus();
            if (state.bc.isFinished) {
                var result = state.bc.getResult();
                if (result.concludedBy === "complete") {
                    initPlay();
                } else {
                    // 违例判负
                    state.phase = "over";
                    state.resignWinner = result.concludedBy === "violation_a" ? "B" : "W";
                    updateStatus();
                    updateControls();
                    showToast("Ban 阶段违例判负：" + (state.resignWinner === "B" ? "黑" : "白") + "胜");
                }
            }
        } else {
            showToast(res.reason, true);
            updateStatus();
        }
    }

    /* ── 正式对局点击 ──────────────────────────────────────────────────── */
    function handlePlayClick(row, col) {
        var key = ptKey(row, col);
        var gtp = ENG.pointToGtp(row, col);

        // UI 预校验
        if (state.banned.has(key)) { showToast(gtp + " 是禁点", true); return; }
        if (state.board.grid.has(key)) { showToast(gtp + " 已有棋子", true); return; }

        var color = state.currentColor;
        var sizeBefore = state.board.grid.size;

        // 落子
        state.board.play(color, row, col);

        // 检测是否成功落子
        if (!state.board.grid.has(key)) {
            showToast("此处不可落子", true);
            return;
        }

        // 计算提子数
        var captured = sizeBefore + 1 - state.board.grid.size;
        if (captured > 0) {
            state.captures[color] += captured;
        }

        // 自杀检测：落子后己方棋串无气则拒绝
        // （提子着法因被提点变空，棋串必有气，不会误判）
        var group = state.board._findGroup(row, col);
        var libs = state.board._countLiberties(group);
        if (libs === 0) {
            // 自杀，撤销
            state.board.grid.delete(key);
            showToast("自杀手，不可落子", true);
            return;
        }

        // 记录
        state.moves.push({ color: color, gtp: gtp });
        state.lastMove = { row: row, col: col };
        state.passes = 0;
        state.currentColor = (color === "B") ? "W" : "B";

        renderBoard();
        updateStatus();
        updateControls();
    }

    /* ── 标记死子点击 ──────────────────────────────────────────────────── */
    function handleDeadClick(row, col) {
        var key = ptKey(row, col);
        if (!state.board.grid.has(key)) return; // 只能标记棋子
        if (state.deadStones.has(key)) {
            state.deadStones.delete(key);
        } else {
            state.deadStones.add(key);
        }
        renderBoard();
    }

    /* ── 阶段切换 ──────────────────────────────────────────────────────── */
    function initBan() {
        var cfg = new ENG.BanConfig({
            boardSize: state.rows,
            boardCols: state.cols,
        });
        cfg.validate();
        state.bc = new ENG.BanController(cfg);
        state.banned = state.bc.banned;
        state.board = null;
        state.moves = [];
        state.lastMove = null;
        state.passes = 0;
        state.captures = { B: 0, W: 0 };
        state.deadStones = new Set();
        state.resignWinner = null;
        state.result = null;
        state.phase = "ban";
        renderBoard();
        updateStatus();
        updateControls();
    }

    function initPlay() {
        state.board = new ENG.ReplayBoard(state.rows, state.cols, state.banned);
        state.currentColor = "B";   // 黑先
        state.moves = [];
        state.lastMove = null;
        state.passes = 0;
        state.captures = { B: 0, W: 0 };
        state.deadStones = new Set();
        state.phase = "play";
        renderBoard();
        updateStatus();
        updateControls();
    }

    function initDead() {
        state.phase = "dead";
        state.deadStones = new Set();
        renderBoard();
        updateStatus();
        updateControls();
    }

    function doScore() {
        // 复制 stones，移除死子
        var stonesCopy = new Map(state.board.grid);
        state.deadStones.forEach(function (key) {
            stonesCopy.delete(key);
        });
        state.result = ENG.scoreGame(stonesCopy, state.banned, KOMI, state.rows, state.cols);
        state.phase = "over";
        renderBoard();
        updateStatus();
        updateControls();
        showResult();
    }

    function newGame() {
        state.phase = "setup";
        state.bc = null;
        state.board = null;
        state.banned = null;
        state.moves = [];
        state.lastMove = null;
        state.passes = 0;
        state.captures = { B: 0, W: 0 };
        state.deadStones = new Set();
        state.resignWinner = null;
        state.result = null;
        elResultModal.classList.remove("show");
        renderBoard();
        updateStatus();
        updateControls();
    }

    /* ── 控制按钮动作 ──────────────────────────────────────────────────── */
    function actPass() {
        if (state.phase !== "play") return;
        var color = state.currentColor;
        state.moves.push({ color: color, gtp: "pass" });
        state.passes += 1;
        state.lastMove = null;
        state.currentColor = (color === "B") ? "W" : "B";
        if (state.passes >= 2) {
            initDead();
            showToast("双方 Pass，进入标记死子阶段");
        } else {
            renderBoard();
            updateStatus();
            updateControls();
            showToast((color === "B" ? "黑" : "白") + "方 Pass");
        }
    }

    function actResign() {
        if (state.phase !== "play") return;
        var color = state.currentColor;
        state.resignWinner = (color === "B") ? "W" : "B";
        state.phase = "over";
        renderBoard();
        updateStatus();
        updateControls();
        showResult();
    }

    function actStart() {
        initBan();
    }

    /* ── 状态面板更新 ──────────────────────────────────────────────────── */
    function updateStatus() {
        var html = "";
        var phase = state.phase;

        // 阶段徽章
        var badgeMap = {
            setup: ["phase-setup", "选择尺寸"],
            ban: ["phase-ban", "Ban 选阶段"],
            play: ["phase-play", "正式对局"],
            dead: ["phase-dead", "标记死子"],
            over: ["phase-over", "对局结束"],
        };
        var badge = badgeMap[phase];
        html += '<span class="phase-badge ' + badge[0] + '">' + badge[1] + '</span>';

        if (phase === "setup") {
            html += '<div class="status-row"><span class="label">棋盘</span><span class="value">' +
                    state.rows + ' × ' + state.cols + '</span></div>';
            html += '<p style="font-size:13px;color:var(--text-soft);margin-top:10px;">选择棋盘尺寸后点击「开始对局」。</p>';
        } else if (phase === "ban") {
            var bc = state.bc;
            var player = bc.currentPlayer;
            var roleName = player === "A" ? "选手A（白）" : "选手B（黑）";
            html += '<div class="status-row"><span class="label">当前轮次</span><span class="value accent">' +
                    roleName + '</span></div>';
            html += '<div class="status-row"><span class="label">进度</span><span class="value">第 ' +
                    (bc.step + 1) + ' / ' + bc.config.banCount + ' 次</span></div>';
            html += '<div class="status-row"><span class="label">违例</span><span class="value">A ' +
                    bc.violations.A + '/' + bc.config.maxViolations + ' · B ' +
                    bc.violations.B + '/' + bc.config.maxViolations + '</span></div>';
            html += '<div class="status-row"><span class="label">禁点</span><span class="value ban-red">' +
                    bc.banned.size + ' 个</span></div>';
            var banLabels = [];
            bc.banned.forEach(function (k) {
                var p = k.split(",");
                banLabels.push(ENG.pointToGtp(parseInt(p[0], 10), parseInt(p[1], 10)));
            });
            banLabels.sort();
            html += '<div class="ban-list">' + (banLabels.join(" ") || "（无）") + '</div>';
        } else if (phase === "play") {
            var color = state.currentColor;
            var colorName = color === "B" ? "黑方" : "白方";
            html += '<div class="status-row"><span class="label">当前轮次</span><span class="value accent">' +
                    colorName + '</span></div>';
            html += '<div class="status-row"><span class="label">手数</span><span class="value">' +
                    state.moves.length + '</span></div>';
            html += '<div class="status-row"><span class="label">提子</span><span class="value">黑提白 ' +
                    state.captures.B + ' · 白提黑 ' + state.captures.W + '</span></div>';
            html += '<div class="status-row"><span class="label">连续 Pass</span><span class="value">' +
                    state.passes + '</span></div>';
            html += '<div class="status-row"><span class="label">最后一手</span><span class="value">' +
                    (state.lastMove ? ENG.pointToGtp(state.lastMove.row, state.lastMove.col) : "—") + '</span></div>';
            html += '<div class="status-row"><span class="label">禁点</span><span class="value ban-red">' +
                    state.banned.size + ' 个</span></div>';
        } else if (phase === "dead") {
            html += '<div class="status-row"><span class="label">提示</span><span class="value">点击棋子标记死子</span></div>';
            html += '<div class="status-row"><span class="label">已标记死子</span><span class="value ban-red">' +
                    state.deadStones.size + ' 个</span></div>';
            html += '<div class="status-row"><span class="label">禁点</span><span class="value ban-red">' +
                    state.banned.size + ' 个</span></div>';
        } else if (phase === "over") {
            if (state.result) {
                html += '<div class="status-row"><span class="label">结果</span><span class="value accent">' +
                        state.result.result + '</span></div>';
                html += '<div class="status-row"><span class="label">黑区</span><span class="value">' +
                        state.result.blackArea + '</span></div>';
                html += '<div class="status-row"><span class="label">白区</span><span class="value">' +
                        state.result.whiteArea + '</span></div>';
            } else if (state.resignWinner) {
                html += '<div class="status-row"><span class="label">结果</span><span class="value accent">' +
                        state.resignWinner + '+R（认输）</span></div>';
            } else {
                // 违例判负
                html += '<div class="status-row"><span class="label">结果</span><span class="value accent">' +
                        state.resignWinner + '+R（违例）</span></div>';
            }
        }

        elStatusPanel.querySelector(".status-content").innerHTML = html;
    }

    /* ── 控制按钮更新 ──────────────────────────────────────────────────── */
    function updateControls() {
        var phase = state.phase;
        var html = "";
        if (phase === "setup") {
            html += '<button class="btn btn-primary" id="btn-start">开始对局</button>';
        } else if (phase === "ban") {
            html += '<button class="btn btn-secondary" id="btn-new">新对局</button>';
        } else if (phase === "play") {
            html += '<button class="btn btn-secondary" id="btn-pass">Pass</button>';
            html += '<button class="btn btn-secondary" id="btn-resign">认输</button>';
            html += '<button class="btn btn-secondary" id="btn-new">新对局</button>';
        } else if (phase === "dead") {
            html += '<button class="btn btn-primary" id="btn-score">确认数子</button>';
            html += '<button class="btn btn-secondary" id="btn-new">新对局</button>';
        } else if (phase === "over") {
            html += '<button class="btn btn-primary" id="btn-new">新对局</button>';
        }
        elControls.innerHTML = html;

        // 绑定
        var btnStart = document.getElementById("btn-start");
        if (btnStart) btnStart.addEventListener("click", actStart);
        var btnPass = document.getElementById("btn-pass");
        if (btnPass) btnPass.addEventListener("click", actPass);
        var btnResign = document.getElementById("btn-resign");
        if (btnResign) btnResign.addEventListener("click", actResign);
        var btnScore = document.getElementById("btn-score");
        if (btnScore) btnScore.addEventListener("click", doScore);
        var btnNew = document.getElementById("btn-new");
        if (btnNew) btnNew.addEventListener("click", newGame);
    }

    /* ── Toast 提示 ────────────────────────────────────────────────────── */
    var toastTimer = null;
    function showToast(msg, isError) {
        elToast.textContent = msg;
        elToast.className = "toast show" + (isError ? " error" : "");
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            elToast.className = "toast" + (isError ? " error" : "");
        }, 2500);
    }

    /* ── 结果框 ────────────────────────────────────────────────────────── */
    function showResult() {
        var box = elResultModal.querySelector(".result-box");
        if (state.result) {
            var r = state.result;
            var winnerName = r.winner === "B" ? "黑胜" : (r.winner === "W" ? "白胜" : "平局");
            var neutral = r.validPoints - r.blackArea - r.whiteArea;
            box.innerHTML =
                '<h3>对局结束</h3>' +
                '<div class="result-line result-winner-' + r.winner + '">' + winnerName + '</div>' +
                '<div style="text-align:center;font-size:18px;color:var(--accent);margin-bottom:14px;">' + r.result + '</div>' +
                '<table class="result-detail">' +
                '<tr><td>黑区（子+独占空）</td><td>' + r.blackArea + '</td></tr>' +
                '<tr><td>白区（子+独占空）</td><td>' + r.whiteArea + '</td></tr>' +
                '<tr><td>中性空</td><td>' + neutral + '</td></tr>' +
                '<tr><td>有效点位</td><td>' + r.validPoints + '</td></tr>' +
                '<tr><td>基准（半数）</td><td>' + r.half + '</td></tr>' +
                '<tr><td>贴目</td><td>' + KOMI + '</td></tr>' +
                '<tr><td>黑胜线</td><td>＞ ' + r.blackWinThreshold + '</td></tr>' +
                '<tr><td>白胜线</td><td>＞ ' + r.whiteWinThreshold + '</td></tr>' +
                '<tr><td>死子数</td><td>' + state.deadStones.size + '</td></tr>' +
                '</table>' +
                '<button class="btn btn-primary" id="btn-modal-new">新对局</button>';
        } else if (state.resignWinner) {
            var w = state.resignWinner === "B" ? "黑" : "白";
            box.innerHTML =
                '<h3>对局结束</h3>' +
                '<div class="result-line result-winner-' + state.resignWinner + '">' + w + '胜</div>' +
                '<div style="text-align:center;font-size:16px;color:var(--text-soft);margin-bottom:14px;">对方认输</div>' +
                '<button class="btn btn-primary" id="btn-modal-new">新对局</button>';
        }
        elResultModal.classList.add("show");
        var btnModalNew = document.getElementById("btn-modal-new");
        if (btnModalNew) btnModalNew.addEventListener("click", newGame);
    }

    /* ── 尺寸选择 ──────────────────────────────────────────────────────── */
    function onSizeChange() {
        var selRows = document.getElementById("sel-rows");
        var selCols = document.getElementById("sel-cols");
        state.rows = parseInt(selRows.value, 10);
        state.cols = parseInt(selCols.value, 10);
        renderBoard();
        updateStatus();
    }

    /* ── 初始化 ────────────────────────────────────────────────────────── */
    function init() {
        elBoard = document.getElementById("board-svg");
        elSetupBar = document.getElementById("setup-bar");
        elStatusPanel = document.getElementById("status-panel");
        elControls = document.getElementById("controls");
        elToast = document.getElementById("toast");
        elResultModal = document.getElementById("result-modal");

        var selRows = document.getElementById("sel-rows");
        var selCols = document.getElementById("sel-cols");
        selRows.addEventListener("change", onSizeChange);
        selCols.addEventListener("change", onSizeChange);

        var btnStartBar = document.getElementById("btn-start-bar");
        if (btnStartBar) btnStartBar.addEventListener("click", actStart);

        renderBoard();
        updateStatus();
        updateControls();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
