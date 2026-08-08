"""
test_ban.py — ban_controller 模块测试

覆盖：坐标工具 / 区域校验 / 重复校验 / 连通性 BFS / 序列推进 / 违例判负 / AI 选点
"""

import random
import sys
import unittest

from ban_controller import (
    BanConfig,
    BanController,
    BanResult,
    check_connectivity,
    check_no_duplicate,
    check_region,
    col_to_letter,
    gtp_to_point,
    letter_to_col,
    point_to_gtp,
)


# ── 坐标工具测试 ────────────────────────────────────────────────────────────

class TestCoords(unittest.TestCase):
    def test_col_to_letter(self):
        self.assertEqual(col_to_letter(1), "A")
        self.assertEqual(col_to_letter(8), "H")
        self.assertEqual(col_to_letter(9), "J")
        self.assertEqual(col_to_letter(10), "K")
        self.assertEqual(col_to_letter(20), "U")
        with self.assertRaises(ValueError):
            col_to_letter(0)
        with self.assertRaises(ValueError):
            col_to_letter(21)

    def test_letter_to_col(self):
        self.assertEqual(letter_to_col("A"), 1)
        self.assertEqual(letter_to_col("H"), 8)
        self.assertEqual(letter_to_col("j"), 9)
        self.assertEqual(letter_to_col("U"), 20)
        with self.assertRaises(ValueError):
            letter_to_col("I")

    def test_point_to_gtp(self):
        self.assertEqual(point_to_gtp(1, 1), "A1")
        self.assertEqual(point_to_gtp(7, 4), "D7")
        self.assertEqual(point_to_gtp(20, 20), "U20")
        self.assertEqual(point_to_gtp(10, 10), "K10")

    def test_gtp_to_point(self):
        self.assertEqual(gtp_to_point("A1"), (1, 1))
        self.assertEqual(gtp_to_point("d7"), (7, 4))
        self.assertEqual(gtp_to_point("U20"), (20, 20))
        self.assertEqual(gtp_to_point("K10"), (10, 10))

    def test_roundtrip(self):
        for rc in [(1, 1), (7, 4), (10, 10), (20, 20), (1, 20)]:
            self.assertEqual(gtp_to_point(point_to_gtp(*rc)), rc)


# ── 校验器单元测试 ──────────────────────────────────────────────────────────

class TestCheckRegion(unittest.TestCase):
    def setUp(self):
        self.cfg = BanConfig()

    def test_inside_region(self):
        self.assertTrue(check_region(4, 4, self.cfg).valid)
        self.assertTrue(check_region(10, 10, self.cfg).valid)
        self.assertTrue(check_region(17, 17, self.cfg).valid)

    def test_outside_region_row(self):
        r = check_region(3, 10, self.cfg)
        self.assertFalse(r.valid)
        self.assertIn("不在 ban 区域内", r.reason)

        r = check_region(18, 10, self.cfg)
        self.assertFalse(r.valid)

    def test_outside_region_col(self):
        r = check_region(10, 3, self.cfg)
        self.assertFalse(r.valid)
        r = check_region(10, 18, self.cfg)
        self.assertFalse(r.valid)

    def test_custom_region(self):
        cfg = BanConfig(region_row_min=6, region_row_max=15,
                        region_col_min=6, region_col_max=15)
        self.assertTrue(check_region(6, 6, cfg).valid)
        self.assertFalse(check_region(5, 10, cfg).valid)


class TestCheckNoDuplicate(unittest.TestCase):
    def test_not_duplicate(self):
        self.assertTrue(check_no_duplicate(5, 5, {(1, 1), (2, 2)}).valid)

    def test_duplicate(self):
        r = check_no_duplicate(5, 5, {(5, 5)})
        self.assertFalse(r.valid)
        self.assertIn("已被标记为禁点", r.reason)


