"""
cli_player.py — 20路Ban选围棋 CLI 对弈工具

职责：
  1. GtpEngine 类：通过 subprocess 管道与 KataGo 通信（GTP 协议）
  2. run_game()：Ban 阶段（调用 BanController）+ 正式对局（双引擎交替 genmove）
  3. review_sgf()：SGF 导入复盘（打印棋谱 + 禁点 + 终局棋盘）
  4. main()：命令行入口（aivai / human / sgf-in 复盘模式）

引擎：使用 ENGINE 改造后的 KataGo v1.16.4（20 路 + kata-set-bans + komi 4.25）。
      komi 4.25 经 -override-config ignoreGTPAndForceKomi=4.25 生效（不发 GTP komi 命令）。
      19 路网络经 -override-config gtpForceMaxNNSize=true pad 到 20 路。

GTP 协议响应格式：
  成功：= <内容>\n[后续行]\n\n   （以等号开头，空行结束）
  失败：? <错误>\n\n             （以问号开头，空行结束）
  kata-analyze 为流式输出：info 行持续输出，不以 = 开头，靠新命令终止。

SGF 坐标系（详见 sgf_io.py）：
  SGF 小写不跳 I（a-t），GTP 大写跳 I（A-H,J-U），经 (row,col) 中转。
  ban 点用根节点 AE 属性记录，导入只读 AE。
"""

from __future__ import annotations

import argparse
import datetime
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

from ban_controller import (
    BanConfig,
    BanController,
    col_to_letter,
    gtp_to_point,
    point_to_gtp,
)
from sgf_io import (
    ReplayBoard,
    SgfGame,
    export_sgf,
    import_sgf,
    point_to_sgf,
    sgf_to_gtp,
    sgf_to_point,
)

# ── 默认资源路径 ────────────────────────────────────────────────────────────

DEFAULT_ENGINE = r"E:\小工具\new_go\ban-selection\dist_opencl\katago.exe"
DEFAULT_MODEL = r"E:\2026-01-07-win64-KataGo\weights\28b.bin.gz"
DEFAULT_CONFIG = r"E:\2026-01-07-win64-KataGo\katago_configs\default_gtp.cfg"

# 20 路 Ban 选围棋必需的 override-config（硬编码为默认，确保开箱即用）
DEFAULT_OVERRIDE_CONFIGS = [
    "ignoreGTPAndForceKomi=4.25",   # 强制 komi 4.25（绕过 GTP komi 半整数限制）
    "gtpForceMaxNNSize=true",       # 19 路网络 pad 到 MAX_LEN（支持 20 路）
]

# 选手 ↔ 棋色映射（规则：选手 B 执黑，选手 A 执白）
PLAYER_TO_COLOR = {"B": "B", "A": "W"}      # 选手 → 棋色 B/W
COLOR_TO_PLAYER = {"B": "B", "W": "A"}      # 棋色 → 选手


# ── GtpEngine：subprocess 管道通信 ──────────────────────────────────────────

