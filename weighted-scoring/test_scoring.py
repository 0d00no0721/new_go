#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_scoring.py — 加权点目数子单元测试。

覆盖 DoD：
  - W=1 等价标准 area scoring（含与 ban-selection 数子的交叉对照）
  - 已知终局加权分（手工算的小盘面）
  - 边界：空盘 / 单子 / 全占
  - 死子处理
  - 与引擎 final_score 一致性（@slow，需起引擎，--slow 启用）

运行：
  $env:PYTHONIOENCODING='utf-8'; python -m pytest test_scoring.py -q
  $env:PYTHONIOENCODING='utf-8'; python -m pytest test_scoring.py -q --slow   # 含引擎对照
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 本方向的 scoring.py
import scoring as ws  # noqa: E402
from scoring import N, load_weights, score_game  # noqa: E402

# 真实权重表路径（若存在），供用真实权重的测试用
WT_PATH = os.path.join(HERE, "weight_table_final.txt")
REAL_W = load_weights(WT_PATH) if os.path.exists(WT_PATH) else None
REAL_W_SUM = sum(sum(row) for row in REAL_W) if REAL_W else None


# ---------- 工具 ----------

def const_w(v, rows=N, cols=N):
    return [[float(v)] * cols for _ in range(rows)]


def cells_w(rows=N, cols=N):
    """每格 W = 100*row + col（1-based），每格唯一，便于验证精确累加。"""
    return [[float(r * 100 + c) for c in range(1, cols + 1)]
            for r in range(1, rows + 1)]


def wall5():
    """5×5：黑竖墙 col3，白竖墙 col5。左(col1-2)=黑独占空，col4=中性。"""
    s = {}
    for r in range(1, 6):
        s[(r, 3)] = "B"
        s[(r, 5)] = "W"
    return s


def full_board(n_on_black, rows=N, cols=N):
    """row-major 填盘：前 n_on_black 为黑，其余为白，无空点。"""
    s = {}
    n = 0
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            s[(r, c)] = "B" if n < n_on_black else "W"
            n += 1
    return s


def align(value, **kw):
    return pytest.approx(value, rel=1e-9, abs=1e-9, **kw)


# ---------- W=1 等价标准 area scoring ----------

def test_w1_equivalence_wall5():
    s = wall5()
    res = score_game(s, const_w(1.0, 5, 5), komi=7.5, rows=5, cols=5)
    assert res["black_weighted"] == pytest.approx(15.0)   # 5子+10独占空
    assert res["white_weighted"] == pytest.approx(5.0)    # 5子无独占空
    assert res["detail"]["neutral"] == 5                  # col4
    assert res["result"] == "B+2.5"   # 5-15+7.5 = -2.5
    assert res["winner"] == "B"


def test_w1_matches_ban_selection_area():
    """与 ban-selection/scoring.py 的 black_area/white_area 交叉对照（W=1 应相等）。"""
    ban_path = os.path.abspath(os.path.join(HERE, "..", "ban-selection", "scoring.py"))
    if not os.path.exists(ban_path):
        pytest.skip("ban-selection/scoring.py 不存在")
    spec = importlib.util.spec_from_file_location("ban_scoring", ban_path)
    ban = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ban)

    positions = [
        wall5(),
        {**wall5(), (1, 1): "W"},                        # 加死子（未标记）
        {(r, c): "B" if (r + c) % 3 == 0 else "W"
         for r in range(1, 20) for c in range(1, 20)},   # 19×19 杂色全盘
        {(r, 10): "B" for r in range(1, 20)},            # 黑整列 col10
    ]
    for i, s in enumerate(positions):
        rows = 19 if max(r for r, _ in s) > 5 else 5
        cols = 19 if max(c for _, c in s) > 5 else 5
        dead = {(1, 1)} if (1, 1) in s and s[(1, 1)] == "W" and i == 1 else set()
        mine = score_game(s, const_w(1.0, rows, cols), komi=7.5,
                          dead_stones=dead, rows=rows, cols=cols)
        ref = ban.score_game(s, set(), rows, cols, komi=7.5, dead_stones=dead)
        assert mine["black_weighted"] == pytest.approx(ref["black_area"], abs=1e-9), f"pos{i} black"
        assert mine["white_weighted"] == pytest.approx(ref["white_area"], abs=1e-9), f"pos{i} white"
        assert mine["detail"]["neutral"] == ref["neutral"], f"pos{i} neutral"


# ---------- 已知终局加权分（手工算） ----------