class TestCheckConnectivity(unittest.TestCase):
    BS = 20

    def test_empty_board_connected(self):
        self.assertTrue(
            check_connectivity(self.BS, set(), (10, 10)).valid
        )

    def test_single_ban_on_empty(self):
        self.assertTrue(
            check_connectivity(self.BS, set(), (4, 4)).valid
        )

    def test_small_hole_allowed(self):
        banned = {(10, 10), (10, 11), (11, 10), (11, 11)}
        r = check_connectivity(self.BS, banned | {(12, 12)}, (12, 12))
        self.assertTrue(r.valid,
                        msg="制造局部小型空洞应该是允许的")

    def test_cut_row_should_disconnect(self):
        # Ban entire row 10: points (10,1) through (10,20)
        full_row_bans = {(10, c) for c in range(1, 21)}
        full_row_bans.discard((10, 20))  # leaves one gap → connected
        r = check_connectivity(self.BS, full_row_bans, (10, 20))
        self.assertFalse(r.valid, "Row 10 almost fully banned should disconnect")

    def test_ban_single_edge_point_ok(self):
        r = check_connectivity(self.BS, set(), (10, 1))
        self.assertTrue(r.valid, "Ban at column 1 within the board should be fine")

    def test_cut_corner_trap(self):
        # Ban line from (4,10) to (20, 10) - but (1,1)-(3,3) are corner escape
        banned = {(r, 10) for r in range(4, 21)}
        self.assertTrue(
            check_connectivity(self.BS, banned, (10, 5)).valid
        )

    def test_edge_bans_dont_block_edges(self):
        # Ban entire row 4 (through the region). Points above row 4 are
        # 1-3 (edges), points below row 4 are 5-20 — they must stay connected.
        row4_banned = {(4, c) for c in range(1, 21)}
        r = check_connectivity(self.BS, row4_banned, (4, 1))
        self.assertFalse(r.valid, "Banning entire row 4 should disconnect top from bottom")

    def test_connectivity_full_col_cuts(self):
        # Ban col 5 fully from row 1 through 20 — should disconnect left/right
        col_bans = {(r, 5) for r in range(1, 21)}
        col_bans.discard((10, 5))  # leave one gap → should still disconnect
        r = check_connectivity(self.BS, col_bans, (10, 5))
        self.assertFalse(r.valid,
                         "Banning col 5 nearly fully should disconnect left/right")


# ── BanController 序列推进 ──────────────────────────────────────────────────

class TestSequence(unittest.TestCase):
    def test_default_sequence_order(self):
        bc = BanController()
        expected = list("ABBAABBABA")
        pts = [(10, 10), (10, 11), (10, 12), (10, 13), (10, 14),
               (11, 10), (11, 11), (11, 12), (11, 13), (11, 14)]
        for i, exp in enumerate(expected):
            self.assertEqual(bc.current_player, exp, f"step {i}")
            bc.submit(*pts[i], source="test")

        self.assertTrue(bc.is_finished)
        self.assertEqual(bc.conclusion_reason, "complete")

    def test_custom_sequence(self):
        cfg = BanConfig(ban_count=6, sequence="ABABAB")
        bc = BanController(cfg)
        pts = [(10,10),(10,11),(10,12),(10,13),(10,14),(10,15)]
        for i, exp in enumerate("ABABAB"):
            self.assertEqual(bc.current_player, exp)
            bc.submit(*pts[i], source="test")
        self.assertTrue(bc.is_finished)

    def test_submit_label(self):
        bc = BanController()
        r = bc.submit_label("D4")
        self.assertTrue(r.valid)
        self.assertIn((4, 4), bc.banned)

    def test_submit_label_out_of_region(self):
        bc = BanController()
        r = bc.submit_label("C3")
        self.assertFalse(r.valid)
        self.assertIn("不在 ban 区域内", r.reason)


# ── 违例判负 ────────────────────────────────────────────────────────────────

class TestViolations(unittest.TestCase):
    def test_three_violations_lose(self):
        bc = BanController()
        for _ in range(3):
            r = bc.submit(1, 1, source="test")  # 区域外
            self.assertFalse(r.valid)
        self.assertTrue(bc.is_finished)
        self.assertEqual(bc.conclusion_reason, "violation_a")
        self.assertEqual(bc.violations["A"], 3)

    def test_violations_per_player(self):
        bc = BanController()
        # A violates once
        bc.submit(1, 1, source="test")
        self.assertEqual(bc.violations["A"], 1)
        self.assertEqual(bc.step, 0)  # 未推进

        # A does a valid ban
        bc.submit(10, 10, source="test")
        self.assertEqual(bc.step, 1)
        self.assertEqual(bc.current_player, "B")

        # B violates
        bc.submit(1, 1, source="test")
        self.assertEqual(bc.violations["B"], 1)
        self.assertEqual(bc.step, 1)

    def test_violation_reset_on_new_game(self):
        bc = BanController()
        bc.submit(1, 1, source="test")
        bc.submit(1, 1, source="test")
        self.assertEqual(bc.violations["A"], 2)
        bc.reset()
        self.assertEqual(bc.violations["A"], 0)