class GtpEngine:
    """与一个 KataGo 实例通信的 GTP 客户端。

    读线程持续把 stdout 行放入 queue，send/analyze 从 queue 消费。
    这样流式命令（kata-analyze）与标准命令可共用同一读取通道，
    analyze 的残留 info 行会被下一次 send 自动跳过。
    """

    def __init__(
        self,
        exe_path: str,
        model_path: str,
        config_path: str,
        boardsize: int = 19,
        color: str = "B",
        stderr_path: Optional[str] = None,
        extra_configs: Optional[list[str]] = None,
        override_configs: Optional[list[str]] = None,
        init_timeout: float = 900.0,
    ):
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"引擎不存在: {exe_path}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"权重不存在: {model_path}")
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置不存在: {config_path}")
        for ec in (extra_configs or []):
            if not os.path.isfile(ec):
                raise FileNotFoundError(f"附加配置不存在: {ec}")

        args = [exe_path, "gtp", "-config", config_path]
        for ec in (extra_configs or []):
            args += ["-config", ec]
        for oc in (override_configs or []):
            args += ["-override-config", oc]
        args += ["-model", model_path]
        self._init_timeout = init_timeout

        # stderr 重定向到文件便于调试启动失败，避免污染主输出
        self._stderr_file = None
        if stderr_path:
            self._stderr_file = open(stderr_path, "w", encoding="utf-8")
            stderr_target = self._stderr_file
        else:
            stderr_target = subprocess.DEVNULL

        self.color = color
        self.boardsize = boardsize
        self._closed = False

        try:
            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                text=True,
                encoding="utf-8",
                bufsize=1,  # 行缓冲
            )
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._proc = subprocess.Popen(args, **popen_kwargs)
        except Exception as e:
            if self._stderr_file:
                self._stderr_file.close()
            raise RuntimeError(f"启动引擎失败: {e}") from e

        # 守护读线程：持续 readline → queue
        self._read_queue: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        # 初始化棋盘（首次启动可能触发 OpenCL tuning，用大超时）
        self.boardsize_n(boardsize, timeout=self._init_timeout)
        self.clear_board(timeout=self._init_timeout)

    # ── 读线程 ──

    def _read_loop(self) -> None:
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    break  # stdout 关闭（进程退出）
                self._read_queue.put(line)
        except Exception:
            pass

    # ── 标准命令 ──

    def send(self, cmd: str, timeout: float = 120.0) -> str:
        """发送 GTP 命令，返回去掉 = / ? 前缀的响应内容。

        失败（? 前缀）抛 RuntimeError。流式命令残留的 info 行会被跳过。
        """
        if self._closed or self._proc.poll() is not None:
            raise RuntimeError(f"引擎已退出，无法发送: {cmd}")

        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"写入引擎管道失败: {e}") from e

        deadline = time.time() + timeout
        header: Optional[str] = None

        # 找到响应头（以 = 或 ? 开头），跳过 analyze 残留的 info 行
        while header is None:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]"
                    )
                continue
            stripped = line.strip()
            if stripped.startswith("=") or stripped.startswith("?"):
                header = stripped
            # 否则丢弃（analyze 流式残留）

        prefix = header[0]
        rest = header[1:].strip()

        # 读取后续行直到空行
        body: list[str] = []
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"等待 GTP 响应空行超时 [{cmd}]")
            try:
                line = self._read_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"引擎进程已退出 (code={self._proc.returncode}) [{cmd}]"
                    )
                continue
            if line.strip() == "":
                break
            body.append(line.rstrip("\r\n"))

        content = rest
        if body:
            content = (rest + "\n" + "\n".join(body)) if rest else "\n".join(body)

        if prefix == "?":
            raise RuntimeError(f"GTP 命令失败 [{cmd}]: {content}")
        return content

    # ── 流式分析命令 ──

    def analyze(self, interval: float = 1.0) -> str:
        """kata-analyze 流式输出。读取 interval 秒内的所有行并返回。

        注意：调用后引擎处于流式模式，下一次 send 会自动终止并跳过残留。
        interval 参数单位为秒，内部转换为厘秒（KataGo 要求）。
        """
        if self._closed or self._proc.poll() is not None:
            raise RuntimeError("引擎已退出，无法 analyze")

        cmd = f"kata-analyze interval {int(interval * 100)}"
        try:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"写入引擎管道失败: {e}") from e

        lines: list[str] = []
        deadline = time.time() + interval
        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                line = self._read_queue.get(timeout=max(0.01, remaining))
            except queue.Empty:
                break
            s = line.strip()
            if s == "":
                continue
            lines.append(s)
        return "\n".join(lines)

    # ── 高级封装 ──

    def boardsize_n(self, n, timeout: Optional[float] = None) -> str:
        """设置棋盘大小。n 为 int（正方形）或 (rows, cols) tuple（非正方形）。"""
        if isinstance(n, tuple):
            cmd = f"boardsize {n[0]}:{n[1]}"
        else:
            cmd = f"boardsize {n}"
        return self.send(cmd, timeout=timeout)

    def clear_board(self, timeout: Optional[float] = None) -> str:
        return self.send("clear_board", timeout=timeout)

    def komi(self, k: float) -> str:
        return self.send(f"komi {k}")

    def genmove(self, color: str) -> str:
        """生成一手。color 为 'black' 或 'white'。返回 GTP 坐标 / pass / resign。"""
        return self.send(f"genmove {color}").strip()

    def play(self, color: str, coord: str) -> str:
        """通知引擎对方落子。color 为 'black'/'white'，coord 为 GTP 坐标或 pass。"""
        return self.send(f"play {color} {coord}")

    def final_score(self) -> str:
        """终局数子。返回引擎原始结果，如 'B+4.5' / 'W+3.75' / '0'。"""
        return self.send("final_score").strip()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.poll() is None:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        if self._stderr_file:
            try:
                self._stderr_file.close()
            except Exception:
                pass