def test_weighted_3x3_hand_computed():
    """3×3，W=[[1..9]]（0-indexed）。黑整列 col1，白整列 col3，col2 中性。
    black = W(1,1)+W(2,1)+W(3,1) = 1+4+7 = 12
    white = W(1,3)+W(2,3)+W(3,3) = 3+6+9 = 18
    neutral= W(1,2)+W(2,2)+W(3,2) = 2+5+8 = 15
    final = 18-12+7.5 = 13.5 → W+13.5
    """
    w = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    s = {}
    for r in range(1, 4):
        s[(r, 1)] = "B"
        s[(r, 3)] = "W"
    res = score_game(s, w, komi=7.5, rows=3, cols=3)
    assert res["black_weighted"] == pytest.approx(12.0)
    assert res["white_weighted"] == pytest.approx(18.0)
    assert res["neutral_weight"] == pytest.approx(15.0)
    assert res["detail"]["black_stones"] == 3
    assert res["detail"]["white_stones"] == 3
    assert res["detail"]["neutral"] == 3
    assert res["detail"]["sum_weights"] == pytest.approx(45.0)  # 1+..+9
    assert res["result"] == "W+13.5"
    assert res["winner"] == "W"


def test_weighted_5x5_wall_scale():
    """权重全 2.0 → 分数为标准 area 的 2 倍。"""
    s = wall5()
    res = score_game(s, const_w(2.0, 5, 5), komi=7.5, rows=5, cols=5)
    assert res["black_weighted"] == pytest.approx(30.0)   # 15×2
    assert res["white_weighted"] == pytest.approx(10.0)   # 5×2
    assert res["neutral_weight"] == pytest.approx(10.0)   # 5×2
    assert res["result"] == "B+12.5"   # 10-30+7.5 = -12.5


def test_weighted_unique_cells_exact_accumulation():
    """W 每格唯一（100r+c），且形成独占空，逐格精确累加。"""
    s = {(1, 1): "B", (1, 2): "B"}      # 黑左上两子，其余全空→黑独占空
    res = score_game(s, cells_w(), komi=0.0)
    # 黑 = 两个子 + 其余 359 格独占空 = Σ全部 = (1+..+19)*100*19 + (1+..+19)*19
    expect = sum(sum(row) for row in cells_w())
    assert res["black_weighted"] == pytest.approx(expect)
    assert res["white_weighted"] == pytest.approx(0.0)
    assert res["winner"] == "B"


# ---------- 边界：空盘 / 单子 / 全占 ----------

def test_boundary_empty_board_w1():
    res = score_game({}, const_w(1.0), komi=7.5)
    assert res["black_weighted"] == pytest.approx(0.0)
    assert res["white_weighted"] == pytest.approx(0.0)
    assert res["neutral_weight"] == pytest.approx(361.0)
    assert res["detail"]["neutral"] == 361
    assert res["result"] == "W+7.5"   # 0-0+7.5
    assert res["winner"] == "W"


@pytest.mark.skipif(REAL_W is None, reason="weight_table_final.txt 不存在")
def test_boundary_empty_board_real_weights():
    res = score_game({}, REAL_W, komi=7.5)
    assert res["neutral_weight"] == pytest.approx(REAL_W_SUM)   # ΣW≈421.59
    assert abs(res["neutral_weight"] - 421.587) < 0.01
    assert res["result"] == "W+7.5"   # 双方 0 分，仅 komi


def test_boundary_single_stone_w1():
    res = score_game({(10, 10): "B"}, const_w(1.0), komi=7.5)
    assert res["black_weighted"] == pytest.approx(361.0)   # 1子 + 360 独占空
    assert res["white_weighted"] == pytest.approx(0.0)
    assert res["result"] == "B+353.5"   # 0-361+7.5 = -353.5


@pytest.mark.skipif(REAL_W is None, reason="weight_table_final.txt 不存在")
def test_boundary_single_stone_real_weights():
    res = score_game({(10, 10): "B"}, REAL_W, komi=7.5)
    assert res["black_weighted"] == pytest.approx(REAL_W_SUM)   # 单子→全盘黑独占
    assert res["white_weighted"] == pytest.approx(0.0)
    assert res["winner"] == "B"
    assert res["result"] == f"B+{- (0 - REAL_W_SUM + 7.5):.1f}"


def test_boundary_full_board_w1():
    s = full_board(181)   # 181黑 / 180白，无空
    res = score_game(s, const_w(1.0), komi=7.5)
    assert res["black_weighted"] == pytest.approx(181.0)
    assert res["white_weighted"] == pytest.approx(180.0)
    assert res["detail"]["neutral"] == 0
    assert res["result"] == "W+6.5"   # 180-181+7.5


