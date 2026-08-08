"""
sgf_io.py — SGF 导出/导入（20路Ban选围棋）

坐标系约定（易错，务必注意）：
  SGF 坐标：小写字母，不跳 I，a=1..t=20。格式 col+row（如 "dg" = col4,row7）
  GTP 坐标：大写字母，跳过 I，A=1..H=8,J=9..U=20。格式 letter(col)+row（如 "D7"）
  ban_controller 内部：1-based (row, col)，row/col 均 1-20

ban 点用 SGF 标准 AE 属性（Add Empty）记录于根节点。导入只读 AE。
  可选叠加 CR[] 仅供编辑器可视化，导入不读 CR。

换算链：GTP ↔ (row,col) ↔ SGF
  GTP "D7" → gtp_to_point → (row=7, col=4) → point_to_sgf → "dg"
  SGF "dg" → sgf_to_point → (row=7, col=4) → point_to_gtp → "D7"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ban_controller import gtp_to_point, point_to_gtp


# ── 坐标转换 ────────────────────────────────────────────────────────────────

def point_to_sgf(row: int, col: int) -> str:
    """(row, col) 1-based → SGF 坐标。小写字母不跳 I，col 在前 row 在后。"""
    return chr(ord("a") + col - 1) + chr(ord("a") + row - 1)


def sgf_to_point(s: str) -> tuple[int, int]:
    """SGF 坐标 → (row, col)。空串或长度 <2 → (0, 0) 表示 pass。"""
    if not s or len(s) < 2:
        return (0, 0)
    col = ord(s[0]) - ord("a") + 1
    row = ord(s[1]) - ord("a") + 1
    return (row, col)


def gtp_to_sgf(label: str) -> str:
    """GTP 坐标 'D7' → SGF 'dg'。"""
    row, col = gtp_to_point(label)
    return point_to_sgf(row, col)


def sgf_to_gtp(sgf_coord: str) -> str:
    """SGF 'dg' → GTP 'D7'。"""
    row, col = sgf_to_point(sgf_coord)
    return point_to_gtp(row, col)


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class SgfGame:
    """一局 SGF 棋谱的完整数据。"""
    boardsize: int = 20
    komi: float = 4.25
    player_b: str = "选手B"
    player_a: str = "选手A"
    date: str = ""
    bans: list[tuple[int, int]] = field(default_factory=list)   # (row, col)
    moves: list[tuple[str, str]] = field(default_factory=list)  # (color "B"/"W", gtp_coord or "pass")
    result: str = ""  # "B+R" / "W+R" / "B+4.25" / ""


# ── 导出 ────────────────────────────────────────────────────────────────────

def export_sgf(game: SgfGame, path: str) -> None:
    """将 SgfGame 写入 .sgf 文件。"""
    props: list[str] = [
        "FF[4]",
        "GM[1]",
        f"SZ[{game.boardsize}]",
        "CA[UTF-8]",
        f"KM[{game.komi}]",
        "RU[chinese]",
        "AP[new_go]",
        f"PB[{game.player_b}]",
        f"PW[{game.player_a}]",
    ]
    if game.date:
        props.append(f"DT[{game.date}]")
    if game.result:
        props.append(f"RE[{game.result}]")
    if game.bans:
        ae = "AE" + "".join(
            f"[{point_to_sgf(r, c)}]" for r, c in game.bans
        )
        props.append(ae)

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
    """解析节点属性字符串 → {KEY: [val1, val2, ...]}。

    处理转义 \\] 和多值属性 KEY[v1][v2]。
    """
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
    """读取 .sgf 文件 → SgfGame。支持线性棋谱（无分支）。"""
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
    if "AE" in root:
        for s in root["AE"]:
            if len(s) >= 2:
                game.bans.append(sgf_to_point(s))

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
    """简易围棋棋盘，支持落子 + 提子，用于 SGF 复盘展示。

    禁点视为棋盘外（不产生气、不可落子）。
    """

    def __init__(self, size: int, bans: Optional[set[tuple[int, int]]] = None):
        self.size = size
        self.bans: set[tuple[int, int]] = bans or set()
        self.grid: dict[tuple[int, int], str] = {}

    def play(self, color: str, row: int, col: int) -> None:
        """落子并处理提子。color: 'B' or 'W'。"""
        if (row, col) in self.bans or (row, col) in self.grid:
            return
        if not (1 <= row <= self.size and 1 <= col <= self.size):
            return
        self.grid[(row, col)] = color
        opp = "W" if color == "B" else "B"
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if (nr, nc) in self.grid and self.grid[(nr, nc)] == opp:
                group = self._find_group(nr, nc)
                if self._count_liberties(group) == 0:
                    for pt in group:
                        del self.grid[pt]

    def _find_group(self, row: int, col: int) -> set[tuple[int, int]]:
        color = self.grid[(row, col)]
        seen: set[tuple[int, int]] = set()
        stack = [(row, col)]
        while stack:
            r, c = stack.pop()
            if (r, c) in seen:
                continue
            seen.add((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if (nr, nc) in self.grid and self.grid[(nr, nc)] == color:
                    stack.append((nr, nc))
        return seen

    def _count_liberties(self, group: set[tuple[int, int]]) -> int:
        libs: set[tuple[int, int]] = set()
        for r, c in group:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 1 <= nr <= self.size and 1 <= nc <= self.size:
                    if (nr, nc) not in self.grid and (nr, nc) not in self.bans:
                        libs.add((nr, nc))
        return len(libs)

    @property
    def stones(self) -> dict[tuple[int, int], str]:
        return dict(self.grid)
