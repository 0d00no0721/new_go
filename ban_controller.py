"""
Ban 阶段控制器 — 20路Ban选围棋

职责：
  1. Ban 序列推进（A→B→B→A→A→B→B→A→A→B，可配置）
  2. 合法性校验（区域 / 不重复 / 全局连通性）
  3. 人类输入通道
  4. AI 自动选点（随机策略 + GTP 评估策略）
  5. 违例计数与判负
"""

from __future__ import annotations

import itertools
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

# ── 坐标工具 ────────────────────────────────────────────────────────────────

COL_LETTERS = "ABCDEFGHJKLMNOPQRSTU"

def col_to_letter(col: int) -> str:
    """1-based column → letter (skip I).  1→A, 8→H, 9→J, 20→U."""
    if col < 1 or col > 20:
        raise ValueError(f"列编号必须在 1-20 之间，收到 {col}")
    return COL_LETTERS[col - 1]

def letter_to_col(letter: str) -> int:
    """Letter → 1-based column."""
    return COL_LETTERS.index(letter.upper()) + 1

def point_to_gtp(row: int, col: int) -> str:
    """(row, col) → GTP coordinate like 'D7'."""
    return f"{col_to_letter(col)}{row}"

def gtp_to_point(s: str) -> tuple[int, int]:
    """GTP coordinate 'D7' → (row=7, col=4)."""
    s = s.strip().upper()
    letter = s[0]
    row = int(s[1:])
    return row, letter_to_col(letter)

# ── 数据定义 ────────────────────────────────────────────────────────────────

@dataclass
class BanConfig:
    """Ban 阶段全部可配置参数。"""
    board_size: int = 20
    ban_count: int = 10
    sequence: str = "ABBAABBABA"
    region_row_min: int = 4
    region_row_max: int = 17
    region_col_min: int = 4
    region_col_max: int = 17
    max_violations: int = 3
    ai_candidate_sample: int = 20

    def validate(self) -> None:
        bs = self.board_size
        if self.region_row_min < 1 or self.region_row_max > bs:
            raise ValueError(f"region rows must be within [1, {bs}]")
        if self.region_col_min < 1 or self.region_col_max > bs:
            raise ValueError(f"region cols must be within [1, {bs}]")
        if len(self.sequence) != self.ban_count:
            raise ValueError(f"sequence length {len(self.sequence)} != ban_count {self.ban_count}")


@dataclass
class BanState:
    """每次 ban 事件记录。"""
    index: int
    player: str          # 'A' or 'B'
    row: int
    col: int
    label: str           # GTP label e.g. 'D7'
    source: str = "human"  # "human" | "ai"


@dataclass
class BanResult:
    """单次 ban 校验结果。"""
    valid: bool
    reason: str = ""


@dataclass
class BanPhaseResult:
    """Ban 阶段结束时的完整结果。"""
    banned_points: set[tuple[int, int]]
    history: list[BanState]
    concluded_by: str   # "complete" | "violation_a" | "violation_b"


# ── 校验器 ──────────────────────────────────────────────────────────────────

def check_region(row: int, col: int, config: BanConfig) -> BanResult:
    """ban 点必须在中间可配置区域内。"""
    if not (config.region_row_min <= row <= config.region_row_max and
            config.region_col_min <= col <= config.region_col_max):
        return BanResult(False, f"点 {point_to_gtp(row,col)} 不在 ban 区域内 "
                         f"(行{config.region_row_min}-{config.region_row_max}, "
                         f"列{config.region_col_min}-{config.region_col_max})")
    return BanResult(True)


def check_no_duplicate(row: int, col: int, banned: set[tuple[int, int]]) -> BanResult:
    """不能选择已标记为禁点的位置。"""
    if (row, col) in banned:
        return BanResult(False, f"点 {point_to_gtp(row,col)} 已被标记为禁点")
    return BanResult(True)