def test_symmetric_board_komi0_draw():
    """3×3 对称，komi=0 → 和局 "0"。"""
    s = {}
    for r in range(1, 4):
        s[(r, 1)] = "B"
        s[(r, 3)] = "W"
    res = score_game(s, const_w(1.0, 3, 3), komi=0.0, rows=3, cols=3)
    assert res["black_weighted"] == pytest.approx(res["white_weighted"])
    assert res["winner"] == ""
    assert res["result"] == "0"


# ---------- 死子 ----------

def test_dead_stones_wall5():
    s = {**wall5(), (1, 1): "W"}          # (1,1) 被黑墙围住，死子
    w = const_w(1.0, 5, 5)
    res_no = score_game(s, w, komi=7.5, rows=5, cols=5)
    assert res_no["black_weighted"] == pytest.approx(5.0)   # 左区域变中性
    res_dead = score_game(s, w, komi=7.5, dead_stones={(1, 1)}, rows=5, cols=5)
    assert res_dead["black_weighted"] == pytest.approx(15.0)  # 死子位置复原为黑独占空
    assert res_dead["white_weighted"] == pytest.approx(5.0)
    assert res_dead["detail"]["white_stones"] == 5            # 6−1死子
    assert res_dead["detail"]["dead"] == 1
    assert res_dead["detail"]["black_territory"] == 10
    assert res_dead["result"] == "B+2.5"


@pytest.mark.skipif(REAL_W is None, reason="weight_table_final.txt 不存在")
def test_dead_stones_real_weights():
    """真实表上，死子位置被"接管"，其 W 计入对方独占空。"""
    # 黑墙 col10（9×?...用 5×5 局部难以凑，直接在 19 上做：
    # 黑整列 col10 与白整列 col19，再在左区中央放一颗白死子 (5,3)。
    s = {(r, 10): "B" for r in range(1, 20)}
    s.update({(r, 19): "W" for r in range(1, 20)})
    s[(5, 3)] = "W"                       # 左区里被围的白死子
    res_no = score_game(s, REAL_W, komi=7.5)
    assert res_no["detail"]["dead"] == 0
    # 标记死子后 black 增加死子位置权重（其所在空块由白→黑独占）
    res_dead = score_game(s, REAL_W, komi=7.5, dead_stones={(5, 3)})
    assert res_dead["detail"]["dead"] == 1
    assert res_dead["black_weighted"] > res_no["black_weighted"]
    assert res_dead["white_weighted"] < res_no["white_weighted"]


# ---------- 与引擎 final_score 一致性（@slow） ----------

def _engine_available():
    exe = os.path.join(HERE, "dist_opencl", "katago.exe")
    cfg = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
    model = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
    ovr = os.path.join(HERE, "gtp_override.cfg")
    return all(os.path.exists(p) for p in (exe, cfg, model, ovr))


