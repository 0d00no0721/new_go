# -*- coding: utf-8 -*-
"""
sgf_io.py — 加权点目围棋 SGF 导出/导入 + 坐标工具 + 复盘棋盘

坐标系约定（0-indexed，全模块统一）：
  内部 (r, c)：r=0 是棋盘顶部（GTP 行 19），c=0 是棋盘左侧（GTP 列 A）。
  权重表 row-major：索引 = r * N + c，与 (r, c) 一一对应。
  GTP 坐标：大写字母跳过 I（A-H, J-T），数字 = N - r（底部为 1）。
  SGF 坐标：小写字母不跳 I，col 在前 row 在后；col='a'+c，row='a'+(N-1-r)。

换算链：GTP ↔ (r,c) ↔ SGF
  GTP "D16" → gtp_to_rc → (r=3, c=3) → rc_to_sgf → "dd"
  SGF "dd"  → sgf_to_rc → (r=3, c=3) → rc_to_gtp → "D16"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

N = 19  # 棋盘边长（加权表为 19×19，本方向固定 19 路）

# GTP 列字母（跳过 I）：A-H(1-8), J-T(9-19)
COL_LETTERS = "ABCDEFGHJKLMNOPQRST"


# ── 坐标转换 ────────────────────────────────────────────────────────────────

def rc_to_gtp(r: int, c: int) -> str:
    """(r, c) 0-indexed → GTP 坐标，如 (3,3) → 'D16'。"""
    if not (0 <= r < N and 0 <= c < N):
        raise ValueError(f"坐标越界: ({r},{c})")
    return f"{COL_LETTERS[c]}{N - r}"


def gtp_to_rc(gtp: str) -> tuple[int, int]:
    """GTP 坐标 → (r, c) 0-indexed，如 'D16' → (3,3)。pass/resign 返回 (-1,-1)。"""
    s = gtp.strip().upper()
    if s in ("PASS", "RESIGN", ""):
        return (-1, -1)
    letter = s[0]
    num = int(s[1:])
    c = COL_LETTERS.index(letter)
    r = N - num
    if not (0 <= r < N and 0 <= c < N):
        raise ValueError(f"GTP 坐标越界: {gtp}")
    return (r, c)


def rc_to_sgf(r: int, c: int) -> str:
    """(r, c) 0-indexed → SGF 坐标（小写不跳 I，col 在前 row 在后）。"""
    return chr(ord("a") + c) + chr(ord("a") + (N - 1 - r))


def sgf_to_rc(s: str) -> tuple[int, int]:
    """SGF 坐标 → (r, c) 0-indexed。空串 → (-1,-1) 表示 pass。"""
    if not s or len(s) < 2:
        return (-1, -1)
    c = ord(s[0]) - ord("a")
    r = N - 1 - (ord(s[1]) - ord("a"))
    return (r, c)


def gtp_to_sgf(gtp: str) -> str:
    r, c = gtp_to_rc(gtp)
    if r < 0:
        return ""
    return rc_to_sgf(r, c)


def sgf_to_gtp(sgf: str) -> str:
    r, c = sgf_to_rc(sgf)
    if r < 0:
        return "pass"
    return rc_to_gtp(r, c)


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class SgfGame:
    """一局 SGF 棋谱的完整数据。"""
    boardsize: int = N
    komi: float = 7.5
    player_b: str = "人类"
    player_a: str = "AI"
    date: str = ""
    weights_file: str = ""          # 加权表文件名（元信息）
    moves: list[tuple[str, str]] = field(default_factory=list)  # (color "B"/"W", gtp_coord or "pass")
    result: str = ""                # "B+2.50" / "W+R" / ""


# ── 导出 ────────────────────────────────────────────────────────────────────

def export_sgf(game: SgfGame, path: str) -> None:
    """将 SgfGame 写入 .sgf 文件（含权重元信息）。"""
    props: list[str] = [
        "FF[4]",
        "GM[1]",
        f"SZ[{game.boardsize}]",
        "CA[UTF-8]",
        f"KM[{game.komi}]",
        "RU[chinese]",
        "AP[weighted-scoring]",
        f"PB[{game.player_b}]",
        f"PW[{game.player_a}]",
    ]
    if game.date:
        props.append(f"DT[{game.date}]")
    if game.result:
        props.append(f"RE[{game.result}]")
    if game.weights_file:
        # 用用户自定义属性记录权重表（SGF 允许小写键作扩展）
        props.append(f"WeightsFile[{os.path.basename(game.weights_file)}]")

    lines = [";" + "".join(props)]

    for color, coord in game.moves:
        if coord.lower() == "pass":
            lines.append(f";{color}[]")
        else:
            sgf = gtp_to_sgf(coord)
            lines.append(f";{color}[{sgf}]")

    content = "(" + "\n".join(lines) + "\n)"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── 导入 ────────────────────────────────────────────────────────────────────

def _parse_node_props(node: str) -> dict[str, list[str]]:
    """解析节点属性字符串 → {KEY: [val1, ...]}。处理转义与多值 KEY[v1][v2]。"""
    props: dict[str, list[str]] = {}
    i = 0
    n = len(node)
    while i < n:
        while i < n and node[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        key_start = i
        while i < n and "A" <= node[i] <= "Z":
            i += 1
        if i == key_start:
            i += 1
            continue
        key = node[key_start:i]
        values: list[str] = []
        while i < n and node[i] == "[":
            i += 1
            val_chars: list[str] = []
            while i < n:
                if node[i] == "\\" and i + 1 < n:
                    val_chars.append(node[i + 1])
                    i += 2
                elif node[i] == "]":
                    break
                else:
                    val_chars.append(node[i])
                    i += 1
            if i < n and node[i] == "]":
                i += 1
            values.append("".join(val_chars))
        if key and values:
            props.setdefault(key, []).extend(values)
    return props


def import_sgf(path: str) -> SgfGame:
    """读取 .sgf 文件 → SgfGame（支持线性棋谱，无分支）。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.strip()
    if content.startswith("("):
        content = content[1:]
    if content.endswith(")"):
        content = content[:-1]

    parts = content.split(";")
    nodes = [p.strip() for p in parts if p.strip()]
    if not nodes:
        raise ValueError("SGF 文件无节点")

    game = SgfGame()
    root = _parse_node_props(nodes[0])
    if "SZ" in root:
        game.boardsize = int(root["SZ"][0])
    if "KM" in root:
        game.komi = float(root["KM"][0])
    if "PB" in root:
        game.player_b = root["PB"][0]
    if "PW" in root:
        game.player_a = root["PW"][0]
    if "DT" in root:
        game.date = root["DT"][0]
    if "RE" in root:
        game.result = root["RE"][0]
    if "WeightsFile" in root:
        game.weights_file = root["WeightsFile"][0]

    for node_str in nodes[1:]:
        props = _parse_node_props(node_str)
        if "B" in props:
            color = "B"
            val = props["B"][0] if props["B"] else ""
        elif "W" in props:
            color = "W"
            val = props["W"][0] if props["W"] else ""
        else:
            continue
        if not val:
            game.moves.append((color, "pass"))
        else:
            game.moves.append((color, sgf_to_gtp(val)))

    return game