def check_connectivity(
    board_size: int,
    banned: set[tuple[int, int]],
    new_ban: tuple[int, int],
) -> BanResult:
    """BFS: ban 之后所有可落子点必须保持全局四向连通。

    可落子点 = 整个棋盘去掉所有禁点。边界（行列 <1 或 >board_size）是自然障碍。
    允许局部小型空洞。只要有一个种子能连到所有可落子点即可。
    """
    bs = board_size
    all_banned = banned | {new_ban}

    def in_bounds(r: int, c: int) -> bool:
        return 1 <= r <= bs and 1 <= c <= bs and (r, c) not in all_banned

    all_playable: list[tuple[int, int]] = [
        (r, c)
        for r in range(1, bs + 1)
        for c in range(1, bs + 1)
        if (r, c) not in all_banned
    ]

    if not all_playable:
        return BanResult(False, "没有可落子点（所有点均为禁点）")

    start = all_playable[0]
    visited: set[tuple[int, int]] = set()
    q: deque[tuple[int, int]] = deque([start])
    visited.add(start)

    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if in_bounds(nr, nc) and (nr, nc) not in visited:
                visited.add((nr, nc))
                q.append((nr, nc))

    if len(visited) != len(all_playable):
        unreachable = set(all_playable) - visited
        example = min(unreachable)
        return BanResult(
            False,
            f"Ban {point_to_gtp(*new_ban)} 导致棋盘被分割："
            f"可落子 {len(all_playable)} 点，BFS 仅到达 {len(visited)} 点。"
            f"不可达点示例: {point_to_gtp(*example)}"
        )
    return BanResult(True)


# ── Ban 控制器 ──────────────────────────────────────────────────────────────