@pytest.fixture(scope="module")
def engine():
    if not _engine_available():
        pytest.skip("引擎产物/配置不存在")
    exe = os.path.join(HERE, "dist_opencl", "katago.exe")
    cfg = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
    ovr = os.path.join(HERE, "gtp_override.cfg")
    model = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"

    proc = subprocess.Popen(
        [exe, "gtp", "-config", cfg, "-config", ovr, "-model", model],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    import threading
    threading.Thread(
        target=lambda: [sys.stderr.write("") for _ in iter(proc.stderr.readline, "")],
        daemon=True,
    ).start()

    class E:
        def cmd(self, c):
            proc.stdin.write(c + "\n"); proc.stdin.flush()
            resp, started = [], False
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\n")
                if not started:
                    if line.startswith("=") or line.startswith("?"):
                        started = True
                        resp.append(line)
                        if c.split()[0] not in ("list_commands", "kata-query-weights", "showboard", "kata-analyze"):
                            break
                    continue
                if line == "":
                    break
                resp.append(line)
            return resp[0].startswith("?"), "\n".join(resp)

        def close(self):
            try:
                proc.stdin.write("quit\n"); proc.stdin.flush(); proc.wait(timeout=10)
            except Exception:
                proc.kill()

    g = E()
    ok = g.cmd("name")
    try:
        if ok[0]:
            pytest.skip("引擎无响应")
        g.cmd("boardsize 19"); g.cmd("clear_board")
        g.cmd("kata-clear-weights")            # W=1
        g.cmd("komi 7.5")
        r = g.cmd("kata-set-rules tromp-taylor")
        if r[0]:
            pytest.skip("设置 tromp-taylor 失败")
    except Exception as exc:                    # noqa: BLE001
        g.close()
        pytest.skip(f"引擎初始化失败: {exc}")
    yield g
    g.close()


def _gtp_col(c):
    return chr(ord('A') + c - 1 + (1 if c >= 9 else 0))


@pytest.mark.slow
def test_engine_consistency_empty(engine):
    """空盘 + 双 pass（TT 确定性硬数子）：引擎与 scoring.py 都应 W+7.5。"""
    engine.cmd("clear_board")
    engine.cmd("play B PASS"); engine.cmd("play W PASS")
    err, r = engine.cmd("final_score")
    assert not err
    assert r.startswith("= ")
    engine_result = r[2:].strip()
    mine = score_game({}, const_w(1.0), komi=7.5)["result"]
    assert engine_result == mine == "W+7.5"


@pytest.mark.slow
def test_engine_consistency_wall(engine):
    """黑整列 col10、白整列 col19 + 双 pass：引擎与 scoring.py 都应 B+163.5。
    black=19子+171独占空=190，white=19，final=19-190+7.5=-163.5。"""
    engine.cmd("clear_board")
    # 整列填石：col10 全黑、col19 全白（行向不影响整列结果）
    for rr in range(1, 20):
        engine.cmd(f"play B {_gtp_col(10)}{20 - rr}")
        engine.cmd(f"play W {_gtp_col(19)}{20 - rr}")
    engine.cmd("play B PASS"); engine.cmd("play W PASS")
    err, r = engine.cmd("final_score")
    assert not err
    engine_result = r.split("= ", 1)[1].strip()
    py_stones = {(r, 10): "B" for r in range(1, 20)}
    py_stones.update({(r, 19): "W" for r in range(1, 20)})
    mine = score_game(py_stones, const_w(1.0), komi=7.5)["result"]
    assert engine_result == mine == "B+163.5"


@pytest.mark.slow
def test_engine_consistency_w4():
    """W₄ ↔ 引擎：加载真实 weight_table_final.txt 后，同一盘面的加权 final_score
    应与 scoring.py 加权 result 一致（缺口补测）。

    盘面：黑整列 col10 + 白整列 col19 + 双 pass（无死子判定干扰）。

    注意：引擎对已跑过 final_score 的共享引擎状态敏感（setPosition 恢复可能丢
    pointWeights）→ 本用例**自起一台全新引擎**，先加载权重再落子，保证干净。
    """
    if REAL_W is None:
        pytest.skip("weight_table_final.txt 不存在")
    if not _engine_available():
        pytest.skip("引擎产物/配置不存在")

    exe = os.path.join(HERE, "dist_opencl", "katago.exe")
    cfg = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"
    ovr = os.path.join(HERE, "gtp_override.cfg")
    model = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"

    proc = subprocess.Popen(
        [exe, "gtp", "-config", cfg, "-config", ovr, "-model", model],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    import threading
    threading.Thread(
        target=lambda: [sys.stderr.write("") for _ in iter(proc.stderr.readline, "")],
        daemon=True,
    ).start()

    def cmd(c):
        proc.stdin.write(c + "\n"); proc.stdin.flush()
        resp, started = [], False
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if not started:
                if line.startswith("=") or line.startswith("?"):
                    started = True
                    resp.append(line)
                    if c.split()[0] not in ("list_commands", "kata-query-weights", "showboard", "kata-analyze"):
                        break
                continue
            if line == "":
                break
            resp.append(line)
        return resp[0].startswith("?"), "\n".join(resp)

    try:
        assert not cmd("name")[0]
        cmd("boardsize 19"); cmd("clear_board"); cmd("komi 7.5")
        err, _ = cmd("kata-set-rules tromp-taylor")
        if err:
            pytest.skip("设置 tromp-taylor 失败")

        # 权重表复制到 ASCII 路径（引擎 fopen 不支持中文路径）
        ascii_path = os.path.join(tempfile.gettempdir(), "wt_final_ascii.txt")
        shutil.copyfile(WT_PATH, ascii_path)
        err, r = cmd(f"kata-load-weights {ascii_path}")
        assert not err, f"kata-load-weights 失败: {r}"
        # 确认权重确实改为真实表（非全 1.0）
        err, r = cmd("kata-query-weights")
        assert not err
        vals = [float(x) for x in r.replace("=", "").split()]
        assert len(vals) == N * N
        assert any(abs(v - 1.0) > 1e-6 for v in vals), "权重表应非全 1.0"

        # 注意：此处不能在加载权重后 clear_board（会重置 pointWeights 为 1.0）；
        # 引擎构造函数已 clear_board，加载权重后直接落子即可。
        for rr in range(1, 20):
            cmd(f"play B {_gtp_col(10)}{20 - rr}")
            cmd(f"play W {_gtp_col(19)}{20 - rr}")
        cmd("play B PASS"); cmd("play W PASS")
        err, r = cmd("final_score")
        assert not err, f"final_score 失败: {r}"
        engine_result = r.split("= ", 1)[-1].strip()

        py_stones = {(r, 10): "B" for r in range(1, 20)}
        py_stones.update({(r, 19): "W" for r in range(1, 20)})
        mine = score_game(py_stones, REAL_W, komi=7.5)["result"]

        # 回归：W₄ 应显著不同于 W=1（B+163.5），证明权重确实生效
        assert engine_result != "B+163.5", "加权 final_score 不应等于 W=1 值"
        assert engine_result == mine, f"引擎 {engine_result} != scoring.py {mine}"
    finally:
        try:
            proc.stdin.write("quit\n"); proc.stdin.flush(); proc.wait(timeout=10)
        except Exception:
            proc.kill()


# ---------- 与 scoring.js 一致性（1:1 端口对照） ----------

NODE_DRIVER = os.path.join(tempfile.gettempdir(), "opencode", "js_driver.js")
JS_SCORING = os.path.join(HERE, "scoring.js")


def _node_available():
    return all(os.path.exists(p) for p in (NODE_DRIVER, JS_SCORING)) and subprocess.run(
        ["node", "-v"], capture_output=True).returncode == 0


def run_js(payload):
    proc = subprocess.run(
        ["node", NODE_DRIVER, JS_SCORING],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _assert_same(py_result, js_result):
    for field in ("black_weighted", "white_weighted", "neutral_weight",
                  "final_white_minus_black_score", "komi"):
        assert js_result[field] == align(py_result[field]), field
    assert js_result["result"] == py_result["result"]
    assert js_result["winner"] == py_result["winner"]
    for field in ("black_stones", "white_stones", "black_territory", "white_territory",
                  "neutral", "dead"):
        assert js_result["detail"][field] == py_result["detail"][field], field
    for field in ("black_stones_weight", "white_stones_weight", "black_territory_weight",
                  "white_territory_weight", "neutral_weight", "sum_weights"):
        assert js_result["detail"][field] == align(py_result["detail"][field]), field


@pytest.mark.skipif(not _node_available(), reason="node 或驱动文件缺失")
def test_js_port_consistency():
    """同一盘面，scoring.py 与 scoring.js 结果逐字段一致（含死子、真权重）。"""
    scenarios = [
        {
            "name": "wall5_w1",
            "stones": {f"{r},{3}": "B" for r in range(1, 6)},
            "weights": [[1.0] * 5 for _ in range(5)],
            "komi": 7.5, "deadStones": [], "rows": 5, "cols": 5,
        },
        {
            "name": "dead_wall5",
            "stones": {**{f"{r},{3}": "B" for r in range(1, 6)},
                       **{f"{r},{5}": "W" for r in range(1, 6)}, "1,1": "W"},
            "weights": [[1.0] * 5 for _ in range(5)],
            "komi": 7.5, "deadStones": ["1,1"], "rows": 5, "cols": 5,
        },
        {
            "name": "full_w1",
            "stones": {f"{r},{c}": ("B" if (r - 1) * 19 + c <= 181 else "W")
                       for r in range(1, 20) for c in range(1, 20)},
            "weights": [[1.0] * 19 for _ in range(19)],
            "komi": 7.5, "deadStones": [], "rows": 19, "cols": 19,
        },
    ]
    if REAL_W is not None:
        scenarios.append({
            "name": "single_real",
            "stones": {"10,10": "B"},
            "weights": REAL_W,
            "komi": 7.5, "deadStones": [], "rows": 19, "cols": 19,
        })
    for sc in scenarios:
        js_result = run_js(sc)
        py_stones = {tuple(map(int, k.split(","))): v for k, v in sc["stones"].items()}
        py_dead = {tuple(map(int, k.split(","))) for k in sc.get("deadStones", [])}
        py_result = score_game(
            py_stones, sc["weights"], komi=sc["komi"],
            dead_stones=py_dead, rows=sc["rows"], cols=sc["cols"],
        )
        _assert_same(py_result, js_result)