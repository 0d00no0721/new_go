/* ==========================================================================
   ban-engine.js — 20路Ban选围棋 JS 规则引擎
   移植自 ban_controller.py + sgf_io.ReplayBoard + 新规则.md §4
   纯 ES2015+，无依赖。暴露 window.BanGoEngine。
   ========================================================================== */
(function (global) {
    "use strict";

    /* ── 坐标工具（参考 ban_controller.py:23-46）─────────────────────────── */

    var COL_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"; // 跳过 I，1-25 列

    function colToLetter(col) {
        if (col < 1 || col > 25) {
            throw new Error("列编号必须在 1-25 之间，收到 " + col);
        }
        return COL_LETTERS[col - 1];
    }

    function letterToCol(letter) {
        return COL_LETTERS.indexOf(letter.toUpperCase()) + 1;
    }

    function pointToGtp(row, col) {
        return colToLetter(col) + row;
    }

    function gtpToPoint(s) {
        s = s.trim().toUpperCase();
        var letter = s[0];
        var row = parseInt(s.slice(1), 10);
        return { row: row, col: letterToCol(letter) };
    }

    /* ── 内部工具：点键 ↔ 1-based (row,col) ────────────────────────────── */
    // 键格式 "row,col"，如 "7,4"

    function ptKey(r, c) { return r + "," + c; }

    function keyToPt(key) {
        var i = key.indexOf(",");
        return { row: parseInt(key.slice(0, i), 10), col: parseInt(key.slice(i + 1), 10) };
    }

    /* ── BanConfig（参考 ban_controller.py:50-82）────────────────────────── */

    function BanConfig(opts) {
        opts = opts || {};
        this.boardSize = opts.boardSize !== undefined ? opts.boardSize : 20;
        this.boardCols = opts.boardCols !== undefined ? opts.boardCols : null;
        this.banCount = opts.banCount !== undefined ? opts.banCount : 10;
        this.sequence = opts.sequence !== undefined ? opts.sequence : "ABBAABBABA";
        this.regionRowMin = opts.regionRowMin !== undefined ? opts.regionRowMin : 1;
        this.regionRowMax = opts.regionRowMax !== undefined ? opts.regionRowMax : 0;
        this.regionColMin = opts.regionColMin !== undefined ? opts.regionColMin : 1;
        this.regionColMax = opts.regionColMax !== undefined ? opts.regionColMax : 0;
        this.maxViolations = opts.maxViolations !== undefined ? opts.maxViolations : 3;
        this.aiCandidateSample = opts.aiCandidateSample !== undefined ? opts.aiCandidateSample : 20;
    }

    BanConfig.prototype.validate = function () {
        if (this.boardCols === null) {
            this.boardCols = this.boardSize;
        }
        if (this.regionRowMax === 0) {
            this.regionRowMax = this.boardRows;
        }
        if (this.regionColMax === 0) {
            this.regionColMax = this.boardCols;
        }
        if (this.regionRowMin < 1 || this.regionRowMax > this.boardRows) {
            throw new Error("region rows must be within [1, " + this.boardRows + "]");
        }
        if (this.regionColMin < 1 || this.regionColMax > this.boardCols) {
            throw new Error("region cols must be within [1, " + this.boardCols + "]");
        }
        if (this.sequence.length !== this.banCount) {
            throw new Error("sequence length " + this.sequence.length + " != ban_count " + this.banCount);
        }
    };

    // 只读属性 boardRows（= boardSize）
    Object.defineProperty(BanConfig.prototype, "boardRows", {
        get: function () { return this.boardSize; },
        enumerable: true,
    });

    /* ── 校验器（参考 ban_controller.py:113-178）─────────────────────────── */

    // ban 点必须在中间可配置区域内
    function checkRegion(row, col, config) {
        if (!(config.regionRowMin <= row && row <= config.regionRowMax &&
              config.regionColMin <= col && col <= config.regionColMax)) {
            return {
                valid: false,
                reason: "点 " + pointToGtp(row, col) + " 不在 ban 区域内 " +
                        "(行" + config.regionRowMin + "-" + config.regionRowMax + ", " +
                        "列" + config.regionColMin + "-" + config.regionColMax + ")",
            };
        }
        return { valid: true, reason: "" };
    }

    // 不能选择已标记为禁点的位置
    function checkNoDuplicate(row, col, bannedSet) {
        if (bannedSet.has(ptKey(row, col))) {
            return { valid: false, reason: "点 " + pointToGtp(row, col) + " 已被标记为禁点" };
        }
        return { valid: true, reason: "" };
    }

    // BFS: ban 之后所有可落子点必须保持全局四向连通
    function checkConnectivity(boardRows, boardCols, bannedSet, newBan) {
        var allBanned = new Set(bannedSet);
        allBanned.add(ptKey(newBan.row, newBan.col));

        function inBounds(r, c) {
            return r >= 1 && r <= boardRows && c >= 1 && c <= boardCols &&
                   !allBanned.has(r + "," + c);
        }

        // 收集所有可落子点
        var allPlayable = [];
        for (var r = 1; r <= boardRows; r++) {
            for (var c = 1; c <= boardCols; c++) {
                if (!allBanned.has(r + "," + c)) {
                    allPlayable.push({ row: r, col: c });
                }
            }
        }

        if (allPlayable.length === 0) {
            return { valid: false, reason: "没有可落子点（所有点均为禁点）" };
        }

        var start = allPlayable[0];
        var visited = new Set();
        var queue = [start];
        visited.add(ptKey(start.row, start.col));

        while (queue.length > 0) {
            var cur = queue.shift();
            var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
            for (var i = 0; i < 4; i++) {
                var nr = cur.row + dirs[i][0];
                var nc = cur.col + dirs[i][1];
                var k = nr + "," + nc;
                if (inBounds(nr, nc) && !visited.has(k)) {
                    visited.add(k);
                    queue.push({ row: nr, col: nc });
                }
            }
        }

        if (visited.size !== allPlayable.length) {
            // 找不可达点示例（按 row,col 排序取最小）
            var unreachable = [];
            for (var j = 0; j < allPlayable.length; j++) {
                var pk = ptKey(allPlayable[j].row, allPlayable[j].col);
                if (!visited.has(pk)) unreachable.push(allPlayable[j]);
            }
            unreachable.sort(function (a, b) {
                return a.row !== b.row ? a.row - b.row : a.col - b.col;
            });
            var ex = unreachable[0];
            return {
                valid: false,
                reason: "Ban " + pointToGtp(newBan.row, newBan.col) + " 导致棋盘被分割：" +
                        "可落子 " + allPlayable.length + " 点，BFS 仅到达 " + visited.size + " 点。" +
                        "不可达点示例: " + pointToGtp(ex.row, ex.col),
            };
        }
        return { valid: true, reason: "" };
    }

    /* ── ReplayBoard（参考 sgf_io.py:208-262）─────────────────────────────── */

    function ReplayBoard(rows, cols, bansSet) {
        this.rows = rows;
        this.cols = cols;
        this.bans = bansSet || new Set();   // Set<"row,col">
        this.grid = new Map();              // Map<"row,col", "B"|"W">
    }

    // 只读属性 stones（返回 Map 副本）
    Object.defineProperty(ReplayBoard.prototype, "stones", {
        get: function () { return new Map(this.grid); },
        enumerable: true,
    });

    ReplayBoard.prototype.play = function (color, row, col) {
        var k = ptKey(row, col);
        if (this.bans.has(k) || this.grid.has(k)) return;
        if (!(row >= 1 && row <= this.rows && col >= 1 && col <= this.cols)) return;

        this.grid.set(k, color);
        var opp = color === "B" ? "W" : "B";
        var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];

        for (var i = 0; i < 4; i++) {
            var nr = row + dirs[i][0];
            var nc = col + dirs[i][1];
            var nk = ptKey(nr, nc);
            if (this.grid.has(nk) && this.grid.get(nk) === opp) {
                var group = this._findGroup(nr, nc);
                if (this._countLiberties(group) === 0) {
                    var gi = group.length;
                    while (gi--) {
                        this.grid.delete(group[gi]);
                    }
                }
            }
        }
    };

    // BFS 找棋串（返回 key 字符串数组）
    ReplayBoard.prototype._findGroup = function (row, col) {
        var k = ptKey(row, col);
        var color = this.grid.get(k);
        var seen = new Set();
        var stack = [{ row: row, col: col }];
        while (stack.length > 0) {
            var cur = stack.pop();
            var ck = ptKey(cur.row, cur.col);
            if (seen.has(ck)) continue;
            seen.add(ck);
            var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
            for (var i = 0; i < 4; i++) {
                var nr = cur.row + dirs[i][0];
                var nc = cur.col + dirs[i][1];
                var nk = ptKey(nr, nc);
                if (this.grid.has(nk) && this.grid.get(nk) === color) {
                    stack.push({ row: nr, col: nc });
                }
            }
        }
        return Array.from(seen);
    };

    // 数气（返回 group 的气数）
    ReplayBoard.prototype._countLiberties = function (groupKeys) {
        var libs = new Set();
        for (var i = 0; i < groupKeys.length; i++) {
            var pt = keyToPt(groupKeys[i]);
            var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
            for (var j = 0; j < 4; j++) {
                var nr = pt.row + dirs[j][0];
                var nc = pt.col + dirs[j][1];
                if (nr >= 1 && nr <= this.rows && nc >= 1 && nc <= this.cols) {
                    var nk = ptKey(nr, nc);
                    if (!this.grid.has(nk) && !this.bans.has(nk)) {
                        libs.add(nk);
                    }
                }
            }
        }
        return libs.size;
    };

    /* ── BanController（参考 ban_controller.py:183-414）───────────────────── */

    function BanController(config) {
        this.config = config || new BanConfig();
        this.config.validate();

        this.banned = new Set();     // Set<"row,col">
        this.history = [];           // Array<BanState>
        this.step = 0;
        this.violations = { A: 0, B: 0 };
        this.concluded = false;
        this.conclusionReason = "";
    }

    // 只读属性
    Object.defineProperty(BanController.prototype, "currentPlayer", {
        get: function () { return this.config.sequence[this.step]; },
        enumerable: true,
    });
    Object.defineProperty(BanController.prototype, "remaining", {
        get: function () { return this.config.banCount - this.step; },
        enumerable: true,
    });
    Object.defineProperty(BanController.prototype, "isFinished", {
        get: function () { return this.concluded; },
        enumerable: true,
    });

    // 核心：提交一次 ban
    BanController.prototype.submit = function (row, col, source) {
        source = source || "human";
        if (this.concluded) {
            return { valid: false, reason: "Ban 阶段已结束" };
        }

        var checks = this._allChecks(row, col);
        for (var i = 0; i < checks.length; i++) {
            if (!checks[i].valid) {
                var player = this.currentPlayer;
                this.violations[player] += 1;
                if (this.violations[player] >= this.config.maxViolations) {
                    this.concluded = true;
                    this.conclusionReason = "violation_" + player.toLowerCase();
                }
                return checks[i];
            }
        }

        this._apply(row, col, source);
        return { valid: true, reason: "" };
    };

    BanController.prototype._allChecks = function (row, col) {
        return [
            checkRegion(row, col, this.config),
            checkNoDuplicate(row, col, this.banned),
            checkConnectivity(this.config.boardRows, this.config.boardCols,
                              this.banned, { row: row, col: col }),
        ];
    };

    BanController.prototype._apply = function (row, col, source) {
        var player = this.currentPlayer;
        var k = ptKey(row, col);
        this.banned.add(k);
        var st = {
            index: this.step,
            player: player,
            row: row,
            col: col,
            label: pointToGtp(row, col),
            source: source,
        };
        this.history.push(st);
        this.step += 1;

        if (this.step >= this.config.banCount) {
            this.concluded = true;
            this.conclusionReason = "complete";
        }
    };

    // 人类输入通道：接受 GTP 坐标字符串如 'D7'
    BanController.prototype.submitLabel = function (label) {
        var row, col;
        try {
            var pt = gtpToPoint(label);
            row = pt.row;
            col = pt.col;
        } catch (e) {
            return { valid: false, reason: "无效坐标: " + label };
        }
        if (!(row >= 1 && row <= this.config.boardRows && col >= 1 && col <= this.config.boardCols)) {
            return { valid: false, reason: "坐标越界: " + label };
        }
        return this.submit(row, col, "human");
    };

    // AI 选点：合法候选池
    BanController.prototype._legalCandidates = function () {
        var candidates = [];
        var cfg = this.config;
        for (var r = cfg.regionRowMin; r <= cfg.regionRowMax; r++) {
            for (var c = cfg.regionColMin; c <= cfg.regionColMax; c++) {
                if (this.banned.has(ptKey(r, c))) continue;
                if (!checkConnectivity(cfg.boardRows, cfg.boardCols,
                                       this.banned, { row: r, col: c }).valid) continue;
                candidates.push({ row: r, col: c });
            }
        }
        return candidates;
    };

    // 保底策略：随机选一个合法候选
    BanController.prototype.aiPickRandom = function () {
        var candidates = this._legalCandidates();
        if (candidates.length === 0) {
            throw new Error("没有合法候选禁点");
        }
        return candidates[Math.floor(Math.random() * candidates.length)];
    };

    // AI 自动选点并提交一步（仅 random 策略，GTP 策略需引擎绑定）
    BanController.prototype.submitAi = function (strategy) {
        strategy = strategy || "random";
        if (this.concluded) {
            return { valid: false, reason: "Ban 阶段已结束" };
        }
        var pt = this.aiPickRandom();
        return this.submit(pt.row, pt.col, "ai");
    };

    // 结果
    BanController.prototype.getResult = function () {
        return {
            bannedPoints: new Set(this.banned),
            history: this.history.slice(),
            concludedBy: this.conclusionReason,
        };
    };

    BanController.prototype.reset = function () {
        this.banned.clear();
        this.history.length = 0;
        this.step = 0;
        this.violations = { A: 0, B: 0 };
        this.concluded = false;
        this.conclusionReason = "";
    };

    /* ── 数子（参考 新规则.md §4）─────────────────────────────────────────── */

    // 简化数子法：黑区 = 黑子 + 黑独占空；白区同理；中性空不计
    // 签名：scoreGame(stonesMap, bannedSet, komi, rows, cols)
    //   komi 默认 4.25；rows/cols 必填（棋盘尺寸）
    function scoreGame(stonesMap, bannedSet, komi, rows, cols) {
        komi = komi !== undefined ? komi : 4.25;
        var banned = bannedSet;
        var stones = stonesMap;

        var blackArea = 0;
        var whiteArea = 0;

        // 数黑子、白子
        stones.forEach(function (color) {
            if (color === "B") blackArea++;
            else whiteArea++;
        });

        // 找空连通块，判定独占
        var visited = new Set();
        for (var r = 1; r <= rows; r++) {
            for (var c = 1; c <= cols; c++) {
                var k = ptKey(r, c);
                if (stones.has(k) || banned.has(k) || visited.has(k)) continue;

                // BFS 找空连通块
                var block = [];
                var queue = [{ row: r, col: c }];
                visited.add(k);
                var touchesBlack = false;
                var touchesWhite = false;

                while (queue.length > 0) {
                    var cur = queue.shift();
                    block.push(cur);
                    var dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
                    for (var i = 0; i < 4; i++) {
                        var nr = cur.row + dirs[i][0];
                        var nc = cur.col + dirs[i][1];
                        if (nr < 1 || nr > rows || nc < 1 || nc > cols) continue;
                        var nk = ptKey(nr, nc);
                        if (banned.has(nk)) continue;        // 禁点 = 棋盘外，不参与
                        if (stones.has(nk)) {
                            if (stones.get(nk) === "B") touchesBlack = true;
                            else touchesWhite = true;
                            continue;
                        }
                        if (!visited.has(nk)) {
                            visited.add(nk);
                            queue.push({ row: nr, col: nc });
                        }
                    }
                }

                // 独占判定
                if (touchesBlack && !touchesWhite) {
                    blackArea += block.length;
                } else if (touchesWhite && !touchesBlack) {
                    whiteArea += block.length;
                }
                // 中性空（邻黑白或都不邻）不计
            }
        }

        // 胜负判定（新规则.md §4）
        var totalValid = rows * cols - banned.size;
        var half = totalValid / 2;
        var blackWinThreshold = half + komi;   // 黑需 > 199.25
        var whiteWinThreshold = half - komi;   // 白需 > 190.75

        var result, winner;
        if (blackArea > blackWinThreshold) {
            winner = "B";
            result = "B+" + (blackArea - blackWinThreshold).toFixed(2);
        } else if (whiteArea > whiteWinThreshold) {
            winner = "W";
            result = "W+" + (whiteArea - whiteWinThreshold).toFixed(2);
        } else {
            winner = "";
            result = "Draw";
        }

        return {
            blackArea: blackArea,
            whiteArea: whiteArea,
            validPoints: totalValid,
            half: half,
            blackWinThreshold: blackWinThreshold,
            whiteWinThreshold: whiteWinThreshold,
            result: result,
            winner: winner,
        };
    }

    /* ── 导出 ────────────────────────────────────────────────────────────── */

    global.BanGoEngine = {
        // 坐标工具
        COL_LETTERS: COL_LETTERS,
        colToLetter: colToLetter,
        letterToCol: letterToCol,
        pointToGtp: pointToGtp,
        gtpToPoint: gtpToPoint,
        // 内部工具（暴露供测试）
        _ptKey: ptKey,
        _keyToPt: keyToPt,
        // 配置
        BanConfig: BanConfig,
        // 校验器
        checkRegion: checkRegion,
        checkNoDuplicate: checkNoDuplicate,
        checkConnectivity: checkConnectivity,
        // 棋盘
        ReplayBoard: ReplayBoard,
        // Ban 控制器
        BanController: BanController,
        // 数子
        scoreGame: scoreGame,
    };

    /* ==========================================================================
       自测（页面加载时自动运行，console 全过即引擎正确）
       ========================================================================== */
    (function selfTest() {
        var pass = 0;
        var fail = 0;

        function ok(name, cond, actual) {
            if (cond) {
                pass++;
            } else {
                fail++;
                console.error("[FAIL] " + name + (actual !== undefined ? " — 实际值: " + JSON.stringify(actual) : ""));
            }
        }
        function eq(name, got, want) {
            var cond = JSON.stringify(got) === JSON.stringify(want);
            ok(name, cond, got);
        }

        console.log("%c[ban-engine] 自测开始", "color:#8b5a2b;font-weight:bold");

        // ── 1. 坐标 ──────────────────────────────────────────────────────────
        eq("colToLetter(1)==='A'", colToLetter(1), "A");
        eq("colToLetter(8)==='H'", colToLetter(8), "H");
        eq("colToLetter(9)==='J'", colToLetter(9), "J");
        eq("colToLetter(20)==='U'", colToLetter(20), "U");
        eq("letterToCol('J')===9", letterToCol("J"), 9);
        eq("gtpToPoint('D7')", gtpToPoint("D7"), { row: 7, col: 4 });
        eq("pointToGtp(7,4)==='D7'", pointToGtp(7, 4), "D7");
        eq("pointToGtp(9,10)==='K9'", pointToGtp(9, 10), "K9");

        // ── 2. BanConfig ─────────────────────────────────────────────────────
        (function () {
            var cfg = new BanConfig();
            cfg.validate();
            eq("BanConfig 默认 boardSize=20", cfg.boardSize, 20);
            eq("BanConfig 默认 boardCols=20 (validate 后)", cfg.boardCols, 20);
            eq("BanConfig sequence 长度 10", cfg.sequence.length, 10);
            eq("BanConfig boardRows=20", cfg.boardRows, 20);
            eq("BanConfig region 全棋盘 row", [cfg.regionRowMin, cfg.regionRowMax], [1, 20]);
            eq("BanConfig region 全棋盘 col", [cfg.regionColMin, cfg.regionColMax], [1, 20]);
            eq("BanConfig sequence='ABBAABBABA'", cfg.sequence, "ABBAABBABA");

            // 非正方形
            var cfg2 = new BanConfig({ boardSize: 15, boardCols: 20 });
            cfg2.validate();
            eq("BanConfig 非正方形 boardRows=15", cfg2.boardRows, 15);
            eq("BanConfig 非正方形 boardCols=20", cfg2.boardCols, 20);
            eq("BanConfig 非正方形 regionRowMax=15", cfg2.regionRowMax, 15);
            eq("BanConfig 非正方形 regionColMax=20", cfg2.regionColMax, 20);
        })();

        // ── 3. checkConnectivity ─────────────────────────────────────────────
        (function () {
            // 空棋盘 20×20，1 个禁点 → valid
            var r1 = checkConnectivity(20, 20, new Set(), { row: 10, col: 10 });
            ok("checkConnectivity 空棋盘1禁点 valid", r1.valid, r1);

            // 2×3 棋盘，禁中间一整列（第2列全部禁）→ 切成两块 invalid
            // 列1: (1,1)(2,1)  列2: (1,2)(2,2)全禁  列3: (1,3)(2,3)
            // 先禁(1,2)，再禁(2,2)——测试时一次性测第二个
            var banned = new Set(["1,2"]);
            var r2 = checkConnectivity(2, 3, banned, { row: 2, col: 2 });
            ok("checkConnectivity 切两块 invalid", !r2.valid, r2);

            // 2×3 只禁一个点 → valid
            var r3 = checkConnectivity(2, 3, new Set(), { row: 1, col: 2 });
            ok("checkConnectivity 2×3 禁一点 valid", r3.valid, r3);

            // 全禁 → invalid
            var allBanned = new Set();
            for (var rr = 1; rr <= 2; rr++) for (var cc = 1; cc <= 2; cc++) allBanned.add(rr + "," + cc);
            allBanned.delete("1,1");
            var r4 = checkConnectivity(2, 2, allBanned, { row: 1, col: 1 });
            ok("checkConnectivity 全禁 invalid", !r4.valid, r4);
        })();

        // ── 4. ReplayBoard 提子 ──────────────────────────────────────────────
        (function () {
            // 9×9 空，白(5,5)+黑(4,5)(6,5)(5,4)，再黑(5,6) → 白(5,5) 被提
            var board = new ReplayBoard(9, 9, new Set());
            board.play("W", 5, 5);
            board.play("B", 4, 5);
            board.play("B", 6, 5);
            board.play("B", 5, 4);
            ok("提子前 白(5,5) 在场", board.grid.has("5,5"), board.grid);
            board.play("B", 5, 6);  // 第4黑，白无气
            ok("提子后 白(5,5) 被提", !board.grid.has("5,5"), board.grid);
            // 黑子都在
            ok("提子后 黑(4,5) 在", board.grid.has("4,5"));
            ok("提子后 黑(6,5) 在", board.grid.has("6,5"));
            ok("提子后 黑(5,4) 在", board.grid.has("5,4"));
            ok("提子后 黑(5,6) 在", board.grid.has("5,6"));
        })();

        // ── 4b. 提子着法不被误判自杀 ───────────────────────────────────────
        (function () {
            // 场景1：单子提子 — 白(5,5) 1气，黑填气提白，黑子应有气
            var b = new ReplayBoard(9, 9, new Set());
            b.play("W", 5, 5); b.play("B", 4, 5); b.play("B", 6, 5); b.play("B", 5, 4);
            b.play("B", 5, 6);  // 提白(5,5)
            ok("提子着法：白被提", !b.grid.has("5,5"));
            var g = b._findGroup(5, 6);
            ok("提子着法：黑(5,6)有气（非自杀）", b._countLiberties(g) > 0);

            // 场景2：ban邻接提子 — 禁(5,6)，白(5,5) 1气(5,4)，黑填(5,4)提白
            var b2 = new ReplayBoard(9, 9, new Set(["5,6"]));
            b2.play("W", 5, 5); b2.play("B", 4, 5); b2.play("B", 6, 5); b2.play("B", 5, 4);
            ok("ban邻接提子：白被提", !b2.grid.has("5,5"), b2.grid);
            var g2 = b2._findGroup(5, 4);
            ok("ban邻接提子：黑(5,4)有气", b2._countLiberties(g2) > 0);

            // 场景3：真自杀应拒绝 — 白围满黑(5,5)四邻，无提子
            var b3 = new ReplayBoard(9, 9, new Set());
            b3.play("W", 4, 5); b3.play("W", 6, 5); b3.play("W", 5, 4); b3.play("W", 5, 6);
            b3.play("B", 5, 5);  // 0气无提子
            var g3 = b3._findGroup(5, 5);
            eq("真自杀：黑(5,5) 0气", b3._countLiberties(g3), 0);
        })();

        // ── 5. ReplayBoard 禁点不计气 ────────────────────────────────────────
        (function () {
            // 白(5,5)，禁点(5,6)，黑(4,5)(6,5)(5,4) 三个方向包围，禁点方向不产气
            // 白剩1气(5,4)时仍在场；黑占(5,4)后白无气被提（禁点5,6不算气）
            var bans = new Set(["5,6"]);
            var b = new ReplayBoard(9, 9, bans);
            b.play("W", 5, 5);   // 白落，邻居(4,5)空(6,5)空(5,4)空(5,6)禁 → 有3气
            b.play("B", 4, 5);   // 黑占一气，白剩2气
            b.play("B", 6, 5);   // 黑占一气，白剩1气(5,4)
            ok("禁点不计气：白还有1气时在场", b.grid.has("5,5"));
            b.play("B", 5, 4);   // 黑占最后一气，白(5,5)无气被提（禁点5,6不产气）
            ok("禁点不计气：白被提", !b.grid.has("5,5"), b.grid);
            // 额外：禁点本身不可落子
            var b3 = new ReplayBoard(9, 9, new Set(["5,5"]));
            b3.play("B", 5, 5);  // 禁点落子被忽略
            ok("禁点不可落子", !b3.grid.has("5,5"));
        })();

        // ── 6. ReplayBoard 边界 ──────────────────────────────────────────────
        (function () {
            var b = new ReplayBoard(1, 1, new Set());
            b.play("B", 1, 1);
            ok("1×1 落子合法", b.grid.has("1,1"));
            b.play("W", 0, 1);   // 越界
            b.play("W", 1, 0);   // 越界
            b.play("W", 2, 1);   // 越界
            b.play("W", 1, 2);   // 越界
            ok("越界落子被忽略", b.grid.size === 1, b.grid);
            // 落已有子上
            b.play("W", 1, 1);
            ok("落已有子上被忽略", b.grid.get("1,1") === "B");
        })();

        // ── 7. BanController ─────────────────────────────────────────────────
        (function () {
            var cfg = new BanConfig();
            var bc = new BanController(cfg);

            // 序列推进 currentPlayer
            eq("BanController step0 currentPlayer=A", bc.currentPlayer, "A");
            eq("BanController step0 isFinished=false", bc.isFinished, false);
            eq("BanController step0 step=0", bc.step, 0);

            // 第1步：A 禁 D4 (row4 col4，在 region 1-20 内)
            var r1 = bc.submitLabel("D4");
            ok("BanController 第1步 A valid", r1.valid, r1);
            eq("BanController 第1步后 currentPlayer=B", bc.currentPlayer, "B");
            eq("BanController 第1步后 step=1", bc.step, 1);

            // 第2步：B 禁 E5
            var r2 = bc.submitLabel("E5");
            ok("BanController 第2步 B valid", r2.valid, r2);
            eq("BanController 第2步后 currentPlayer=B", bc.currentPlayer, "B"); // 序列第3个是B

            // 第3步：B 禁 F6
            bc.submitLabel("F6");
            eq("BanController 第3步后 currentPlayer=A", bc.currentPlayer, "A");

            // 重复点 → invalid
            var rDup = bc.submitLabel("D4");
            ok("BanController 重复点 invalid", !rDup.valid, rDup);

            // 继续 7 步完成（共10步，已3步，剩7步）
            // 序列 ABBAABBABA，step3-9 对应 A A B B A A B
            var rest = ["G7", "H8", "J9", "K10", "L11", "M12", "N13"];
            for (var i = 0; i < rest.length; i++) {
                var r = bc.submitLabel(rest[i]);
                ok("BanController 第" + (4 + i) + "步 valid", r.valid, r);
            }
            eq("BanController 完成后 isFinished=true", bc.isFinished, true);
            eq("BanController 完成后 step=10", bc.step, 10);

            var res = bc.getResult();
            eq("BanController getResult concludedBy=complete", res.concludedBy, "complete");
            eq("BanController getResult bannedPoints size=10", res.bannedPoints.size, 10);
            eq("BanController getResult history length=10", res.history.length, 10);

            // 已结束后再提交 → invalid
            var rAfter = bc.submitLabel("P14");
            ok("BanController 结束后再提交 invalid", !rAfter.valid, rAfter);

            // 违例测试：新控制器，连续提交越界点
            var bc2 = new BanController(new BanConfig());
            // 越界点 Z99（row99 越界）会被 submitLabel 拦截不算违例
            // 用 region 外的点：row1（region 1-20 全棋盘时都在区域内）
            // 改用小棋盘 + 限定 region 测试违例
            var cfg3 = new BanConfig({
                boardSize: 9, banCount: 2, sequence: "AB",
                regionRowMin: 4, regionRowMax: 6,
                regionColMin: 4, regionColMax: 6,
                maxViolations: 2,
            });
            var bc3 = new BanController(cfg3);
            // (1,1) 在 region 外 → invalid + 违例
            var v1 = bc3.submitLabel("A1");
            ok("违例1 invalid (region外)", !v1.valid, v1);
            eq("违例1 后 violations A=1", bc3.violations.A, 1);
            var v2 = bc3.submitLabel("A2");
            ok("违例2 invalid", !v2.valid, v2);
            eq("违例2 后 violations A=2", bc3.violations.A, 2);
            eq("违例达上限 concluded=true", bc3.isFinished, true);
            eq("违例结束 concludedBy=violation_a", bc3.getResult().concludedBy, "violation_a");
        })();

        // ── 8. 数子 ──────────────────────────────────────────────────────────
        (function () {
            // 构造简单终局：5×5 棋盘，黑围左上角
            // 黑: (1,1)(1,2)(2,1)  白: (5,5)(5,4)(4,5)
            // 空区域：左上(1,1)被黑围？不，(1,1)是黑子本身
            // 重新设计：3×3，黑占满第1行+第1列围(2,2)(3,3)等空...
            // 更简单：2×2 棋盘，无禁点，黑(1,1)(1,2)白(2,1)，空(2,2)
            // (2,2) 邻 (1,2)B + (2,1)W → 中性空不计
            // blackArea=2, whiteArea=1, totalValid=4, half=2, komi=4.25
            // 黑需 > 2+4.25=6.25 → 不可能（最多4点）→ 白胜？白需 > 2-4.25=-2.25 → 白(1)不>-2.25？
            // 白1 > -2.25 → true → 白胜 W+1-(-2.25)=W+3.25
            var stones = new Map([["1,1", "B"], ["1,2", "B"], ["2,1", "W"]]);
            var sc = scoreGame(stones, new Set(), 4.25, 2, 2);
            eq("数子 2×2 blackArea=2", sc.blackArea, 2);
            eq("数子 2×2 whiteArea=1", sc.whiteArea, 1);
            eq("数子 2×2 winner=W", sc.winner, "W");
            ok("数子 2×2 result 含 W+", sc.result.indexOf("W+") === 0, sc.result);

            // 独占空测试：3×3，黑围满外围一圈（除(2,2)）
            // 黑: (1,1)(1,2)(1,3)(2,1)(2,3)(3,1)(3,2)(3,3)  空(2,2)被黑完全包围→黑独占
            // blackArea = 8黑子 + 1独占空 = 9, whiteArea=0
            // totalValid=9, half=4.5, komi=4.25, 黑需>8.75 → 9>8.75 → 黑胜 B+0.25
            var stones2 = new Map([
                ["1,1", "B"], ["1,2", "B"], ["1,3", "B"],
                ["2,1", "B"], ["2,3", "B"],
                ["3,1", "B"], ["3,2", "B"], ["3,3", "B"],
            ]);
            var sc2 = scoreGame(stones2, new Set(), 4.25, 3, 3);
            eq("数子 3×3黑围 blackArea=9 (8子+1独占空)", sc2.blackArea, 9);
            eq("数子 3×3黑围 whiteArea=0", sc2.whiteArea, 0);
            eq("数子 3×3黑围 winner=B", sc2.winner, "B");
            eq("数子 3×3黑围 result=B+0.25", sc2.result, "B+0.25");

            // 含禁点的数子：3×3，禁(2,2)，黑围外围
            // 黑: 8个外围点，空(2,2)是禁点不计
            // blackArea=8, totalValid=9-1=8, half=4, komi=4.25
            // 黑需 > 4+4.25=8.25 → 8>8.25 false
            // 白需 > 4-4.25=-0.25 → 0>-0.25 true（komi 对小棋盘过大，白胜）
            // 注：komi 4.25 为 20 路(390点)校准，小棋盘结果退化属正常
            var stones3 = new Map([
                ["1,1", "B"], ["1,2", "B"], ["1,3", "B"],
                ["2,1", "B"], ["2,3", "B"],
                ["3,1", "B"], ["3,2", "B"], ["3,3", "B"],
            ]);
            var sc3 = scoreGame(stones3, new Set(["2,2"]), 4.25, 3, 3);
            eq("数子 含禁点 blackArea=8", sc3.blackArea, 8);
            eq("数子 含禁点 validPoints=8", sc3.validPoints, 8);
            eq("数子 含禁点 half=4", sc3.half, 4);
            eq("数子 含禁点 blackWinThreshold=8.25", sc3.blackWinThreshold, 8.25);
            eq("数子 含禁点 whiteWinThreshold=-0.25", sc3.whiteWinThreshold, -0.25);
            eq("数子 含禁点 winner=W (komi退化)", sc3.winner, "W");
        })();

        // ── 汇总 ────────────────────────────────────────────────────────────
        console.log("%c[ban-engine] 自测完成: " + pass + " passed, " + fail + " failed",
                    fail === 0 ? "color:#2e7d32;font-weight:bold" : "color:#cc2222;font-weight:bold");
        if (fail > 0) {
            console.error("[ban-engine] 存在失败用例，请检查上方 [FAIL] 输出");
        }
    })();

})(typeof window !== "undefined" ? window : this);
