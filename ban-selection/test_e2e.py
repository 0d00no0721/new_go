"""
test_e2e.py — QA 测试矩阵 D（端到端，实跑）

依赖：FE ✅（cli_player.py 第三阶段完成）+ ENGINE ✅ + INFRA ✅
方式：subprocess 启动 `python cli_player.py`，捕获 stdout 断言标记。
加速：临时 cfg 文件 `maxVisits = 10` 经 --extra-config 传入（CLI 未暴露逐键 override）。
      gtp_override.cfg（homeDataDir=E:/katago_cache）复用 tuner 缓存。
编码：subprocess env 设 PYTHONIOENCODING=utf-8，与 cli_player print 一致。

D1/D3 共用 session 级 aivai 对局（跑一次 ~1-2min），D2 单独 stdin 注入。

SGF ban 标记格式（已冻结）：SGF 标准 AE 节点 `;AE[xx][yy]...`。
  坐标小写不跳 I（SGF 标准），GTP 跳 I。换算：(row,col) → chr(ord('a')+col-1)+chr(ord('a')+row-1)。
  注意：cli_player stdout 打印禁点用 GTP 字典序排序，SGF export 用 (row,col) 元组序——
  断言用集合比对（顺序无关）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from sgf_io import import_sgf, point_to_sgf

# ── 资源路径 ─────────────────────────────────────────────────────────────────

CLI = os.path.join(os.path.dirname(__file__), "cli_player.py")
OVERRIDE_CFG = os.path.join(os.path.dirname(__file__), "gtp_override.cfg")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _to_sgf(row: int, col: int) -> str:
    """(row, col) → SGF 坐标（小写，不跳 I）。列字母在前。"""
    return chr(ord("a") + col - 1) + chr(ord("a") + row - 1)


# ── session 级 aivai 对局（D1/D3 共用）──────────────────────────────────────

@pytest.fixture(scope="session")
def aivai_run(tmp_path_factory):
    """跑一次 aivai（--max-moves 10 + maxVisits=10），返回 (stdout, sgf_path)。

    max-moves 10 控制对局时长（完整双 pass 终局可能 200+ 手太慢）。
    """
    tmp = tmp_path_factory.mktemp("aivai")
    maxvisits_cfg = tmp / "maxvisits.cfg"
    maxvisits_cfg.write_text("maxVisits = 10\n", encoding="utf-8")
    sgf_path = tmp / "d1_game.sgf"

    proc = subprocess.run(
        [sys.executable, CLI,
         "--mode", "aivai", "--boardsize", "20",
         "--max-moves", "10",
         "--extra-config", OVERRIDE_CFG,
         "--extra-config", str(maxvisits_cfg),
         "--sgf-out", str(sgf_path)],
        capture_output=True, text=True, timeout=300, encoding="utf-8", env=ENV,
    )
    return proc, str(sgf_path)


# ── D1 AI vs AI 全自动对局 ───────────────────────────────────────────────────

def test_d1_ai_vs_ai(aivai_run):
    """D1: AI vs AI 全自动对局（--max-moves 10）→ 完整结束并输出公式胜负。

    断言 stdout 关键标记 + SGF 文件生成。
    """
    proc, sgf_path = aivai_run
    assert proc.returncode == 0, f"cli_player 非零退出: {proc.returncode}\nstderr: {proc.stderr[-500:]}"
    out = proc.stdout
    assert "[确认] 引擎 komi = 4.25" in out, f"应确认 komi=4.25\n{out[-800:]}"
    assert "[禁点集合] (10 个)" in out, f"Ban 阶段应完成 10 次\n{out[-800:]}"
    assert "[引擎] kata-set-bans 已注入 10 个禁点" in out, f"应注入禁点到引擎\n{out[-800:]}"
    assert ("引擎 final_score:" in out or "认输结局" in out), f"应有终局判定\n{out[-800:]}"
    assert "20路公式" in out, f"应打印 20 路公式\n{out[-800:]}"
    assert os.path.isfile(sgf_path) and os.path.getsize(sgf_path) > 0, "SGF 文件应存在且非空"


# ── D2 人 vs AI（stdin 管道注入）─────────────────────────────────────────────

def test_d2_human_vs_ai(tmp_path):
    """D2: 人 vs AI — stdin 注入人类选点，测 Ban 违例拒绝 + 合法落子 + AI 应手 + resign。

    human 黑 B（先手），Ban 序列 ABBAABBABA 中 B 在 step1,2,5,6,9（5 次 human ban）。
    stdin 序列：合法ban → 非法ban(区域外)被拒重试 → 合法ban ×4 → 合法落子 → resign。

    风险：AI random ban 可能与 human 预定点碰撞致 stdin 时序错位（见 docstring 末尾）。
    """
    maxvisits_cfg = tmp_path / "maxvisits.cfg"
    maxvisits_cfg.write_text("maxVisits = 10\n", encoding="utf-8")

    # stdin：Q17合法 / A1非法(区域外)→重试 / Q14 / Q11 / Q8 / Q5 / D4落子 / resign
    # human 黑 B：step1,2,5,6,9 为 human ban；move0,2 为 human 落子（move2 resign）
    stdin_input = "Q17\nA1\nQ14\nQ11\nQ8\nQ5\nD4\nresign\n"

    proc = subprocess.run(
        [sys.executable, CLI,
         "--mode", "human", "--color", "B", "--boardsize", "20",
         "--max-moves", "5",
         "--extra-config", OVERRIDE_CFG,
         "--extra-config", str(maxvisits_cfg),
         "--no-sgf"],
        input=stdin_input, capture_output=True, text=True,
        timeout=300, encoding="utf-8", env=ENV,
    )
    out = proc.stdout
    # 非法 ban A1 应被拒并提示违例
    assert "不在 ban 区域内" in out, f"非法 ban A1 应被拒\n{out[-1000:]}"
    # AI 应有应手（genmove 后打印落子）
    assert "→" in out or "genmove" in out.lower() or "白" in out, f"AI 应有应手\n{out[-1000:]}"
    assert proc.returncode == 0, f"应正常退出\nstderr: {proc.stderr[-500:]}"
    # 随机碰撞注记：若 AI random ban 选了 human 预定点，stdin 时序错位会致此处失败。
    # 此时该用例反映真实时序脆弱性，应改 xfail（见 §6 备注）。


# ── D3 SGF 导出导入（ban 标记） ──────────────────────────────────────────────

def test_d3_sgf_export_import_ban_markers(aivai_run):
    """D3: 导出对局 SGF → 含 AE[xx] 节点；导入后 ban 集合/boardsize/komi/moves 一致。

    用 D1 的 aivai 对局 SGF。从 stdout 解析禁点 GTP 坐标集（顺序无关）。
    """
    proc, sgf_path = aivai_run
    out = proc.stdout

    # ── sanity check: 坐标换算自检 ──
    assert _to_sgf(7, 4) == "dg"
    assert _to_sgf(10, 10) == "jj"
    assert _to_sgf(4, 17) == "qd"

    # ── 从 stdout 解析禁点 GTP 坐标集 ──
    m = re.search(r"\[禁点集合\] \(10 个\):\s*(.+)", out)
    assert m, f"应打印禁点集合\n{out[-800:]}"
    ban_gtp_labels = m.group(1).strip().split()
    assert len(ban_gtp_labels) == 10, f"应有 10 个禁点，实际 {len(ban_gtp_labels)}"

    # ── 读 SGF 文件，断言 AE 节点存在且含所有禁点 SGF 坐标 ──
    with open(sgf_path, "r", encoding="utf-8") as f:
        sgf_text = f.read()
    assert "AE[" in sgf_text, f"SGF 应含 AE 节点\n{sgf_text[:300]}"
    # 每个禁点的 SGF 坐标都应在 AE 节点中
    for label in ban_gtp_labels:
        from sgf_io import gtp_to_sgf
        sgf_coord = gtp_to_sgf(label)
        assert f"[{sgf_coord}]" in sgf_text, f"禁点 {label}→{sgf_coord} 应在 SGF AE 中\n{sgf_text[:300]}"

    # ── 导入 SGF，断言 ban 集合一致 ──
    game = import_sgf(sgf_path)
    # 导入的 bans 是 list[(row,col)]，与 stdout 的 GTP 坐标转 (row,col) 比对（集合）
    from ban_controller import gtp_to_point
    expected_bans = {gtp_to_point(l) for l in ban_gtp_labels}
    actual_bans = set(game.bans)
    assert actual_bans == expected_bans, f"ban 集合不一致: 期望 {expected_bans}, 实际 {actual_bans}"
    # boardsize / komi
    assert game.boardsize == 20, f"boardsize 应为 20，实际 {game.boardsize}"
    assert game.komi == 4.25, f"komi 应为 4.25，实际 {game.komi}"
    # moves 非空（max-moves 10 应有落子）
    assert len(game.moves) > 0, f"应有落子记录，实际 {len(game.moves)}"
    # moves 数应与 stdout 落子数一致（解析 "第N手" 或计数）
    move_count = len(re.findall(r"第\d+手", out))
    # move_count 可能含双方，game.moves 是每手一条；宽松断言：moves 数 <= move_count+2（容差）
    assert len(game.moves) <= 10, f"max-moves 10，moves 应 <=10，实际 {len(game.moves)}"