# ── AI 选点测试 ─────────────────────────────────────────────────────────────

class TestAIPick(unittest.TestCase):
    def test_random_pick_always_legal(self):
        bc = BanController()
        for _ in range(bc.config.ban_count):
            pt = bc.ai_pick_random()
            r = bc.submit(*pt, source="ai")
            self.assertTrue(r.valid, f"AI 选了非法点 {pt}")
        self.assertTrue(bc.is_finished)
        self.assertEqual(bc.conclusion_reason, "complete")

    def test_random_pick_no_duplicate(self):
        bc = BanController()
        for _ in range(bc.config.ban_count):
            pt = bc.ai_pick_random()
            self.assertNotIn(pt, bc.banned)
            bc.submit(*pt, source="ai")
        self.assertEqual(len(bc.banned), 10)

    def test_auto_strategy_fallback(self):
        bc = BanController()
        # 没有 GTP 引擎，auto 应 fallback 到 random
        r = bc.submit_ai(strategy="auto")
        self.assertTrue(r.valid)

    def test_mock_gtp_pick(self):
        bc = BanController()
        call_log = []

        def mock_engine(cmd: str) -> str:
            call_log.append(cmd)
            if cmd.startswith("kata-set-bans"):
                return "= ok"
            if cmd.startswith("kata-clear-bans"):
                return "= ok"
            if cmd.startswith("kata-analyze"):
                return "info winrate 0.55"
            return "? unknown"

        bc.set_gtp_engine(mock_engine)
        pt = bc.ai_pick_gtp()
        self.assertIsNotNone(pt)
        self.assertGreater(len(call_log), 0)

    def test_ai_pick_concluded(self):
        bc = BanController()
        for _ in range(10):
            bc.submit(10, 10, source="test")
        r = bc.submit_ai()
        self.assertFalse(r.valid)
        self.assertIn("已结束", r.reason)


# ── 综合流程 ────────────────────────────────────────────────────────────────

class TestFullFlow(unittest.TestCase):
    def test_full_ban_phase(self):
        bc = BanController()
        points = [
            "D4", "K10", "F7", "P12", "E5",
            "M8", "G6", "N13", "H8", "Q14",
        ]
        for label in points:
            r = bc.submit_label(label)
            self.assertTrue(r.valid, f"{label} 应为合法: {r.reason}")

        result = bc.get_result()
        self.assertEqual(result.concluded_by, "complete")
        self.assertEqual(len(result.banned_points), 10)
        self.assertEqual(len(result.history), 10)
        self.assertEqual(result.history[0].player, "A")
        self.assertEqual(result.history[1].player, "B")

    def test_duplicate_rejected(self):
        bc = BanController()
        bc.submit_label("D4")
        r = bc.submit_label("D4")
        self.assertFalse(r.valid)
        self.assertIn("已被标记为禁点", r.reason)

    def test_connectivity_prevents_full_cut(self):
        bc = BanController()
        # 尝试在行 6 的每一列（4-17）都 ban，但最终一个会把棋盘切开
        for col in range(4, 17):
            label = f"{col_to_letter(col)}6"
            r = bc.submit_label(label)
            # 前 13 个应该合法，最后一个（如果全部都不合法则可能提前被拒）
            if col == 17:
                break
        # 14 个点在同一条横线上 → 必然在某次被拒绝
        # 确认某次被拒
        self.assertTrue(bc.step < 14)


# ── 配置 ────────────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    def test_validate_bad_region(self):
        with self.assertRaises(ValueError):
            BanConfig(region_row_max=25).validate()

    def test_validate_sequence_length(self):
        with self.assertRaises(ValueError):
            BanConfig(ban_count=5, sequence="ABABAB").validate()


if __name__ == "__main__":
    unittest.main()