class BanController:
    """Ban 阶段的完整控制器。"""

    def __init__(self, config: Optional[BanConfig] = None):
        self.config = config or BanConfig()
        self.config.validate()

        self.banned: set[tuple[int, int]] = set()
        self.history: list[BanState] = []
        self.step: int = 0
        self.violations: dict[str, int] = {"A": 0, "B": 0}
        self.concluded: bool = False
        self.conclusion_reason: str = ""

        self._gtp_engine: Optional[Callable] = None

    # ── 只读属性 ──

    @property
    def current_player(self) -> str:
        return self.config.sequence[self.step]

    @property
    def remaining(self) -> int:
        return self.config.ban_count - self.step

    @property
    def is_finished(self) -> bool:
        return self.concluded

    # ── 核心: 提交一次 ban ──

    def submit(self, row: int, col: int, source: str = "human") -> BanResult:
        """提交一个 ban 点，经所有校验后生效或退回。"""
        if self.concluded:
            return BanResult(False, "Ban 阶段已结束")

        for check in self._all_checks(row, col):
            if not check.valid:
                player = self.current_player
                self.violations[player] += 1
                if self.violations[player] >= self.config.max_violations:
                    self.concluded = True
                    self.conclusion_reason = f"violation_{player.lower()}"
                return check

        self._apply(row, col, source)
        return BanResult(True)

    def _all_checks(self, row: int, col: int) -> Iterable[BanResult]:
        yield check_region(row, col, self.config)
        yield check_no_duplicate(row, col, self.banned)
        yield check_connectivity(self.config.board_size, self.banned, (row, col))

    def _apply(self, row: int, col: int, source: str) -> None:
        player = self.current_player
        point = (row, col)
        self.banned.add(point)
        st = BanState(
            index=self.step,
            player=player,
            row=row,
            col=col,
            label=point_to_gtp(row, col),
            source=source,
        )
        self.history.append(st)
        self.step += 1

        if self.step >= self.config.ban_count:
            self.concluded = True
            self.conclusion_reason = "complete"

    # ── 人类输入通道 ──

    def submit_label(self, label: str) -> BanResult:
        """接受 GTP 坐标字符串如 'D7'，解析后提交。"""
        try:
            row, col = gtp_to_point(label)
        except (ValueError, IndexError):
            return BanResult(False, f"无效坐标: {label}")
        if not (1 <= row <= self.config.board_size and 1 <= col <= self.config.board_size):
            return BanResult(False, f"坐标越界: {label}")
        return self.submit(row, col, source="human")

    # ── AI 自动选点 ──

    def _legal_candidates(self) -> list[tuple[int, int]]:
        """收集当前所有合法候选（区域内 + 不重复 + 不割裂）。"""
        candidates = []
        cfg = self.config
        for r in range(cfg.region_row_min, cfg.region_row_max + 1):
            for c in range(cfg.region_col_min, cfg.region_col_max + 1):
                if (r, c) in self.banned:
                    continue
                if not check_connectivity(cfg.board_size, self.banned, (r, c)).valid:
                    continue
                candidates.append((r, c))
        return candidates

    def ai_pick_random(self) -> tuple[int, int]:
        """保底策略：从合法候选集中随机选一个。"""
        candidates = self._legal_candidates()
        if not candidates:
            raise RuntimeError("没有合法候选禁点")
        return random.choice(candidates)

    def set_gtp_engine(self, engine: Callable) -> None:
        """注入 GTP 引擎接口。engine 应为可调用对象，接受命令字符串返回响应字符串。"""
        self._gtp_engine = engine

    def _gtp_command(self, cmd: str) -> str:
        if self._gtp_engine is None:
            raise RuntimeError("GTP 引擎未绑定")
        return self._gtp_engine(cmd).strip()

    def _set_bans_on_engine(self, ban_set: set[tuple[int, int]]) -> None:
        labels = [point_to_gtp(r, c) for r, c in ban_set]
        cmd = f"kata-set-bans {' '.join(labels)}" if labels else "kata-clear-bans"
        resp = self._gtp_command(cmd)
        if not resp.startswith("="):
            raise RuntimeError(f"kata-set-bans 失败: {resp}")

    def _analyze_with_bans(self, ban_set: set[tuple[int, int]],
                           player: str) -> Optional[float]:
        """用给定禁点集合调用 kata-analyze，返回当前 ban 选手视角的胜率。

        kata-analyze 返回 rootInfo，从中解析 scoreLead / winrate。
        这里取 black 的 winrate，再根据当前选手调整。
        如果 player=='B'，要最大化 black winrate；player=='A'，要最小化。
        """
        if self._gtp_engine is None:
            raise RuntimeError("GTP 引擎未绑定")

        self._set_bans_on_engine(ban_set)
        resp = self._gtp_command("kata-analyze interval 1")
        for line in resp.splitlines():
            line = line.strip()
            if line.startswith("info ") and "winrate" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "winrate" and i + 1 < len(parts):
                        try:
                            return float(parts[i + 1])
                        except ValueError:
                            pass
        return None

    def ai_pick_gtp(
        self,
        top_n: int = 1,
        prefer: str = "own",
    ) -> Optional[tuple[int, int]]:
        """GTP 评估策略：对候选池抽样 → 逐个 kata-set-bans → kata-analyze →
        选对己方胜率最高 / 对敌方胜率最低的点。

        prefer: 'own' 取己方胜率最高，'opponent' 取敌方胜率最低。
        top_n: 返回最优前 N 个（默认 1 个）。
        """
        if self._gtp_engine is None:
            raise RuntimeError("GTP 引擎未绑定")

        full_candidates = self._legal_candidates()
        if not full_candidates:
            return None

        sample_size = min(self.config.ai_candidate_sample, len(full_candidates))
        candidates = random.sample(full_candidates, sample_size)

        current = self.current_player
        results: list[tuple[float, tuple[int, int]]] = []

        for pt in candidates:
            trial_banned = self.banned | {pt}
            wr = self._analyze_with_bans(trial_banned, current)
            if wr is None:
                continue
            if current == "A":
                wr = 1.0 - wr  # A 取 white 胜率
            if prefer == "opponent":
                wr = 1.0 - wr  # 反转：取对手视角
            results.append((wr, pt))

        if not results:
            return None

        results.sort(key=lambda x: x[0], reverse=True)
        return results[0][1]

    def ai_pick(self, strategy: str = "random") -> tuple[int, int]:
        """统一的 AI 选点入口。

        strategy:
          - 'random': 纯随机保底
          - 'gtp': GTP 评估策略，需先 set_gtp_engine
          - 'auto': 有 GTP 引擎则用 gtp，否则 fallback 到 random
        """
        if strategy == "random" or (strategy == "auto" and self._gtp_engine is None):
            return self.ai_pick_random()
        elif strategy in ("gtp", "auto"):
            got = self.ai_pick_gtp()
            if got is not None:
                return got
            return self.ai_pick_random()
        else:
            raise ValueError(f"未知 AI 策略: {strategy}")

    def submit_ai(self, strategy: str = "auto") -> BanResult:
        """AI 自动选点并提交一步。"""
        if self.concluded:
            return BanResult(False, "Ban 阶段已结束")
        row, col = self.ai_pick(strategy)
        return self.submit(row, col, source="ai")

    # ── 结果 ──

    def get_result(self) -> BanPhaseResult:
        return BanPhaseResult(
            banned_points=frozenset(self.banned),
            history=list(self.history),
            concluded_by=self.conclusion_reason,
        )

    def reset(self) -> None:
        self.banned.clear()
        self.history.clear()
        self.step = 0
        self.violations = {"A": 0, "B": 0}
        self.concluded = False
        self.conclusion_reason = ""