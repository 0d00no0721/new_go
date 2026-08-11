#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_e2e.py — CLI 端到端测试（加权点目围棋，实跑）。

覆盖 DoD：
  - AI vs AI 全自动对局（--max-moves 10 + --visits 10）→ 权重加载 / komi 生效 /
    终局加权数子 / 盘面加权统计 / SGF 导出
  - 权重表加载路径正确（weight_table_final.txt）且摘要合理（ΣW≈421.59）
  - komi 7.5 经 ignoreGTPAndForceKomi 生效（get_komi 确认）

方式：subprocess 起 `python cli_player.py`，捕获 stdout（PYTHONIOENCODING=utf-8）断言标记。
引擎起停慢 → session 级 fixture 复用一次 aivai 对局。

运行：
  $env:PYTHONIOENCODING='utf-8'; python -m pytest test_e2e.py -q --slow
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "cli_player.py")
OVERRIDE_CFG = os.path.join(HERE, "gtp_override.cfg")
WT_NAME = "weight_table_final.txt"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@pytest.fixture(scope="session")
def aivai_run(tmp_path_factory):
    """跑一次 aivai（--max-moves 10 + --visits 10），返回 CompletedProcess + sgf 路径。

    与 ban-selection/test_e2e.py 的 aivai_run 同模式；本方向无 --boardsize（固定 19 路）。
    """
    tmp = tmp_path_factory.mktemp("weighted_e2e")
    sgf_path = tmp / "e1_game.sgf"
    proc = subprocess.run(
        [sys.executable, CLI,
         "--mode", "aivai",
         "--max-moves", "10",
         "--visits", "10",
         "--extra-config", OVERRIDE_CFG,
         "--sgf-out", str(sgf_path)],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", env=ENV,
    )
    return proc, str(sgf_path)


@pytest.mark.slow
def test_e1_ai_vs_ai(aivai_run):
    """E1: AI vs AI 全自动对局 → 权重加载、komi 生效、终局加权分、SGF 导出。"""
    proc, sgf_path = aivai_run
    out = proc.stdout
    assert proc.returncode == 0, f"cli_player 非零退出: {proc.returncode}\nstderr: {proc.stderr[-600:]}"

    # 权重表加载正确（ASCII 临时路径 + 原文件路径都可见）
    assert "已加载" in out
    assert WT_NAME in out, f"应加载 weight_table_final.txt\n{out[-800:]}"
    assert "ΣW = 421.59" in out, f"权重摘要 ΣW 应 ≈421.59\n{out[-800:]}"

    # komi 7.5 生效（经 ignoreGTPAndForceKomi）
    assert "[确认] komi = 7.5" in out, f"komi 应为 7.5\n{out[-800:]}"

    # 终局 + 加权分标记
    assert "=== 终局加权数子 ===" in out, f"应有终局标记\n{out[-800:]}"
    assert "引擎 final_score（加权）" in out, f"应有加权 final_score\n{out[-800:]}"
    assert "[盘面加权]" in out, f"应有盘面加权统计\n{out[-800:]}"
    assert "[达到最大手数 10" in out, f"应报告达到最大手数\n{out[-800:]}"

    # 正常关闭
    assert "[完成]" in out, f"应正常关闭引擎\n{out[-800:]}"

    # SGF 导出
    assert os.path.isfile(sgf_path) and os.path.getsize(sgf_path) > 0, "SGF 应存在且非空"


@pytest.mark.slow
def test_e2_query_weights():
    """E2: --query-weights 只加载权重表并打印摘要，验证路径与统计（不起对局）。"""
    proc = subprocess.run(
        [sys.executable, CLI, "--query-weights", "--extra-config", OVERRIDE_CFG],
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", env=ENV,
    )
    out = proc.stdout
    assert proc.returncode == 0, f"query-weights 非零退出: {proc.returncode}\nstderr: {proc.stderr[-500:]}"
    # query_weight 模式只打印权重摘要（无"已加载"行），断言摘要关键信息
    assert "ΣW = 421.59" in out, f"权重摘要 ΣW 应 ≈421.59\n{out[-500:]}"
    assert "范围 [" in out, f"应打印权重范围\n{out[-500:]}"
    # 权重分布合理性：关键点列表含天元/星位
    assert "天元" in out, f"应打印关键点权重\n{out[-500:]}"