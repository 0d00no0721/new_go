# -*- coding: utf-8 -*-
"""
scoring.py — 19路加权点目围棋数子（加权 area scoring + 贴目）

纯 Python 实现，不依赖引擎，可独立测试。GUI / CLI / web 共用本模块。

设计要点
--------
- BFS 数空结构移植自 ban-selection/scoring.py：空连通块只邻一色→该色独占空；
  邻双色或都不邻→中性（dame）。
- 加权累加：每个棋子和每个独占空点都按其位置权重 W 计值，而非每点 1 目。
  black_weighted = Σ(黑活子位置 W) + Σ(黑独占空位置 W)
  white_weighted = Σ(白活子位置 W) + Σ(白独占空位置 W)
- 贴目用引擎约定（difference-komi，非 ban-selection 的 half+komi）：
  finalWhiteMinusBlack = white_weighted - black_weighted + komi
  与改造版 KataGo 的 final_score 对齐：>0→W+X.X，<0→B+X.X，==0→0（1 位小数）。
- 死子：dead_stones 显式传入，移除后其位置变空点参与地域 BFS（同 ban-selection）。

坐标约定
--------
- stones / dead_stones 用 1-based (row, col)，row=1 顶、col=1 左（同 ban-selection）。
- 权重表 19×19 row-major：文件第 1 行=棋盘顶行，第 1 列=最左列。
  load_weights() 读为 2D list（0-indexed [r][c]，r=0 顶）。

回归保证
--------
W≡1 时：black_weighted==黑子数+黑独占空数，white_weighted 同理，
finalWhiteMinusBlack == 标准中国数子（area scoring）的 white-black+komi，
即与标准 area scoring 完全等价（见 test_scoring.py 与引擎对照）。
"""
from __future__ import annotations

N = 19


