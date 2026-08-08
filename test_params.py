"""
test_params.py — QA 测试矩阵 E1-E5（参数化用例）

依赖：RULES ✅ + ENGINE ✅ + INFRA ✅
  E1 boardsize 19/20：GTP 引擎 fixture（共用主 fixture）
  E2 ban_count=6：纯 BanController
  E3 region 5-16：纯 BanController
  E4 komi=3.75：subprocess 直启 katago（不经 cli_player，因 cli_player 硬编码 4.25）
  E5 sequence ABABABABAB：纯 BanController
"""

from __future__ import annotations

import pytest

from ban_controller import BanConfig, BanController
from test_gtp_engine import GtpEngine, _BASE, CACHE_DIR, engine  # 复用引擎客户端 + fixture
import os


# ── E1 boardsize 19/20 ──────────────────────────────────────────────────────

def test_e1_boardsize_switch(engine):
    """E1: 切换 boardsize 19/20 → 两尺寸 genmove 均合法。

    共用主引擎 fixture（komi=4.25 override，但 E1 测尺寸切换不依赖 komi 值）。
    """
    # 20 路
    engine.send("boardsize 20")
    engine.send("clear_board")
    ok, _, status = engine.send("genmove B")
    assert ok, f"20路 genmove 应成功: {status!r}"
    # 19 路
    engine.send("boardsize 19")
    engine.send("clear_board")
    ok, _, status = engine.send("genmove B")
    assert ok, f"19路 genmove 应成功: {status!r}"


# ── E2 ban_count=6 ──────────────────────────────────────────────────────────

def test_e2_ban_count_6():
    """E2: BanConfig(ban_count=6) → 连续 6 个合法 ban 后 concluded，reason=complete。

    序列默认 ABBAABBABA 长度 10 != ban_count 6 → 需配匹配序列（6 位）。
    """
    cfg = BanConfig(ban_count=6, sequence="ABBAAB")
    bc = BanController(cfg)
    pts = [(10, 10), (10, 11), (10, 12), (10, 13), (10, 14), (10, 15)]
    for p in pts:
        r = bc.submit(*p)
        assert r.valid, f"{p} 应合法: {r.reason}"
    assert bc.step == 6
    assert bc.concluded
    assert bc.conclusion_reason == "complete"
    assert len(bc.banned) == 6


# ── E3 region 5-16 ──────────────────────────────────────────────────────────

def test_e3_custom_region():
    """E3: BanConfig(region 5-16) → submit(4,10) 被拒（行4<5）+ 违例计数。

    自定义区域行5-16/列5-16，点(4,10)行4<5越界。
    """
    cfg = BanConfig(
        region_row_min=5, region_row_max=16,
        region_col_min=5, region_col_max=16,
    )
    bc = BanController(cfg)
    r = bc.submit(4, 10)
    assert not r.valid, "(4,10) 应在区域外被拒"
    assert "不在 ban 区域内" in r.reason
    assert bc.violations["A"] == 1
    # 区域内点合法
    r = bc.submit(5, 10)
    assert r.valid, "(5,10) 应在区域内合法"


# ── E4 komi=3.75 ────────────────────────────────────────────────────────────

def test_e4_komi_375():
    """E4: 直启 katago（-override-config ignoreGTPAndForceKomi=3.75）→ get_komi==3.75。

    不经 cli_player（其硬编码 4.25）；用 GtpEngine 直启，override 改 3.75。
    final_score 不报错（3.75 是半整数 + 0.25，但 override 绕过半整数校验）。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    args = _BASE + ["-override-config", "ignoreGTPAndForceKomi=3.75"]
    eng = GtpEngine(args)
    try:
        eng.send("boardsize 20")
        ok, text, _ = eng.send("get_komi")
        assert ok and "3.75" in text, f"komi 应为 3.75，实际: {text!r}"
        # final_score 不报错
        eng.send("clear_board")
        ok, text, _ = eng.send("final_score")
        assert ok, f"final_score 在 komi 3.75 下应成功: {text!r}"
    finally:
        eng.quit()


# ── E5 sequence ABABABABAB ──────────────────────────────────────────────────

def test_e5_custom_sequence():
    """E5: BanConfig(sequence="ABABABABAB") → 前 5 步 current_player 依次 A B A B A。

    默认序列 ABBAABBABA，自定义 ABAB 交替。
    """
    cfg = BanConfig(ban_count=10, sequence="ABABABABAB")
    bc = BanController(cfg)
    expected = list("ABABABABAB")[:5]  # 前 5 步
    pts = [(10 + i, 10) for i in range(5)]  # 5 个合法点
    for i, exp in enumerate(expected):
        assert bc.current_player == exp, f"第{i}步应为 {exp}，实际 {bc.current_player}"
        assert bc.submit(*pts[i]).valid
    assert bc.step == 5
    assert not bc.concluded  # 5 < 10 未结束
