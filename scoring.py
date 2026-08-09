# -*- coding: utf-8 -*-
"""
scoring.py — 20路Ban选围棋数子（中国规则 area scoring + 贴目）

移植自 website/js/ban-engine.js scoreGame（1:1 翻译，用 dict/set 代替 JS Map/Set）。
禁点视为棋盘外：BFS 跳过，不产气不占地。
贴目公式（新规则.md §4）：有效点=rows*cols−禁点数，基准=有效点/2，
  黑胜需 > 基准+4.25，白胜需 > 基准−4.25。
"""

from __future__ import annotations


def score_game(
    stones: dict[tuple[int, int], str],   # (row,col) 1-based -> "B"/"W"
    banned: set[tuple[int, int]],          # 禁点 1-based
    rows: int,
    cols: int,
    komi: float = 4.25,
    dead_stones: set[tuple[int, int]] | None = None,  # 死子 1-based，默认空
) -> dict:
    """中国规则 area scoring + 贴子。返回:
    {
        "black_area": int, "white_area": int, "neutral": int,
        "valid_points": int, "half": float,
        "black_win_threshold": float, "white_win_threshold": float,
        "result": str, "winner": str,
        "detail": {"black_stones": int, "white_stones": int,
                   "black_territory": int, "white_territory": int, "dead": int}
    }
    """
    if dead_stones is None:
        dead_stones = set()

    # 死子从棋子副本移除（不计入任何一方，其位置变为空点参与地域 BFS）
    live_stones = {k: v for k, v in stones.items() if k not in dead_stones}

    black_area = 0
    white_area = 0
    black_stones = 0
    white_stones = 0

    for color in live_stones.values():
        if color == "B":
            black_area += 1
            black_stones += 1
        else:
            white_area += 1
            white_stones += 1

    black_territory = 0
    white_territory = 0
    neutral = 0

    # BFS 找空连通块（空点 = 棋盘内非禁点、非棋子）
    visited: set[tuple[int, int]] = set()
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            if (r, c) in live_stones or (r, c) in banned or (r, c) in visited:
                continue

            block_size = 0
            queue = [(r, c)]
            visited.add((r, c))
            touches_black = False
            touches_white = False

            while queue:
                cur = queue.pop(0)
                block_size += 1
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cur[0] + dr, cur[1] + dc
                    if nr < 1 or nr > rows or nc < 1 or nc > cols:
                        continue
                    if (nr, nc) in banned:
                        continue  # 禁点 = 棋盘外，不参与
                    if (nr, nc) in live_stones:
                        if live_stones[(nr, nc)] == "B":
                            touches_black = True
                        else:
                            touches_white = True
                        continue
                    if (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

            # 独占判定：只邻黑→黑独占；只邻白→白独占；邻黑白或都不邻→中性
            if touches_black and not touches_white:
                black_area += block_size
                black_territory += block_size
            elif touches_white and not touches_black:
                white_area += block_size
                white_territory += block_size
            else:
                neutral += block_size

    # 胜负判定（新规则.md §4）
    valid_points = rows * cols - len(banned)
    half = valid_points / 2
    black_win_threshold = half + komi   # 黑需 > 199.25（20路）
    white_win_threshold = half - komi   # 白需 > 190.75（20路）

    if black_area > black_win_threshold:
        winner = "B"
        result = f"B+{black_area - black_win_threshold:.2f}"
    elif white_area > white_win_threshold:
        winner = "W"
        result = f"W+{white_area - white_win_threshold:.2f}"
    else:
        winner = ""
        result = "Draw"

    return {
        "black_area": black_area,
        "white_area": white_area,
        "neutral": neutral,
        "valid_points": valid_points,
        "half": half,
        "black_win_threshold": black_win_threshold,
        "white_win_threshold": white_win_threshold,
        "result": result,
        "winner": winner,
        "detail": {
            "black_stones": black_stones,
            "white_stones": white_stones,
            "black_territory": black_territory,
            "white_territory": white_territory,
            "dead": len(dead_stones),
        },
    }


if __name__ == "__main__":
    # ── 自测块 ──
    ok = True

    def check(name, cond):
        global ok
        print(f"  {'OK' if cond else 'FAIL'}  {name}")
        if not cond:
            ok = False

    print("测试 1: 无死子简单终局（黑围一角，黑独占空正确）")
    # 5×5：黑竖墙 col3，白竖墙 col5；左 10 格黑独占空，col4 中性
    s1 = {}
    for r in range(1, 6):
        s1[(r, 3)] = "B"
        s1[(r, 5)] = "W"
    res = score_game(s1, set(), 5, 5)
    check("black_area == 15 (5子+10独占空)", res["black_area"] == 15)
    check("black_territory == 10", res["detail"]["black_territory"] == 10)
    check("white_area == 5 (5子无独占空)", res["white_area"] == 5)
    check("neutral == 5 (col4)", res["neutral"] == 5)
    check("valid_points == 25", res["valid_points"] == 25)

    print("测试 2: 有死子（白死子被黑围，标记后变黑独占空）")
    # 在测试1基础上加白子 (1,1)（被黑墙围住，死子）
    s2 = dict(s1)
    s2[(1, 1)] = "W"
    # 未标记死子：(1,2) 邻 (1,1)=W → 左区域邻黑白 → 中性，黑区缩小
    res_no_dead = score_game(s2, set(), 5, 5)
    check("未标记死子: black_area == 5 (左区域变中性)", res_no_dead["black_area"] == 5)
    check("未标记死子: neutral == 14 (左9+原5)", res_no_dead["neutral"] == 14)
    # 标记死子：(1,1) 移除 → 左区域 10 格只邻黑 → 黑独占空
    res_dead = score_game(s2, set(), 5, 5, dead_stones={(1, 1)})
    check("标记死子: black_area == 15 (恢复)", res_dead["black_area"] == 15)
    check("标记死子: black_territory == 10", res_dead["detail"]["black_territory"] == 10)
    check("标记死子: dead == 1", res_dead["detail"]["dead"] == 1)
    check("标记死子: white_stones == 5 (6白子−1死子)", res_dead["detail"]["white_stones"] == 5)

    print("测试 3: 贴目 4.25 使结果含 .25/.75")
    # 20×20，10 禁点，有效点 390，基准 195，黑需>199.25，白需>190.75
    banned20 = {(1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
                (1, 6), (1, 7), (1, 8), (1, 9), (1, 10)}
    # 黑 200 子 + 白 190 子 = 390（满盘无空）
    s_b200 = {}
    n = 0
    for r in range(1, 21):
        for c in range(1, 21):
            if (r, c) in banned20:
                continue
            s_b200[(r, c)] = "B" if n < 200 else "W"
            n += 1
    res_b = score_game(s_b200, banned20, 20, 20)
    check("black_area=200 → B+0.75", res_b["result"] == "B+0.75")
    check("winner == B", res_b["winner"] == "B")
    check("black_win_threshold == 199.25", res_b["black_win_threshold"] == 199.25)
    # 白 191 子 → W+0.25
    s_w191 = {}
    n = 0
    for r in range(1, 21):
        for c in range(1, 21):
            if (r, c) in banned20:
                continue
            s_w191[(r, c)] = "W" if n < 191 else "B"
            n += 1
    res_w = score_game(s_w191, banned20, 20, 20)
    check("white_area=191 → W+0.25", res_w["result"] == "W+0.25")
    check("winner == W", res_w["winner"] == "W")
    check("white_win_threshold == 190.75", res_w["white_win_threshold"] == 190.75)

    print("测试 4: 双活模拟（空块邻黑白→中性，不计任一方）")
    # 4×4：黑左列，白右列，中间 8 格邻黑白 → 中性
    s4 = {}
    for r in range(1, 5):
        s4[(r, 1)] = "B"
        s4[(r, 4)] = "W"
    res4 = score_game(s4, set(), 4, 4)
    check("neutral == 8 (中间两列)", res4["neutral"] == 8)
    check("black_territory == 0", res4["detail"]["black_territory"] == 0)
    check("white_territory == 0", res4["detail"]["white_territory"] == 0)
    check("black_area == 4 (仅子)", res4["black_area"] == 4)
    check("white_area == 4 (仅子)", res4["white_area"] == 4)

    print("测试 5: 禁点不计地域（banned 点不参与 BFS）")
    # 5×5：禁点 (3,3)，黑顶行，白底行，中间空区邻黑白→中性
    s5 = {}
    for c in range(1, 6):
        s5[(1, c)] = "B"
        s5[(5, c)] = "W"
    res5 = score_game(s5, {(3, 3)}, 5, 5)
    check("valid_points == 24 (25-1禁)", res5["valid_points"] == 24)
    check("neutral == 14 (中间14格，禁点不计)", res5["neutral"] == 14)
    check("black_area == 5", res5["black_area"] == 5)
    check("white_area == 5", res5["white_area"] == 5)
    check("总面积 == valid_points (5+5+14=24)",
          res5["black_area"] + res5["white_area"] + res5["neutral"] == 24)

    print()
    print("全部通过" if ok else "有失败！")
    raise SystemExit(0 if ok else 1)