# ── 棋盘打印 ────────────────────────────────────────────────────────────────

def print_board(
    stones: dict[tuple[int, int], str],
    banned: set[tuple[int, int]],
    boardsize,
) -> None:
    """打印棋盘。stones: (row,col)->'B'/'W'；banned 禁点用 X；空点用 .
    boardsize: int（正方形）或 (rows, cols) tuple（非正方形）。
    """
    if isinstance(boardsize, tuple):
        rows, cols_n = boardsize
    else:
        rows = cols_n = boardsize
    cols = "".join(col_to_letter(c) for c in range(1, cols_n + 1))
    # 列标头（每两字符一列）
    header = "   " + " ".join(cols)
    print(header)
    for r in range(rows, 0, -1):
        parts = [f"{r:>2} "]
        for c in range(1, cols_n + 1):
            if (r, c) in banned:
                parts.append("X")
            elif (r, c) in stones:
                parts.append(stones[(r, c)])
            else:
                parts.append(".")
            parts.append(" ")
        parts.append(f"{r:<2}")
        print("".join(parts))
    print(header)


# ── 对局配置 ────────────────────────────────────────────────────────────────

@dataclass
class GameConfig:
    mode: str = "aivai"            # aivai / human
    color: str = "B"               # human 模式下人类棋色 B/W
    boardsize: "int | tuple[int, int]" = 20  # int（正方形）或 (rows, cols) tuple（非正方形）
    engine: str = DEFAULT_ENGINE
    model: str = DEFAULT_MODEL
    config: str = DEFAULT_CONFIG
    extra_configs: Optional[list[str]] = None  # 附加 config（如 homeDataDir 缓存）
    override_configs: Optional[list[str]] = None  # override-config（默认用 DEFAULT_OVERRIDE_CONFIGS）
    ban_strategy: str = "random"   # random / gtp / auto
    max_moves: int = 0             # 正式对局最大手数（0=不限）
    komi: float = 4.25             # 贴子（经 override-config 生效，非 GTP komi 命令）
    sgf_out: Optional[str] = None  # SGF 导出路径（None=自动生成名）
    no_sgf: bool = False           # 不导出 SGF

    @property
    def board_rows(self) -> int:
        return self.boardsize[0] if isinstance(self.boardsize, tuple) else self.boardsize

    @property
    def board_cols(self) -> int:
        return self.boardsize[1] if isinstance(self.boardsize, tuple) else self.boardsize


# ── 对局主流程 ──────────────────────────────────────────────────────────────

