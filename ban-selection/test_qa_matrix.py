"""
test_qa_matrix.py — QA 测试矩阵 A1-A8（Ban 阶段校验）

依赖：RULES ✅（ban_controller 已就绪，36 测试全过）
覆盖：DoD3 — Ban 控制器区域 / 不重复 / 连通性 / 违例判负

API 约定（来自 ban_controller.py）：
  - BanResult.valid / .reason          （注意：字段名 valid，非 accepted）
  - bc.banned: set[(row, col)]
  - bc.violations: {"A": int, "B": int}
  - bc.concluded: bool / bc.conclusion_reason: str
  - bc.step / bc.current_player
  - 默认配置：20路, 14×14区域(行4-17,列4-17), 10禁, 序列 ABBAABBABA, max_violations=3
"""

import pytest

from ban_controller import BanController


@pytest.fixture
def bc():
    """每个用例全新控制器，默认配置。"""
    return BanController()


# ── A1 区域-合法 ─────────────────────────────────────────────────────────────

def test_a1_region_inside(bc):
    """A1: ban(10,10) 区域中心 → 接受；禁点集={(10,10)}。"""
    r = bc.submit(10, 10)
    assert r.valid
    assert bc.banned == {(10, 10)}


# ── A2 区域-越界 ─────────────────────────────────────────────────────────────

def test_a2_region_out_of_bounds():
    """A2: 行越界 / 列越界 / 角落各自拒绝，违例计在当前选手并递增。

    注意：max_violations=3，第 3 次违例触发判负；故 (18,18) 用全新控制器验证
    其本身为越界拒绝（否则阶段已结束只会返回"已结束"）。
    """
    bc = BanController()

    # 行越界 (row=3 < region_row_min=4)
    r = bc.submit(3, 10)
    assert not r.valid
    assert "不在 ban 区域内" in r.reason
    assert bc.violations["A"] == 1

    # 列越界 (col=18 > region_col_max=17)
    r = bc.submit(10, 18)
    assert not r.valid
    assert bc.violations["A"] == 2

    # 角落 (1,1) — 行列均越界；第 3 次违例触发判负
    r = bc.submit(1, 1)
    assert not r.valid
    assert bc.violations["A"] == 3
    assert bc.concluded
    assert "violation" in bc.conclusion_reason

    # 角落 (18,18) — 用全新控制器验证该点本身越界
    bc2 = BanController()
    r = bc2.submit(18, 18)
    assert not r.valid
    assert "不在 ban 区域内" in r.reason
    assert bc2.violations["A"] == 1


# ── A3 重复 ──────────────────────────────────────────────────────────────────

def test_a3_duplicate(bc):
    """A3: 先 ban(10,10) 成功，再 ban(10,10) → 拒绝（重复），违例 +1。

    序列第 2 步为 B，重复 ban 计在 B。
    """
    r = bc.submit(10, 10)
    assert r.valid
    r = bc.submit(10, 10)
    assert not r.valid
    assert "已被标记为禁点" in r.reason
    assert bc.violations["B"] == 1


# ── A4 连通-单点 ─────────────────────────────────────────────────────────────

def test_a4_connectivity_single_point(bc):
    """A4: ban(10,10) 单点 → 连通保持，合法。"""
    r = bc.submit(10, 10)
    assert r.valid
    assert bc.banned == {(10, 10)}


# ── A5 连通-孤立单点 ─────────────────────────────────────────────────────────

def test_a5_connectivity_isolate_single():
    """A5: 依次 (8,9)(9,8)(9,10) 三次成功，第 4 次 (10,9)
    使 (9,9) 四邻全禁 → 孤立 → 拒绝该次（连通性失败）。

    (9,9) 的四邻 = (8,9)(10,9)(9,8)(9,10)；前三次 ban 三个邻点，第四次封死。
    """
    bc = BanController()
    assert bc.submit(8, 9).valid     # A  step0
    assert bc.submit(9, 8).valid     # B  step1
    assert bc.submit(9, 10).valid    # B  step2
    r = bc.submit(10, 9)             # A  step3 → 围死 (9,9)
    assert not r.valid
    assert "分割" in r.reason        # check_connectivity 的 reason 含"分割"
    assert (9, 9) not in bc.banned   # (9,9) 未被 ban，仅被孤立
    assert bc.violations["A"] == 1


# ── A6 连通-区域孤立 ─────────────────────────────────────────────────────────

def test_a6_connectivity_isolate_region():
    """A6: 依次 (9,10)(11,10)(10,9)(9,11)(11,11) 五次成功，
    第 6 次 (10,12) 使 {(10,10),(10,11)} 2 点孤立 → 拒绝。

    (10,10) 外邻 = (9,10)(11,10)(10,9)；(10,11) 外邻 = (9,11)(11,11)(10,12)。
    六个外邻全禁后，2 点相互连通但与外界断开。
    """
    bc = BanController()
    assert bc.submit(9, 10).valid    # A  step0
    assert bc.submit(11, 10).valid   # B  step1
    assert bc.submit(10, 9).valid    # B  step2
    assert bc.submit(9, 11).valid    # A  step3
    assert bc.submit(11, 11).valid   # A  step4
    r = bc.submit(10, 12)            # B  step5 → 封死 (10,11) 最后出口
    assert not r.valid
    assert "分割" in r.reason
    assert (10, 10) not in bc.banned
    assert (10, 11) not in bc.banned
    assert bc.violations["B"] == 1


# ── A7 连通-小空洞 ───────────────────────────────────────────────────────────

def test_a7_connectivity_small_hole(bc):
    """A7: L 形 (10,10)(10,11)(11,10) 三次
    → (11,11) 仍经 (12,11)(11,12) 连通 → 合法（小空洞）。

    (11,11) 四邻 = (10,11)✗(11,10)✗(12,11)✓(11,12)✓，仍有两条出路。
    """
    assert bc.submit(10, 10).valid   # A  step0
    assert bc.submit(10, 11).valid   # B  step1
    assert bc.submit(11, 10).valid   # B  step2
    assert (11, 11) not in bc.banned
    assert bc.step == 3
    assert not bc.concluded


# ── A8 违例判负 ──────────────────────────────────────────────────────────────

def test_a8_three_violations_lose(bc):
    """A8: 连续 3 次区域外 ban(1,1) → 第 3 次违例后 concluded，reason 含 violation。

    (1,1) 区域外，每次 region 校验先失败，不入 banned，故三次均命中 region 检查。
    违例计在 step0 的当前选手 A。
    """
    r = bc.submit(1, 1)
    assert not r.valid
    assert not bc.concluded          # 1 < 3
    assert bc.violations["A"] == 1

    r = bc.submit(1, 1)
    assert not r.valid
    assert not bc.concluded          # 2 < 3
    assert bc.violations["A"] == 2

    r = bc.submit(1, 1)
    assert not r.valid
    assert bc.concluded              # 3 >= 3 → 判负
    assert bc.violations["A"] == 3
    assert "violation" in bc.conclusion_reason