# ── 复盘棋盘（带提子） ──────────────────────────────────────────────────────

class ReplayBoard:
    """简易 19×19 围棋棋盘，支持落子 + 提子，用于复盘展示与 UI 数子。

    内部用 0-indexed (r, c) 键，r=0 顶部。
    """

    def __init__(self, size: int = N):
        self.size = size
        self.grid: dict[tuple[int, int], str] = {}

    def play(self, color: str, r: int, c: int) -> None:
        """落子并处理提子。color: 'B' or 'W'。越界/已有点则忽略。"""
        if not (0 <= r < self.size and 0 <= c < self.size):
            return
        if (r, c) in self.grid:
            return
        self.grid[(r, c)] = color
        opp = "W" if color == "B" else "B"
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if (nr, nc) in self.grid and self.grid[(nr, nc)] == opp:
                group = self._find_group(nr, nc)
                if self._count_liberties(group) == 0:
                    for pt in group:
                        del self.grid[pt]

    def _find_group(self, r: int, c: int) -> set[tuple[int, int]]:
        color = self.grid[(r, c)]
        seen: set[tuple[int, int]] = set()
        stack = [(r, c)]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = cur[0] + dr, cur[1] + dc
                if (nr, nc) in self.grid and self.grid[(nr, nc)] == color:
                    stack.append((nr, nc))
        return seen

    def _count_liberties(self, group: set[tuple[int, int]]) -> int:
        libs: set[tuple[int, int]] = set()
        for r, c in group:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    if (nr, nc) not in self.grid:
                        libs.add((nr, nc))
        return len(libs)

    @property
    def stones(self) -> dict[tuple[int, int], str]:
        return dict(self.grid)