def run_game(cfg: GameConfig) -> None:
    """完整对局：Ban 阶段 → 正式对局 → 终局数子。"""
    boardsize = cfg.boardsize
    board_rows = cfg.board_rows
    board_cols = cfg.board_cols

    # 选手 ↔ 棋色
    human_color = cfg.color                # "B" 或 "W"
    human_player = COLOR_TO_PLAYER[human_color]  # 选手 "A" 或 "B"

    # ── 启动两个引擎：黑(选手B) / 白(选手A) ──
    override_configs = cfg.override_configs or list(DEFAULT_OVERRIDE_CONFIGS)
    print(f"[启动] 黑方引擎 (选手B) ...")
    eng_black = GtpEngine(
        cfg.engine, cfg.model, cfg.config,
        boardsize=boardsize, color="B",
        stderr_path="engine_black.log",
        extra_configs=cfg.extra_configs,
        override_configs=override_configs,
    )
    print(f"[启动] 白方引擎 (选手A) ...")
    eng_white = GtpEngine(
        cfg.engine, cfg.model, cfg.config,
        boardsize=boardsize, color="W",
        stderr_path="engine_white.log",
        extra_configs=cfg.extra_configs,
        override_configs=override_configs,
    )

    try:
        # 确认 komi 经 override-config 生效（不发 komi 命令，GTP 会拒 4.25）
        try:
            actual_komi = eng_black.send("get_komi").strip()
            print(f"[确认] 引擎 komi = {actual_komi}（经 override-config 生效）")
        except RuntimeError:
            pass  # 某些引擎版本可能无 get_komi，忽略

        # ═══════════ Ban 阶段 ═══════════
        ban_cfg = BanConfig(
            board_size=board_rows,
            board_cols=board_cols,
        )
        bc = BanController(ban_cfg)

        # 注入真实 GTP 引擎接口（供 BanController 的 ai_pick_gtp 策略使用）
        def _gtp_callable(cmd: str) -> str:
            if cmd.startswith("kata-analyze"):
                return eng_black.analyze(interval=1.0)
            return eng_black.send(cmd)

        bc.set_gtp_engine(_gtp_callable)

        print(f"\n=== Ban 阶段（{boardsize}路，区域 "
              f"{ban_cfg.region_row_min}-{ban_cfg.region_row_max}，"
              f"共 {ban_cfg.ban_count} 次）===")

        while not bc.is_finished:
            player = bc.current_player
            role = "黑" if player == "B" else "白"
            print(f"\n--- 第 {bc.step + 1}/{ban_cfg.ban_count} 次 ban "
                  f"(选手 {player}/{role}) ---")

            if cfg.mode == "human" and player == human_player:
                # 人类输入
                while True:
                    try:
                        label = input(f"您(选手{player})输入禁点坐标 (如 D7): ").strip()
                    except EOFError:
                        print("\n[输入结束]")
                        return
                    if not label:
                        continue
                    res = bc.submit_label(label)
                    if res.valid:
                        print(f"  已禁: {label}")
                        break
                    print(f"  无效: {res.reason}（违例 {bc.violations[player]}/"
                          f"{ban_cfg.max_violations}），请重试")
            else:
                # AI 选点
                res = bc.submit_ai(cfg.ban_strategy)
                if res.valid and bc.history:
                    last = bc.history[-1]
                    print(f"  AI 禁: {last.label}")
                elif not res.valid:
                    print(f"  AI ban 失败: {res.reason}")
                    if bc.is_finished:
                        break

            print_board({}, bc.banned, (board_rows, board_cols))

        # Ban 结果
        result = bc.get_result()
        ban_labels = sorted(point_to_gtp(r, c) for r, c in result.banned_points)
        print(f"\n[Ban 阶段结束] 结论: {result.concluded_by}")
        print(f"[禁点集合] ({len(ban_labels)} 个): {' '.join(ban_labels)}")

        # 真实注入禁点到两个引擎
        if ban_labels:
            ban_cmd = f"kata-set-bans {' '.join(ban_labels)}"
            try:
                eng_black.send(ban_cmd)
                eng_white.send(ban_cmd)
                print(f"[引擎] kata-set-bans 已注入 {len(ban_labels)} 个禁点")
            except RuntimeError as e:
                print(f"[错误] kata-set-bans 失败: {e}")

        # ═══════════ 正式对局 ═══════════
        print(f"\n=== 正式对局（黑先，komi={cfg.komi}）===")

        engines = {"B": eng_black, "W": eng_white}
        board = ReplayBoard(board_rows, board_cols, set(bc.banned))
        turn = "B"  # 黑先 = 选手 B
        consecutive_pass = 0
        move_no = 0
        resigned_by: Optional[str] = None
        game_moves: list[tuple[str, str]] = []  # (color, gtp_coord or "pass")

        while True:
            if cfg.max_moves and move_no >= cfg.max_moves:
                print(f"\n[达到最大手数 {cfg.max_moves}，停止对局]")
                break

            color_gtp = "black" if turn == "B" else "white"
            role = "黑" if turn == "B" else "白"
            eng = engines[turn]

            if cfg.mode == "human" and turn == human_color:
                # 人类走子
                while True:
                    try:
                        coord = input(f"\n第{move_no+1}手 您({role})落子 "
                                      f"(坐标如 D4 / pass / resign): ").strip()
                    except EOFError:
                        print("\n[输入结束]")
                        return
                    if coord:
                        break
                coord = coord.upper() if coord not in ("pass", "resign") else coord.lower()
            else:
                # AI 走子
                print(f"\n第{move_no+1}手 {role}(AI) 思考中 ...")
                coord = eng.genmove(color_gtp)
                coord_norm = coord.strip().lower()
                print(f"  {role} → {coord}")

            move_no += 1
            coord_norm = coord.strip().lower()

            if coord_norm == "resign":
                resigned_by = turn
                print(f"  {role} 认输")
                break

            game_moves.append((turn, "pass" if coord_norm == "pass" else coord.strip()))

            if coord_norm == "pass":
                consecutive_pass += 1
                print(f"  {role} pass（连续 pass: {consecutive_pass}）")
                if consecutive_pass >= 2:
                    print("  双方连续 pass，终局")
                    break
            else:
                consecutive_pass = 0
                try:
                    row, col = gtp_to_point(coord)
                except (ValueError, IndexError):
                    print(f"  [警告] 无法解析坐标 {coord}，跳过同步")
                    row, col = None, None

                if row is not None:
                    board.play(turn, row, col)
                    # 检测 AI 是否落在禁点上（ENGINE 实装后正常应避开）
                    if (row, col) in bc.banned:
                        print(f"  [异常] {coord} 落在禁点上！"
                              f"（规则 §5：落禁点累计 3 次判负）")
                    # 同步给另一个引擎
                    other_key = "W" if turn == "B" else "B"
                    try:
                        engines[other_key].play(color_gtp, coord)
                    except RuntimeError as e:
                        print(f"  [警告] 同步对手引擎失败: {e}")

                print_board(board.stones, bc.banned, (board_rows, board_cols))

            turn = "W" if turn == "B" else "B"

        # ═══════════ 终局数子 ═══════════
        print(f"\n=== 终局数子 ===")
        game_result = ""
        if resigned_by is not None:
            winner = "W" if resigned_by == "B" else "B"
            game_result = f"{winner}+R"
            print(f"认输结局: {'黑' if winner == 'B' else '白'}(选手"
                  f"{'B' if winner == 'B' else 'A'})胜")
        else:
            try:
                score = eng_black.final_score()
                print(f"引擎 final_score: {score}")
                game_result = score
            except RuntimeError as e:
                print(f"final_score 失败: {e}")
                score = ""
                game_result = ""

            # 20 路公式判定（规则 §4）
            ban_count = len(ban_labels)
            total_pts = boardsize * boardsize
            valid_pts = total_pts - ban_count
            base = valid_pts / 2
            black_threshold = base + cfg.komi    # 黑胜需 > 199.25
            white_threshold = base - cfg.komi    # 白胜需 > 190.75
            print(f"20路公式: 有效点 = {total_pts} - {ban_count} = {valid_pts}，"
                  f"基准 = {base}")
            print(f"  黑胜: 黑子数 > {black_threshold:.2f}")
            print(f"  白胜: 白子数 > {white_threshold:.2f}")
            if score:
                print(f"引擎判定: {score}")

        # ═══════════ SGF 导出 ═══════════
        if not cfg.no_sgf:
            sgf_path = cfg.sgf_out or (
                f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf"
            )
            sgf_game = SgfGame(
                boardsize=boardsize,
                komi=cfg.komi,
                player_b="选手B",
                player_a="选手A",
                date=datetime.date.today().isoformat(),
                bans=sorted(bc.banned),
                moves=game_moves,
                result=game_result,
            )
            try:
                export_sgf(sgf_game, sgf_path)
                print(f"[SGF] 已导出: {sgf_path}")
            except Exception as e:
                print(f"[SGF] 导出失败: {e}")

    finally:
        print("\n[关闭引擎 ...")
        eng_black.close()
        eng_white.close()
        print("[完成]")


