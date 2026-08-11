// scoring.js — 19路加权点目围棋数子（加权 area scoring + 贴目）
//
// 与 scoring.py 1:1 对应的 JS 端口，供 FE-WEB 使用。
// Python dict/set 在此用 Map/Set；坐标键统一用 "r,c" 字符串（1-based，row=1 顶、col=1 左）。
//
// 加权累加：black_weighted = Σ(黑活子位置 W) + Σ(黑独占空位置 W)，white 同理。
// 贴目（difference-komi，对齐改造版 KataGo final_score）：
//   finalWhiteMinusBlack = white_weighted - black_weighted + komi
//   >0 → "W+X.X"，<0 → "B+X.X"，==0 → "0"（1 位小数）。
// 回归保证：W≡1 时与标准 area scoring 等价。
//
// 用法（浏览器）：
//   const weights = parseWeightTable(text);      // 19×19 row-major 文本 → 2D 数组
//   const res = scoreGame(stonesMap, weights, 7.5, deadSet);  // stones: Map<"r,c","B"|"W">
// Node 中可另用 loadWeights(path) 读文件（需 fs）。

"use strict";

const N = 19;

function key(r, c) { return r + "," + c; }

// 解析权重表文本（19 行，每行 19 个空格分隔浮点）→ 2D 数组 [r][c]（0-indexed，r=0 顶）。
function parseWeightTable(text, n) {
  n = n || N;
  const grid = [];
  for (const line of text.split(/\r?\n/)) {
    const s = line.trim();
    if (!s) continue;
    const vals = s.split(/\s+/).map(Number);
    grid.push(vals);
  }
  if (grid.length !== n || grid.some((row) => row.length !== n)) {
    throw new Error("权重表应为 " + n + "×" + n + "，实得 " + grid.length + " 行");
  }
  return grid;
}

// Node 专用：从文件读权重表。浏览器请用 parseWeightTable。
function loadWeights(path, n) {
  const fs = require("fs");
  return parseWeightTable(fs.readFileSync(path, "utf-8"), n);
}

// 取 1-based (r,c) 的权重。weights 可为：2D 数组 [r][c] / Map<"r,c",w> / flat row-major 数组。
function wAt(weights, r, c, rows, cols) {
  if (weights instanceof Map) return weights.get(key(r, c));
  if (Array.isArray(weights)) {
    if (Array.isArray(weights[0])) return weights[r - 1][c - 1];     // 2D
    return weights[(r - 1) * cols + (c - 1)];                         // flat row-major
  }
  throw new TypeError("weights 必须为 2D 数组 / Map / flat 数组");
}

function sumWeights(weights, rows, cols) {
  let total = 0;
  for (let r = 1; r <= rows; r++)
    for (let c = 1; c <= cols; c++) total += wAt(weights, r, c, rows, cols);
  return total;
}

// 加权 area scoring + 贴目。
//   stones: Map<"r,c", "B"|"W">（1-based）
//   weights: 2D 数组 / Map<"r,c",w> / flat row-major
//   komi: 默认 7.5
//   deadStones: Set<"r,c">，默认空
//   rows, cols: 默认 19
// 返回与 scoring.py 完全一致的结构。
function scoreGame(stones, weights, komi, deadStones, rows, cols) {
  komi = (komi === undefined) ? 7.5 : komi;
  deadStones = deadStones || new Set();
  rows = rows || N;
  cols = cols || N;

  // 死子移除：不计入任何一方，其位置变空点参与地域 BFS
  const liveStones = new Map();
  for (const [k, v] of stones) if (!deadStones.has(k)) liveStones.set(k, v);

  let blackWeighted = 0, whiteWeighted = 0;
  let blackStones = 0, whiteStones = 0;
  let blackStonesWeight = 0, whiteStonesWeight = 0;

  for (const [pos, color] of liveStones) {
    const [r, c] = pos.split(",").map(Number);
    const w = wAt(weights, r, c, rows, cols);
    if (color === "B") {
      blackWeighted += w; blackStonesWeight += w; blackStones++;
    } else {
      whiteWeighted += w; whiteStonesWeight += w; whiteStones++;
    }
  }

  let blackTerritory = 0, whiteTerritory = 0, neutral = 0;
  let blackTerritoryWeight = 0, whiteTerritoryWeight = 0, neutralWeight = 0;

  // BFS 找空连通块（空点 = 棋盘内非棋子）。独占判定同 scoring.py。
  const visited = new Set();
  for (let r = 1; r <= rows; r++) {
    for (let c = 1; c <= cols; c++) {
      const k0 = key(r, c);
      if (liveStones.has(k0) || visited.has(k0)) continue;

      const block = [];
      const queue = [[r, c]];
      visited.add(k0);
      let touchesBlack = false, touchesWhite = false;

      while (queue.length) {
        const cur = queue.shift();
        block.push(cur);
        const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
        for (const [dr, dc] of dirs) {
          const nr = cur[0] + dr, nc = cur[1] + dc;
          if (nr < 1 || nr > rows || nc < 1 || nc > cols) continue;
          const nk = key(nr, nc);
          if (liveStones.has(nk)) {
            if (liveStones.get(nk) === "B") touchesBlack = true;
            else touchesWhite = true;
            continue;
          }
          if (!visited.has(nk)) { visited.add(nk); queue.push([nr, nc]); }
        }
      }

      let blockW = 0;
      for (const [pr, pc] of block) blockW += wAt(weights, pr, pc, rows, cols);

      if (touchesBlack && !touchesWhite) {
        blackWeighted += blockW; blackTerritoryWeight += blockW; blackTerritory += block.length;
      } else if (touchesWhite && !touchesBlack) {
        whiteWeighted += blockW; whiteTerritoryWeight += blockW; whiteTerritory += block.length;
      } else {
        neutral += block.length; neutralWeight += blockW;
      }
    }
  }

  // 贴目与胜负（对齐改造版 KataGo final_score：difference-komi，1 位小数）
  const finalWhiteMinusBlack = whiteWeighted - blackWeighted + komi;
  let winner, result;
  if (finalWhiteMinusBlack > 0) { winner = "W"; result = "W+" + finalWhiteMinusBlack.toFixed(1); }
  else if (finalWhiteMinusBlack < 0) { winner = "B"; result = "B+" + (-finalWhiteMinusBlack).toFixed(1); }
  else { winner = ""; result = "0"; }

  return {
    black_weighted: blackWeighted,
    white_weighted: whiteWeighted,
    neutral_weight: neutralWeight,
    komi: komi,
    final_white_minus_black_score: finalWhiteMinusBlack,
    result: result,
    winner: winner,
    detail: {
      black_stones: blackStones,
      white_stones: whiteStones,
      black_territory: blackTerritory,
      white_territory: whiteTerritory,
      neutral: neutral,
      black_stones_weight: blackStonesWeight,
      white_stones_weight: whiteStonesWeight,
      black_territory_weight: blackTerritoryWeight,
      white_territory_weight: whiteTerritoryWeight,
      neutral_weight: neutralWeight,
      dead: deadStones.size,
      sum_weights: sumWeights(weights, rows, cols),
    },
  };
}

// CommonJS 导出（Node）；浏览器中这些名挂在 module.exports 或全局。
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    N, key, parseWeightTable, loadWeights, wAt, sumWeights, scoreGame,
  };
}