def load_weights(path: str, n: int = N) -> list[list[float]]:
    """读权重表文件（n 行，每行 n 个空格分隔浮点）→ 2D list [r][c]（0-indexed，r=0 顶）。

    用于把 weight_table_final.txt 等 row-major 文件加载为 score_game 可吃的 weights。
    """
    grid: list[list[float]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            grid.append([float(x) for x in line.split()])
    if len(grid) != n or any(len(row) != n for row in grid):
        raise ValueError(
            f"权重表应为 {n}×{n}，实得 {len(grid)} 行 / 列长 {[len(r) for r in grid]}"
        )
    return grid


def _w_at(weights, r: int, c: int, rows: int, cols: int) -> float:
    """取 1-based (r,c) 的权重。weights 可为：
    - 2D list/tuple [r][c]（0-indexed，load_weights 的产物）；
    - dict {(r,c): w}（1-based，与 stones 同坐标系）；
    - flat list/tuple row-major（长度 rows*cols）。
    """
    if isinstance(weights, dict):
        return float(weights[(r, c)])
    if isinstance(weights, (list, tuple)):
        if weights and isinstance(weights[0], (list, tuple)):
            return float(weights[r - 1][c - 1])          # 2D
        return float(weights[(r - 1) * cols + (c - 1)])   # flat row-major
    raise TypeError("weights 必须为 2D list / dict / flat list")


def _sum_weights(weights, rows: int, cols: int) -> float:
    total = 0.0
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            total += _w_at(weights, r, c, rows, cols)
    return total


def score_game(
    stones: dict[tuple[int, int], str],            # (row,col) 1-based -> "B"/"W"
    weights,                                         # 19×19：2D list / dict / flat
    komi: float = 7.5,
    dead_stones: set[tuple[int, int]] | None = None,  # 死子 1-based，默认空
    rows: int = N,
    cols: int = N,
) -> dict:
    """加权 area scoring + 贴目。返回:

    {
        "black_weighted": float,            # 黑加权总分（子×W + 独占空×W）
        "white_weighted": float,            # 白加权总分
        "neutral_weight": float,            # 中性空点权重和
        "komi": float,
        "final_white_minus_black_score": float,  # 引擎 finalWhiteMinusBlackScore
        "result": str,                      # "B+X.X" / "W+X.X" / "0"（1 位小数，对齐引擎）
        "winner": str,                      # "B" / "W" / ""
        "detail": {
            "black_stones": int, "white_stones": int,
            "black_territory": int, "white_territory": int, "neutral": int,
            "black_stones_weight": float, "white_stones_weight": float,
            "black_territory_weight": float, "white_territory_weight": float,
            "neutral_weight": float,
            "dead": int, "sum_weights": float,
        },
    }
    """
    if dead_stones is None:
        dead_stones = set()

    # 死子移除：不计入任何一方，其位置变空点参与地域 BFS（同 ban-selection）
    live_stones = {k: v for k, v in stones.items() if k not in dead_stones}

    black_weighted = 0.0
    white_weighted = 0.0
    black_stones = 0
    white_stones = 0
    black_stones_weight = 0.0
    white_stones_weight = 0.0

    for pos, color in live_stones.items():
        w = _w_at(weights, pos[0], pos[1], rows, cols)
        if color == "B":
            black_weighted += w
            black_stones_weight += w
            black_stones += 1
        else:
            white_weighted += w
            white_stones_weight += w
            white_stones += 1

    black_territory = 0
    white_territory = 0
    neutral = 0
    black_territory_weight = 0.0
    white_territory_weight = 0.0
    neutral_weight = 0.0

    # BFS 找空连通块（空点 = 棋盘内非棋子）。独占判定同 ban-selection。
    visited: set[tuple[int, int]] = set()
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            if (r, c) in live_stones or (r, c) in visited:
                continue

            block: list[tuple[int, int]] = []
            queue = [(r, c)]
            visited.add((r, c))
            touches_black = False
            touches_white = False

            while queue:
                cur = queue.pop(0)
                block.append(cur)
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cur[0] + dr, cur[1] + dc
                    if nr < 1 or nr > rows or nc < 1 or nc > cols:
                        continue
                    if (nr, nc) in live_stones:
                        if live_stones[(nr, nc)] == "B":
                            touches_black = True
                        else:
                            touches_white = True
                        continue
                    if (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

            block_w = sum(_w_at(weights, p[0], p[1], rows, cols) for p in block)

            if touches_black and not touches_white:
                black_weighted += block_w
                black_territory_weight += block_w
                black_territory += len(block)
            elif touches_white and not touches_black:
                white_weighted += block_w
                white_territory_weight += block_w
                white_territory += len(block)
            else:
                neutral += len(block)
                neutral_weight += block_w

    # 贴目与胜负（对齐改造版 KataGo final_score：difference-komi，1 位小数）
    final_white_minus_black = white_weighted - black_weighted + komi
    if final_white_minus_black > 0:
        winner = "W"
        result = f"W+{final_white_minus_black:.1f}"
    elif final_white_minus_black < 0:
        winner = "B"
        result = f"B+{-final_white_minus_black:.1f}"
    else:
        winner = ""
        result = "0"

    return {
        "black_weighted": black_weighted,
        "white_weighted": white_weighted,
        "neutral_weight": neutral_weight,
        "komi": komi,
        "final_white_minus_black_score": final_white_minus_black,
        "result": result,
        "winner": winner,
        "detail": {
            "black_stones": black_stones,
            "white_stones": white_stones,
            "black_territory": black_territory,
            "white_territory": white_territory,
            "neutral": neutral,
            "black_stones_weight": black_stones_weight,
            "white_stones_weight": white_stones_weight,
            "black_territory_weight": black_territory_weight,
            "white_territory_weight": white_territory_weight,
            "neutral_weight": neutral_weight,
            "dead": len(dead_stones),
            "sum_weights": _sum_weights(weights, rows, cols),
        },
    }


if __name__ == "__main__":
    # ── 自测块（不依赖 pytest，便于快速 sanity check）──
    ok = True

    def check(name, cond):
        global ok
        print(f"  {'OK' if cond else 'FAIL'}  {name}")
        if not cond:
            ok = False

    print("自测 1: W=1 等价标准 area scoring（5×5 黑墙 col3 / 白墙 col5）")
    s1 = {}
    for r in range(1, 6):
        s1[(r, 3)] = "B"
        s1[(r, 5)] = "W"
    w1 = [[1.0] * 5 for _ in range(5)]
    res = score_game(s1, w1, komi=7.5, rows=5, cols=5)
    check("black_weighted == 15 (5子+10独占空)", res["black_weighted"] == 15.0)
    check("white_weighted == 5 (5子无独占空)", res["white_weighted"] == 5.0)
    check("neutral == 5 (col4)", res["detail"]["neutral"] == 5)
    check("result == B+2.5 (5-15+7.5=-2.5)", res["result"] == "B+2.5")
    check("winner == B", res["winner"] == "B")

    print("自测 2: 加权累加（同局面，权重全 2.0 → 分数×2）")
    w2 = [[2.0] * 5 for _ in range(5)]
    res2 = score_game(s1, w2, komi=7.5, rows=5, cols=5)
    check("black_weighted == 30 (×2)", res2["black_weighted"] == 30.0)
    check("white_weighted == 10 (×2)", res2["white_weighted"] == 10.0)
    check("neutral_weight == 10 (×2)", res2["neutral_weight"] == 10.0)
    check("result == B+12.5 (10-30+7.5=-12.5)", res2["result"] == "B+12.5")

    print("自测 3: 空盘（全空→中性，仅 komi）")
    res3 = score_game({}, [[1.0] * N for _ in range(N)], komi=7.5)
    check("black_weighted == 0", res3["black_weighted"] == 0.0)
    check("white_weighted == 0", res3["white_weighted"] == 0.0)
    check("neutral_weight == 361", res3["neutral_weight"] == 361.0)
    check("result == W+7.5", res3["result"] == "W+7.5")
    check("winner == W", res3["winner"] == "W")

    print("自测 4: 死子（白死子被黑围，标记后变黑独占空）")
    s4 = dict(s1)
    s4[(1, 1)] = "W"  # 被黑墙围住，死子
    res_no = score_game(s4, w1, komi=7.5, rows=5, cols=5)
    check("未标记死子: black_weighted == 5 (左区域变中性)", res_no["black_weighted"] == 5.0)
    res_dead = score_game(s4, w1, komi=7.5, dead_stones={(1, 1)}, rows=5, cols=5)
    check("标记死子: black_weighted == 15 (恢复)", res_dead["black_weighted"] == 15.0)
    check("标记死子: white_stones == 5 (6−1死子)", res_dead["detail"]["white_stones"] == 5)
    check("标记死子: dead == 1", res_dead["detail"]["dead"] == 1)
    check("标记死子: result == B+2.5", res_dead["result"] == "B+2.5")

    print("自测 5: 真实权重表加载（ΣW≈421.59）")
    import os
    wt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weight_table_final.txt")
    if os.path.exists(wt_path):
        wt = load_weights(wt_path)
        check("load_weights 返回 19×19", len(wt) == 19 and len(wt[0]) == 19)
        res5 = score_game({}, wt, komi=7.5)
        check("空盘 neutral_weight ≈ ΣW ≈ 421.59",
              abs(res5["neutral_weight"] - 421.587) < 0.01)
        check("空盘仍 W+7.5（双方 0 分）", res5["result"] == "W+7.5")
        # 单子居中：所有空→黑独占，black_weighted == ΣW
        res6 = score_game({(10, 10): "B"}, wt, komi=7.5)
        check("单子居中 black_weighted ≈ ΣW", abs(res6["black_weighted"] - res5["neutral_weight"]) < 1e-9)
        check("单子居中 winner == B", res6["winner"] == "B")
    else:
        print("  [skip] weight_table_final.txt 不存在")

    print()
    print("全部通过" if ok else "有失败！")
    raise SystemExit(0 if ok else 1)