# ── SGF 复盘 ────────────────────────────────────────────────────────────────

def review_sgf(path: str) -> None:
    """导入 SGF 并打印棋谱 + 禁点 + 终局棋盘，供复盘。"""
    game = import_sgf(path)

    print(f"=== SGF 复盘: {path} ===")
    print(f"棋盘: {game.boardsize}路 | 贴目: {game.komi} | "
          f"黑: {game.player_b} | 白: {game.player_a} | 日期: {game.date}")
    if game.result:
        print(f"结果: {game.result}")
    if game.boardsize != 20:
        print(f"[提示] 棋盘尺寸 {game.boardsize} 非 20 路（20 路变体标准）")

    ban_set = set(game.bans)
    ban_labels = sorted(point_to_gtp(r, c) for r, c in game.bans)
    print(f"禁点 ({len(ban_labels)} 个): {' '.join(ban_labels) if ban_labels else '无'}")

    print(f"\n手谱 ({len(game.moves)} 手):")
    for i, (color, coord) in enumerate(game.moves):
        role = "黑" if color == "B" else "白"
        print(f"  {i + 1:>3}. {role} {coord}")

    if isinstance(game.boardsize, tuple):
        sgf_rows, sgf_cols = game.boardsize
    else:
        sgf_rows = sgf_cols = game.boardsize
    board = ReplayBoard(sgf_rows, sgf_cols, ban_set)
    for color, coord in game.moves:
        if coord.lower() == "pass":
            continue
        row, col = gtp_to_point(coord)
        board.play(color, row, col)

    print(f"\n终局棋盘:")
    print_board(board.stones, ban_set, game.boardsize)


# ── 命令行入口 ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="20路Ban选围棋 CLI 对弈工具（KataGo 引擎托管）",
    )
    p.add_argument("--mode", choices=["aivai", "human"], default="aivai",
                   help="对局模式：aivai=AI对AI，human=人对AI（默认 aivai）")
    p.add_argument("--color", choices=["B", "W"], default="B",
                   help="human 模式下人类棋色：B=黑先手，W=白后手（默认 B）")
    p.add_argument("--boardsize", default="20",
                   help="棋盘尺寸：int（正方形，默认 20）或 R:C（非正方形，如 15:20）")
    p.add_argument("--engine", default=DEFAULT_ENGINE, help="katago.exe 路径")
    p.add_argument("--model", default=DEFAULT_MODEL, help="权重文件路径")
    p.add_argument("--config", default=DEFAULT_CONFIG, help="GTP 配置文件路径")
    p.add_argument("--extra-config", action="append", default=None,
                   help="附加 GTP 配置（可多次，如 homeDataDir 缓存），覆盖主 config")
    p.add_argument("--ban-strategy", choices=["random", "gtp", "auto"],
                   default="random", help="Ban 阶段 AI 策略（默认 random 保底）")
    p.add_argument("--max-moves", type=int, default=0,
                   help="正式对局最大手数（0=不限，调试时可设小值）")
    p.add_argument("--komi", type=float, default=4.25,
                   help="贴子（默认 4.25，传给引擎 final_score）")
    p.add_argument("--sgf-out", default=None,
                   help="SGF 导出路径（默认自动生成 game_YYYYMMDD_HHMMSS.sgf）")
    p.add_argument("--sgf-in", default=None,
                   help="导入 SGF 复盘（不启动新对局）")
    p.add_argument("--no-sgf", action="store_true",
                   help="不导出 SGF 文件")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # SGF 导入复盘模式（不启动新对局）
    if args.sgf_in:
        try:
            review_sgf(args.sgf_in)
        except FileNotFoundError as e:
            print(f"[错误] {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            raise
        return 0

    # 解析 boardsize：int 或 "R:C"
    bs_str = args.boardsize
    if ":" in bs_str:
        parts = bs_str.split(":")
        boardsize = (int(parts[0]), int(parts[1]))
    else:
        boardsize = int(bs_str)

    cfg = GameConfig(
        mode=args.mode,
        color=args.color,
        boardsize=boardsize,
        engine=args.engine,
        model=args.model,
        config=args.config,
        extra_configs=args.extra_config,
        override_configs=list(DEFAULT_OVERRIDE_CONFIGS),
        ban_strategy=args.ban_strategy,
        max_moves=args.max_moves,
        komi=args.komi,
        sgf_out=args.sgf_out,
        no_sgf=args.no_sgf,
    )

    bs_desc = f"{cfg.board_rows}x{cfg.board_cols}" if isinstance(cfg.boardsize, tuple) else f"{cfg.boardsize}"
    print(f"模式: {cfg.mode} | 棋盘: {bs_desc} | "
          f"ban策略: {cfg.ban_strategy} | komi: {cfg.komi}")
    if cfg.mode == "human":
        print(f"人类: {'黑(先手,选手B)' if cfg.color == 'B' else '白(后手,选手A)'}")

    try:
        run_game(cfg)
    except KeyboardInterrupt:
        print("\n[中断]")
        return 130
    except Exception as e:
        print(f"\n[错误] {e}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
