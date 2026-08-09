# -*- coding: utf-8 -*-
"""
gui.py — 20路Ban选围棋 GUI（tkinter）

职责：
  1. 图形化棋盘（20×20 Canvas）+ Ban 阶段交互 + 正式对局
  2. AI 思考实时显示（kata-analyze 流式 → winrate/visits/PV）
  3. 终局数子 + SGF 导出

线程模型（严格遵循，否则 tkinter 崩溃）：
  - AI 落子：后台线程 eng.genmove() → ai_queue → root.after(100, _poll_ai) 消费
  - AI 思考：后台线程 eng.analyze() → analyze_queue → root.after(200, _poll_analyze) 消费
  - 禁止后台线程直接调 tkinter，所有 UI 更新在主线程 after 回调里

复用模块：
  - cli_player.GtpEngine（subprocess GTP 通信）
  - ban_controller.BanController（Ban 阶段逻辑）
  - sgf_io.SgfGame / export_sgf / import_sgf（SGF 读写）
"""

from __future__ import annotations

import datetime
import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ban_controller import (
    BanConfig,
    BanController,
    col_to_letter,
    gtp_to_point,
    point_to_gtp,
)
from cli_player import (
    COLOR_TO_PLAYER,
    DEFAULT_CONFIG,
    DEFAULT_ENGINE,
    DEFAULT_MODEL,
    DEFAULT_OVERRIDE_CONFIGS,
    PLAYER_TO_COLOR,
    GtpEngine,
)
from sgf_io import SgfGame, export_sgf, import_sgf, point_to_sgf, ReplayBoard
from settings import (
    DEFAULT_SETTINGS,
    PRESETS,
    build_override_configs,
    load_settings,
    save_settings,
    settings_exist,
)

# ── 常量 ────────────────────────────────────────────────────────────────────

BOARD_SIZE = 20

# 状态机
BAN_PHASE = "ban"          # Ban 选阶段
PLAYING = "playing"        # 正式对局
AI_THINKING = "thinking"   # AI 思考中
GAME_OVER = "over"         # 对局结束
MARK_DEAD = "mark_dead"    # 标记死子（人vs人双 pass 后）

# 颜色
BOARD_BG = "#e9c47f"
LINE_COLOR = "#3d2f14"
LABEL_COLOR = "#6b5233"
STONE_BLACK = "#141414"
STONE_WHITE = "#f8f8f8"
STONE_EDGE = "#9a9a9a"
MARK_RED = "#e02424"
HIGHLIGHT = "#4a90d9"

# 20 路星位（0-indexed）：4-4, 4-17, 17-4, 17-17, 天元 10-10
STAR_POINTS_20 = [(3, 3), (3, 16), (16, 3), (16, 16), (9, 9)]

# 列字母（跳 I）：A-H, J-U
COL_LETTERS = "ABCDEFGHJKLMNOPQRSTU"


# ── 设置对话框 ──────────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    """AI 设置对话框（Toplevel）。确定后 self.result 存 settings dict，取消为 None。"""

    def __init__(self, parent, current: dict):
        super().__init__(parent)
        self.title("AI 设置")
        self.resizable(False, False)
        self.transient(parent)
        self.result: dict | None = None
        self._current = dict(current)

        frm = ttk.Frame(self, padding=12)
        frm.grid()

        row = 0

        # AI 水平
        ttk.Label(frm, text="AI 水平").grid(row=row, column=0, sticky="w", pady=3)
        self.v_level = tk.StringVar(value=current.get("level", "业余"))
        cb = ttk.Combobox(frm, textvariable=self.v_level, state="readonly",
                          values=["新手", "业余", "高级", "自定义"], width=12)
        cb.grid(row=row, column=1, sticky="w", pady=3)
        cb.bind("<<ComboboxSelected>>", self._on_preset)
        row += 1

        # maxTime
        ttk.Label(frm, text="思考时间上限（秒）").grid(row=row, column=0, sticky="w", pady=3)
        self.v_time = tk.StringVar(value=str(current.get("maxTime", 10.0)))
        ttk.Entry(frm, textvariable=self.v_time, width=12).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # maxVisits
        ttk.Label(frm, text="思考深度上限（visits）").grid(row=row, column=0, sticky="w", pady=3)
        self.v_visits = tk.StringVar(value=str(current.get("maxVisits", 800)))
        ttk.Entry(frm, textvariable=self.v_visits, width=12).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # numSearchThreads
        ttk.Label(frm, text="搜索线程数").grid(row=row, column=0, sticky="w", pady=3)
        self.v_threads = tk.StringVar(value=str(current.get("numSearchThreads", 6)))
        ttk.Entry(frm, textvariable=self.v_threads, width=12).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # ponderingEnabled
        self.v_ponder = tk.BooleanVar(value=bool(current.get("ponderingEnabled", False)))
        ttk.Checkbutton(frm, text="后台思考（开启会占 GPU 可能卡顿）",
                        variable=self.v_ponder).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 权重文件
        ttk.Label(frm, text="权重文件").grid(row=row, column=0, sticky="w", pady=3)
        path_frm = ttk.Frame(frm)
        path_frm.grid(row=row, column=1, sticky="w", pady=3)
        self.v_model = tk.StringVar(value=current.get("model_path", DEFAULT_MODEL))
        ttk.Entry(path_frm, textvariable=self.v_model, width=28).pack(side="left")
        ttk.Button(path_frm, text="浏览", command=self._browse, width=6).pack(side="left", padx=4)
        row += 1

        # 棋盘行数
        ttk.Label(frm, text="棋盘行数（9-25）").grid(row=row, column=0, sticky="w", pady=3)
        self.v_rows = tk.IntVar(value=int(current.get("board_rows", 20)))
        ttk.Spinbox(frm, from_=9, to=25, textvariable=self.v_rows, width=10).grid(
            row=row, column=1, sticky="w", pady=3)
        row += 1

        # 棋盘列数
        ttk.Label(frm, text="棋盘列数（9-25）").grid(row=row, column=0, sticky="w", pady=3)
        self.v_cols = tk.IntVar(value=int(current.get("board_cols", 20)))
        ttk.Spinbox(frm, from_=9, to=25, textvariable=self.v_cols, width=10).grid(
            row=row, column=1, sticky="w", pady=3)
        row += 1

        # 对局模式
        ttk.Label(frm, text="对局模式").grid(row=row, column=0, sticky="w", pady=3)
        self.v_mode = tk.StringVar(value=current.get("game_mode", "人vsAI"))
        ttk.Combobox(frm, textvariable=self.v_mode, state="readonly",
                     values=["人vsAI", "AIvsAI", "人vs人"], width=10).grid(
            row=row, column=1, sticky="w", pady=3)
        row += 1

        # 按钮
        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=2, pady=(10, 0), sticky="w")
        ttk.Button(btns, text="确定", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self._cancel).pack(side="left", padx=4)
        row += 1
        ttk.Label(frm, text="改设置后需开始新对局才生效（重启引擎）。",
                  foreground="#888").grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.grab_set()
        self.wait_window()

    def _on_preset(self, _event=None):
        level = self.v_level.get()
        if level in PRESETS:
            p = PRESETS[level]
            self.v_time.set(str(p["maxTime"]))
            self.v_visits.set(str(p["maxVisits"]))
            self.v_threads.set(str(p["numSearchThreads"]))

    def _browse(self):
        path = filedialog.askopenfilename(
            title="选择权重文件",
            filetypes=[("KataGo 权重", "*.bin.gz *.bin"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(self.v_model.get()) or ".",
        )
        if path:
            self.v_model.set(path)

    def _ok(self):
        try:
            visits = int(self.v_visits.get())
            t = float(self.v_time.get())
            threads = int(self.v_threads.get())
            rows = int(self.v_rows.get())
            cols = int(self.v_cols.get())
        except ValueError:
            messagebox.showerror("设置", "数值格式错误，请检查", parent=self)
            return
        if not (9 <= rows <= 25) or not (9 <= cols <= 25):
            messagebox.showwarning("设置", "棋盘行列数必须在 9-25 之间", parent=self)
            return
        model = self.v_model.get().strip()
        if not os.path.isfile(model):
            messagebox.showwarning("设置", f"权重文件不存在：\n{model}", parent=self)
            return
        self.result = {
            "level": self.v_level.get(),
            "maxVisits": visits,
            "maxTime": t,
            "numSearchThreads": threads,
            "ponderingEnabled": bool(self.v_ponder.get()),
            "model_path": model,
            "board_rows": rows,
            "board_cols": cols,
            "game_mode": self.v_mode.get(),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ── 主应用 ──────────────────────────────────────────────────────────────────

class BanGoApp:
    """20路Ban选围棋 GUI 主应用。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("20路Ban选围棋")
        root.resizable(False, False)

        # 设置
        self.settings = load_settings()
        _first_launch = not settings_exist()

        # 棋盘尺寸（从 settings 读，支持非正方形）
        self.rows = self.settings.get("board_rows", 20)
        self.cols = self.settings.get("board_cols", 20)
        self.cell = 28
        self.margin = 36
        self.px_x = 2 * self.margin + self.cell * (self.cols - 1)
        self.px_y = 2 * self.margin + self.cell * (self.rows - 1)

        # 游戏状态
        self.state = BAN_PHASE
        self.board = ReplayBoard(self.rows, self.cols, set())  # 带提子的影子棋盘（1-based）
        self.dead_stones: set[tuple[int, int]] = set()  # 标记的死子（1-based，人vs人终局用）
        self.last_stone: tuple[int, int] | None = None
        self.game_moves: list[tuple[str, str]] = []   # (color, gtp_coord or "pass")
        self.passes = 0
        self.resigned_by: str | None = None
        self.game_result = ""
        self._paused = False  # AIvsAI 暂停

        # 棋色：人=黑(B先手)，AI=白(W后手)（MVP 固定，后续可配置）
        self.human_color = "B"
        self.ai_color = "W"
        self.human_player = COLOR_TO_PLAYER[self.human_color]  # 选手 B
        self.ai_player = COLOR_TO_PLAYER[self.ai_color]         # 选手 A

        # Ban 控制器（region 默认全棋盘）
        self.ban_cfg = BanConfig(board_size=self.rows, board_cols=self.cols)
        self.bc = BanController(self.ban_cfg)

        # 引擎
        self.eng: GtpEngine | None = None
        self._eng_ready = False

        # 线程通信队列
        self.ai_queue: queue.Queue = queue.Queue()
        self.analyze_queue: queue.Queue = queue.Queue()
        self.gen = 0  # 代数（防过期回调）

        # 鼠标悬停
        self._hover_id = None

        # 构建 UI
        self._build_menu()
        self._build_ui()

        # 启动轮询
        self.root.after(100, self._poll_ai)
        self.root.after(200, self._poll_analyze)

        # 首次启动弹设置对话框
        if _first_launch:
            self._open_settings(first_launch=True)
        else:
            self._start_engine()

        # 关闭处理
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="设置", command=self._open_settings)
        m_file.add_command(label="新对局", command=self.new_game)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=m_file)
        self.root.config(menu=menubar)

    def _build_ui(self):
        # 顶部状态栏
        top = tk.Frame(self.root)
        top.pack(side="top", fill="x")
        self.lbl_status = tk.Label(
            top, text="正在加载引擎...", anchor="w",
            font=("Microsoft YaHei", 10), padx=8, pady=4,
        )
        self.lbl_status.pack(fill="x")

        # 主体：左棋盘 + 右侧栏
        main_frame = tk.Frame(self.root)
        main_frame.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        # 棋盘 Canvas
        self.canvas = tk.Canvas(
            main_frame, width=self.px_x, height=self.px_y,
            highlightthickness=0, cursor="hand2", bg=BOARD_BG,
        )
        self.canvas.pack(side="left", padx=4, pady=4)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", lambda e: self._clear_hover())

        # 右侧栏
        side = tk.Frame(main_frame, width=260)
        side.pack(side="right", fill="y", padx=4, pady=4)
        side.pack_propagate(False)

        # AI 思考显示
        tk.Label(side, text="AI 思考", font=("Microsoft YaHei", 11, "bold"),
                 anchor="w").pack(fill="x", pady=(8, 4))
        self.lbl_winrate = tk.Label(side, text="胜率: --", anchor="w",
                                    font=("Consolas", 10))
        self.lbl_winrate.pack(fill="x")
        self.lbl_visits = tk.Label(side, text="访问: --", anchor="w",
                                   font=("Consolas", 10))
        self.lbl_visits.pack(fill="x")
        self.lbl_pv = tk.Label(side, text="PV: --", anchor="w",
                               font=("Consolas", 10), wraplength=240,
                               justify="left")
        self.lbl_pv.pack(fill="x")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=8)

        # 禁点列表
        tk.Label(side, text="禁点", font=("Microsoft YaHei", 11, "bold"),
                 anchor="w").pack(fill="x")
        self.lbl_bans = tk.Label(side, text="（Ban 阶段未开始）", anchor="w",
                                 font=("Microsoft YaHei", 9), wraplength=240,
                                 justify="left", fg="#666")
        self.lbl_bans.pack(fill="x")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=8)

        # 按钮
        btn_frame = tk.Frame(side)
        btn_frame.pack(fill="x", pady=4)
        self.buttons: dict[str, tk.Button] = {}
        for text, cmd in [
            ("Pass", self.human_pass),
            ("认输", self.human_resign),
            ("暂停/继续", self._toggle_pause),
            ("确认数子", self._confirm_dead),
            ("导出 SGF", self.export_sgf),
            ("新对局", self.new_game),
        ]:
            b = tk.Button(btn_frame, text=text, command=cmd,
                          font=("Microsoft YaHei", 10), padx=6, pady=3)
            b.pack(fill="x", pady=2)
            self.buttons[text] = b

        # 底部日志
        log_frame = tk.Frame(self.root)
        log_frame.pack(side="bottom", fill="x", padx=4, pady=2)
        self.log_text = tk.Text(log_frame, height=3, wrap="word",
                                font=("Consolas", 8), state="disabled",
                                bg="#f5f5f5")
        self.log_text.pack(fill="x")

        self.draw_board()
        self._update_buttons()

    # ── 棋盘绘制 ──

    def draw_board(self):
        cv = self.canvas
        cv.delete("all")
        cv.configure(bg=BOARD_BG)
        rows, cols_n = self.rows, self.cols
        cell, m = self.cell, self.margin
        px_x = self.px_x  # 水平像素宽
        px_y = self.px_y  # 垂直像素高

        # 禁点 Canvas 坐标集合（bc.banned 是 1-based (row,col)，转 Canvas r=rows-row1, c=col1-1）
        banned_cv = {(self.rows - r1, c1 - 1) for (r1, c1) in self.bc.banned}

        # 网格线逐段画：涉及禁点的线段跳过（禁点 = 消去连线）
        # 横向线段 (r,c)→(r,c+1)
        for r in range(rows):
            for c in range(cols_n - 1):
                if (r, c) in banned_cv or (r, c + 1) in banned_cv:
                    continue
                y = m + r * cell
                cv.create_line(m + c * cell, y, m + (c + 1) * cell, y, fill=LINE_COLOR)
        # 纵向线段 (r,c)→(r+1,c)
        for r in range(rows - 1):
            for c in range(cols_n):
                if (r, c) in banned_cv or (r + 1, c) in banned_cv:
                    continue
                x = m + c * cell
                cv.create_line(x, m + r * cell, x, m + (r + 1) * cell, fill=LINE_COLOR)

        # 星位（正方形用预定义，非正方形只画天元）—— 跳过禁点
        if rows == cols_n:
            for r, c in STAR_POINTS_20:
                if r < rows and c < cols_n and (r, c) not in banned_cv:
                    x, y = m + c * cell, m + r * cell
                    cv.create_oval(x - 3, y - 3, x + 3, y + 3,
                                   fill=LINE_COLOR, outline="")
        else:
            r, c = rows // 2, cols_n // 2
            if (r, c) not in banned_cv:
                x, y = m + c * cell, m + r * cell
                cv.create_oval(x - 3, y - 3, x + 3, y + 3,
                               fill=LINE_COLOR, outline="")

        # 坐标标签
        for i, ch in enumerate(COL_LETTERS[:cols_n]):
            x = m + i * cell
            cv.create_text(x, 14, text=ch, fill=LABEL_COLOR,
                           font=("Microsoft YaHei", 8))
            cv.create_text(x, px_y - 10, text=ch, fill=LABEL_COLOR,
                           font=("Microsoft YaHei", 8))
        for i in range(rows):
            y = m + i * cell
            row_label = str(rows - i)
            cv.create_text(12, y, text=row_label, fill=LABEL_COLOR,
                           font=("Microsoft YaHei", 8))
            cv.create_text(px_x - 10, y, text=row_label, fill=LABEL_COLOR,
                           font=("Microsoft YaHei", 8))

        # 棋子（self.board.stones 为 1-based (row,col)，转 Canvas 绘制）
        for (row1, col1), color in self.board.stones.items():
            r = self.rows - row1
            c = col1 - 1
            self._draw_stone(r, c, color)

        # 最后一手标记
        if self.last_stone:
            r, c = self.last_stone
            x, y = m + c * cell, m + r * cell
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=MARK_RED, outline="")

        # 死子标记（标记死子模式下，红色 X 叠在棋子上）
        if self.state == MARK_DEAD:
            for (row1, col1) in self.dead_stones:
                r = self.rows - row1
                c = col1 - 1
                x, y = m + c * cell, m + r * cell
                d = cell * 0.3
                cv.create_line(x - d, y - d, x + d, y + d, fill=MARK_RED, width=2)
                cv.create_line(x - d, y + d, x + d, y - d, fill=MARK_RED, width=2)

        self._update_ban_label()

    def _draw_stone(self, r: int, c: int, color: str):
        cv = self.canvas
        x = self.margin + c * self.cell
        y = self.margin + r * self.cell
        rad = self.cell * 0.46
        if color == "B":
            cv.create_oval(x - rad, y - rad, x + rad, y + rad,
                           fill=STONE_BLACK, outline="#000")
        else:
            cv.create_oval(x - rad, y - rad, x + rad, y + rad,
                           fill=STONE_WHITE, outline=STONE_EDGE)

    def _draw_ban(self, r: int, c: int):
        # 已废弃：禁点改用"消去连线"表示，见 draw_board 网格线逐段画法
        pass

    def _clear_hover(self):
        if self._hover_id is not None:
            self.canvas.delete(self._hover_id)
            self._hover_id = None

    def on_hover(self, event):
        self._clear_hover()
        pos = self._event_to_pos(event)
        if pos is None:
            return
        r, c = pos
        x = self.margin + c * self.cell
        y = self.margin + r * self.cell
        rad = self.cell * 0.46
        self._hover_id = self.canvas.create_oval(
            x - rad, y - rad, x + rad, y + rad,
            outline=HIGHLIGHT, width=2,
        )

    # ── 坐标转换 ──

    def _event_to_pos(self, event) -> tuple[int, int] | None:
        c = round((event.x - self.margin) / self.cell)
        r = round((event.y - self.margin) / self.cell)
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return None
        dx = (event.x - self.margin) - c * self.cell
        dy = (event.y - self.margin) - r * self.cell
        if abs(dx) <= self.cell * 0.4 and abs(dy) <= self.cell * 0.4:
            return r, c
        return None

    def _pos_to_gtp(self, r: int, c: int) -> str:
        """Canvas (r=0..rows-1, c=0..cols-1) → GTP 坐标。
        Canvas r=0 是顶部（行 rows），r=rows-1 是底部（行 1）。
        ban_controller 用 1-based (row, col)，row=1 是底部。
        """
        row_1based = self.rows - r      # Canvas r=0 → row=rows
        col_1based = c + 1              # Canvas c=0 → col=1
        return point_to_gtp(row_1based, col_1based)

    def _canvas_to_1based(self, r: int, c: int) -> tuple[int, int]:
        """Canvas (r=0..rows-1, c=0..cols-1) → 1-based (row, col)。"""
        return (self.rows - r, c + 1)

    def _gtp_to_pos(self, gtp: str) -> tuple[int, int]:
        """GTP 坐标 → Canvas (r, c)。"""
        row_1based, col_1based = gtp_to_point(gtp)
        r = self.rows - row_1based
        c = col_1based - 1
        return r, c

    # ── 引擎启动 ──

    def _start_engine(self):
        self._eng_ready = False
        self.lbl_status.config(text="正在加载引擎...（首次启动可能需 1-2 分钟）")
        s = self.settings
        model = s.get("model_path", DEFAULT_MODEL)
        override = list(DEFAULT_OVERRIDE_CONFIGS) + build_override_configs(s)
        # 非正方形时传 tuple
        bs = (self.rows, self.cols) if self.rows != self.cols else self.rows

        def worker():
            try:
                self.eng = GtpEngine(
                    DEFAULT_ENGINE, model, DEFAULT_CONFIG,
                    boardsize=bs, color=self.ai_color,
                    stderr_path="engine_gui.log",
                    extra_configs=["gtp_override.cfg"],
                    override_configs=override,
                )
                komi = self.eng.send("get_komi").strip()
                self._eng_ready = True
                self.ai_queue.put(("engine_ready", komi))
            except Exception as e:
                self.ai_queue.put(("engine_error", str(e)))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_engine_ready(self, komi: str):
        self.log(f"引擎就绪，komi={komi}")
        self.update_status()
        # 如果 Ban 阶段 AI 先手（序列第一个是 A=白=AI），自动触发
        self._maybe_ai_ban()

    def _on_engine_error(self, err: str):
        self.lbl_status.config(text=f"引擎启动失败: {err}")
        messagebox.showerror("引擎错误",
                             f"无法启动 KataGo 引擎:\n{err}\n\n"
                             f"请确保 dist_opencl\\katago.exe 存在。")

    def _open_settings(self, first_launch: bool = False):
        dlg = SettingsDialog(self.root, self.settings)
        if dlg.result is None:
            if first_launch:
                self.lbl_status.config(text="未配置设置，使用默认配置启动引擎...")
                self._start_engine()
            return
        self.settings = dlg.result
        save_settings(self.settings)
        self.log(f"设置已保存：{self.settings['level']} "
                 f"visits={self.settings['maxVisits']} "
                 f"time={self.settings['maxTime']}s")
        if first_launch:
            self._start_engine()
        else:
            if messagebox.askyesno("设置", "新设置将在下一局生效。\n是否立即开始新对局？"):
                self._restart_engine()

    def _restart_engine(self):
        """关闭当前引擎，用当前 settings 重新启动，重置对局。"""
        self.gen += 1  # 使所有过期回调失效
        self._eng_ready = False
        if self.eng:
            self.eng.close()
            self.eng = None
        # 从 settings 重读棋盘尺寸（可能改了行列）
        self.rows = self.settings.get("board_rows", 20)
        self.cols = self.settings.get("board_cols", 20)
        self.px_x = 2 * self.margin + self.cell * (self.cols - 1)
        self.px_y = 2 * self.margin + self.cell * (self.rows - 1)
        self.canvas.config(width=self.px_x, height=self.px_y)
        # 重置对局状态
        self.board = ReplayBoard(self.rows, self.cols, set())
        self.dead_stones = set()
        self.game_moves.clear()
        self.last_stone = None
        self.passes = 0
        self.resigned_by = None
        self.game_result = ""
        self._paused = False
        self.ban_cfg = BanConfig(board_size=self.rows, board_cols=self.cols)
        self.bc = BanController(self.ban_cfg)
        self.state = BAN_PHASE
        # 清空侧栏
        self.lbl_winrate.config(text="胜率: --")
        self.lbl_visits.config(text="访问: --")
        self.lbl_pv.config(text="PV: --")
        self.draw_board()
        self._update_buttons()
        self._start_engine()

    # ── Ban 阶段 ──

    def on_click(self, event):
        if not self._eng_ready:
            return
        if self._is_ai_vs_ai():
            return  # AIvsAI 模式不接受点击
        pos = self._event_to_pos(event)
        if pos is None:
            return
        r, c = pos

        if self.state == BAN_PHASE:
            self._on_ban_click(r, c)
        elif self.state == PLAYING:
            self._on_play_click(r, c)
        elif self.state == MARK_DEAD:
            self._on_dead_click(r, c)

    def _on_ban_click(self, r: int, c: int):
        if self.bc.is_finished:
            return
        if not self._is_human_vs_human() and self.bc.current_player != self.human_player:
            self.flash_status("当前轮到 AI 选禁点...")
            return

        gtp = self._pos_to_gtp(r, c)
        res = self.bc.submit_label(gtp)
        if res.valid:
            self.log(f"Ban #{self.bc.step}: 人类禁 {gtp}")
            self.draw_board()
            self.update_status()
            self._maybe_ai_ban()
        else:
            v = self.bc.violations.get(self.bc.current_player, 0)
            messagebox.showwarning("禁点无效",
                                   f"{res.reason}\n违例 {v}/{self.ban_cfg.max_violations}")
            if self.bc.is_finished:
                self._on_ban_finished()

    def _maybe_ai_ban(self):
        if self.bc.is_finished:
            self._on_ban_finished()
            return
        # AIvsAI: 两选手都 AI；人vsAI: 仅 ai_player 是 AI；人vs人: 都是人
        is_ai_turn = not self._is_human_vs_human() and (
            self._is_ai_vs_ai() or self.bc.current_player == self.ai_player)
        if is_ai_turn and not self._paused:
            self.state = AI_THINKING
            self.update_status()
            gen = self.gen
            # AIvsAI 模式延迟 0.3s 便于观察
            delay = 300 if self._is_ai_vs_ai() else 0
            self.root.after(delay, lambda: self._start_ban_worker(gen))

    def _start_ban_worker(self, gen: int):
        if self._paused or self.bc.is_finished:
            return
        t = threading.Thread(target=self._ban_ai_worker, args=(gen,), daemon=True)
        t.start()

    def _ban_ai_worker(self, gen: int):
        try:
            res = self.bc.submit_ai("random")
            last = self.bc.history[-1] if self.bc.history else None
            label = last.label if last else "?"
            self.ai_queue.put(("ban", gen, res.valid, label))
        except Exception as e:
            self.ai_queue.put(("ban_error", gen, str(e)))

    def _on_ban_finished(self):
        result = self.bc.get_result()
        ban_labels = sorted(point_to_gtp(r, c) for r, c in result.banned_points)
        self.log(f"Ban 结束: {' '.join(ban_labels)}")

        # 真实注入引擎
        if ban_labels and self.eng:
            try:
                self.eng.send(f"kata-set-bans {' '.join(ban_labels)}")
                self.log("kata-set-bans 已注入引擎")
            except RuntimeError as e:
                self.log(f"kata-set-bans 失败: {e}")

        # 重建影子棋盘（注入禁点，使提子时禁点不计气）
        self.board = ReplayBoard(self.rows, self.cols, set(result.banned_points))

        self.state = PLAYING
        self.draw_board()
        self.update_status()

        # AIvsAI: 黑先，自动开始第一手
        # 人vsAI: 人是黑(B)先手，等人落子
        if self._is_ai_vs_ai():
            self.root.after(500, self._ai_move_async)

    # ── 正式对局 ──

    def _on_play_click(self, r: int, c: int):
        if self.state != PLAYING:
            return

        # 判断当前轮谁
        turn = self._whose_turn()
        if not self._is_human_vs_human() and turn != self.human_color:
            self.flash_status("当前轮到 AI 落子...")
            return

        gtp = self._pos_to_gtp(r, c)

        # GUI 侧预校验：非禁点、非已有子
        row_1, col_1 = gtp_to_point(gtp)
        if (row_1, col_1) in self.bc.banned:
            messagebox.showwarning("落子无效", f"{gtp} 是禁点，不可落子")
            return
        if (row_1, col_1) in self.board.stones:
            messagebox.showwarning("落子无效", f"{gtp} 已有棋子")
            return

        # 人类落子（turn 在人vsAI 时等于 human_color；人vs人 时为实际轮次）
        self._do_move(turn, gtp)
        # AI 应手（人vs人 不启动 AI）
        if not self._is_human_vs_human():
            self._ai_move_async()

    def _on_dead_click(self, r: int, c: int):
        """标记死子模式下：点击棋子切换死子标记，点击空点忽略。"""
        row_1, col_1 = self._canvas_to_1based(r, c)
        if (row_1, col_1) in self.board.stones:
            if (row_1, col_1) in self.dead_stones:
                self.dead_stones.discard((row_1, col_1))
            else:
                self.dead_stones.add((row_1, col_1))
            self.draw_board()
            self.update_status()

    def _whose_turn(self) -> str:
        """当前轮到谁落子。黑先。"""
        if not self.game_moves:
            return "B"
        last_color = self.game_moves[-1][0]
        return "W" if last_color == "B" else "B"

    def _do_move(self, color: str, gtp: str):
        """执行一步落子（GUI 侧 + 引擎侧同步）。"""
        self.game_moves.append((color, gtp))
        if gtp.lower() != "pass":
            r, c = self._gtp_to_pos(gtp)
            row_1, col_1 = gtp_to_point(gtp)
            self.board.play(color, row_1, col_1)
            self.last_stone = (r, c)
            # 同步到引擎（人类落子通知 AI 引擎）
            color_gtp = "black" if color == "B" else "white"
            if self.eng:
                try:
                    self.eng.play(color_gtp, gtp)
                except RuntimeError as e:
                    self.log(f"play 同步失败: {e}")
        self.passes = 0
        self.draw_board()
        self.update_status()

    def _ai_move_async(self):
        # AIvsAI 模式下需根据当前轮次决定 genmove 颜色；人vsAI 模式只 AI 色
        if self._is_ai_vs_ai():
            turn = self._whose_turn()
        else:
            turn = self.ai_color
            if turn != self.ai_color:
                return
        self.state = AI_THINKING
        self.gen += 1
        gen = self.gen
        self.update_status()

        color_gtp = "black" if turn == "B" else "white"
        max_t = self.settings.get("maxTime", 10.0)
        timeout = max_t + 30  # 引擎 maxTime + 缓冲

        def worker():
            try:
                result = self.eng.send(f"genmove {color_gtp}", timeout=timeout).strip()
                self.ai_queue.put(("move", gen, turn, result))
            except Exception as e:
                self.ai_queue.put(("error", gen, str(e)))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _analyze_worker(self, gen: int, stop: threading.Event):
        """后台循环调用 analyze，将 info 行放入 analyze_queue。（当前未启用）"""
        while not stop.is_set() and self.eng:
            try:
                info = self.eng.analyze(interval=0.5)
                if info:
                    self.analyze_queue.put(("analyze", gen, info))
            except Exception:
                break

    def _is_ai_vs_ai(self) -> bool:
        return self.settings.get("game_mode", "人vsAI") == "AIvsAI"

    def _is_human_vs_human(self) -> bool:
        return self.settings.get("game_mode", "人vsAI") == "人vs人"

    def human_pass(self):
        if self.state != PLAYING:
            return
        turn = self._whose_turn()
        if not self._is_human_vs_human() and turn != self.human_color:
            return
        self.game_moves.append((turn, "pass"))
        self.passes += 1
        self.log(f"{turn} pass")
        if self.passes >= 2:
            if self._is_human_vs_human():
                self.state = MARK_DEAD
                self.dead_stones = set()
                self.log("双方 pass，进入标记死子模式")
                self.update_status()
                self._update_buttons()
                self.draw_board()
            else:
                self._end_game("pass")
            return
        self.update_status()
        if not self._is_human_vs_human():
            self._ai_move_async()

    def human_resign(self):
        if self.state not in (PLAYING, AI_THINKING):
            return
        if not messagebox.askyesno("认输", "确认认输？"):
            return
        # 人vs人：当前轮次者认输；人vsAI：人类认输
        self.resigned_by = self._whose_turn() if self._is_human_vs_human() else self.human_color
        self._end_game("resign")

    def _toggle_pause(self):
        """AIvsAI 模式下暂停/继续自动落子。"""
        if not self._is_ai_vs_ai():
            return
        self._paused = not self._paused
        if self._paused:
            self.log("已暂停")
            self.flash_status("已暂停（AIvsAI）")
        else:
            self.log("继续")
            self.update_status()
            # 若当前该 AI 走且处于 PLAYING，恢复自动落子
            if self.state == PLAYING:
                self.root.after(300, self._ai_move_async)
            elif self.state == BAN_PHASE and not self.bc.is_finished:
                self.root.after(300, self._maybe_ai_ban)

    # ── 终局 ──

    def _end_game(self, reason: str):
        self.state = GAME_OVER
        self.gen += 1  # 使过期的 analyze 回调失效

        if reason == "resign":
            winner = "W" if self.resigned_by == "B" else "B"
            self.game_result = f"{winner}+R"
        else:
            try:
                score = self.eng.final_score()
                self.game_result = score
            except RuntimeError as e:
                self.log(f"final_score 失败: {e}")
                self.game_result = ""

        # 显示结果
        ban_count = len(self.bc.banned)
        valid_pts = self.rows * self.cols - ban_count
        base = valid_pts / 2
        msg = f"对局结束\n\n结果: {self.game_result}\n\n"
        msg += f"20路公式: 有效点 {valid_pts}，基准 {base}\n"
        msg += f"黑胜: > {base + 4.25:.2f}  白胜: > {base - 4.25:.2f}"
        messagebox.showinfo("终局", msg)

        # 自动导出 SGF
        self._export_sgf_internal()
        self.update_status()
        self._update_buttons()

    def _confirm_dead(self):
        """确认死子标记，UI 层数子（人vs人，不依赖引擎）。"""
        from scoring import score_game
        result = score_game(
            dict(self.board.stones), set(self.bc.banned),
            self.rows, self.cols, 4.25, set(self.dead_stones)
        )
        self.game_result = result["result"] if result["winner"] else "Draw"
        self._end_game_ui_scoring(result)

    def _end_game_ui_scoring(self, result):
        """人vs人 UI 层数子结果展示（不调引擎 final_score）。"""
        self.state = GAME_OVER
        self.gen += 1
        d = result["detail"]
        msg = f"对局结束\n\n结果: {result['result']}\n\n"
        msg += f"黑区: {result['black_area']}（活子 {d['black_stones']} + 独占空 {d['black_territory']}）\n"
        msg += f"白区: {result['white_area']}（活子 {d['white_stones']} + 独占空 {d['white_territory']}）\n"
        msg += f"中性空: {result['neutral']}  死子: {d['dead']}\n"
        msg += f"有效点 {result['valid_points']}，基准 {result['half']}\n"
        msg += f"黑胜: > {result['black_win_threshold']:.2f}  白胜: > {result['white_win_threshold']:.2f}"
        messagebox.showinfo("终局", msg)
        self._export_sgf_internal()
        self.update_status()
        self._update_buttons()

    # ── SGF ──

    def _export_sgf_internal(self) -> str:
        sgf_path = f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf"
        sgf_game = SgfGame(
            boardsize=self.rows,  # SGF SZ 用行数（非正方形 SGF 暂用 rows）
            komi=4.25,
            player_b="选手B",
            player_a="选手A",
            date=datetime.date.today().isoformat(),
            bans=sorted(self.bc.banned),
            moves=self.game_moves,
            result=self.game_result,
        )
        try:
            export_sgf(sgf_game, sgf_path)
            self.log(f"SGF 已导出: {sgf_path}")
        except Exception as e:
            self.log(f"SGF 导出失败: {e}")
        return sgf_path

    def export_sgf(self):
        if not self.game_moves and not self.bc.banned:
            messagebox.showinfo("导出", "尚无对局数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".sgf",
            filetypes=[("SGF 棋谱", "*.sgf"), ("所有文件", "*.*")],
            initialfile=f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf",
        )
        if not path:
            return
        sgf_game = SgfGame(
            boardsize=self.rows,
            komi=4.25,
            player_b="选手B",
            player_a="选手A",
            date=datetime.date.today().isoformat(),
            bans=sorted(self.bc.banned),
            moves=self.game_moves,
            result=self.game_result,
        )
        try:
            export_sgf(sgf_game, path)
            messagebox.showinfo("导出", f"已导出: {path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ── 新对局 ──

    def new_game(self):
        if self.state == AI_THINKING:
            return
        self.gen += 1
        self.board = ReplayBoard(self.rows, self.cols, set())
        self.dead_stones = set()
        self.game_moves.clear()
        self.last_stone = None
        self.passes = 0
        self.resigned_by = None
        self.game_result = ""
        self.bc = BanController(self.ban_cfg)
        self.state = BAN_PHASE

        # 重置引擎棋盘
        if self.eng:
            try:
                self.eng.send("clear_board")
                self.eng.send("kata-clear-bans")
            except RuntimeError:
                pass

        self.draw_board()
        self.update_status()
        self._update_buttons()
        self._maybe_ai_ban()

    # ── 队列轮询 ──

    def _poll_ai(self):
        while True:
            try:
                msg = self.ai_queue.get_nowait()
            except queue.Empty:
                break
            self._on_ai_msg(msg)
        self.root.after(100, self._poll_ai)

    def _on_ai_msg(self, msg: tuple):
        kind = msg[0]

        if kind == "engine_ready":
            komi = msg[1]
            self.log(f"引擎就绪，komi={komi}")
            self.update_status()
            self._maybe_ai_ban()
            return

        if kind == "engine_error":
            self._on_engine_error(msg[1])
            return

        gen = msg[1]

        if gen != self.gen:
            return  # 过期回调

        if kind == "ban":
            valid = msg[2]
            label = msg[3]
            if valid:
                self.log(f"Ban #{self.bc.step}: AI 禁 {label}")
                self.draw_board()
                self.update_status()
                self.state = BAN_PHASE if not self.bc.is_finished else self.state
                if self.bc.is_finished:
                    self._on_ban_finished()
                else:
                    self._maybe_ai_ban()
            else:
                self.log(f"AI ban 失败")
                if self.bc.is_finished:
                    self._on_ban_finished()

        elif kind == "ban_error":
            self.log(f"AI ban 出错: {msg[2]}")

        elif kind == "move":
            move_color = msg[2]
            result = msg[3].strip()
            self._on_ai_move(move_color, result)

        elif kind == "error":
            self.state = PLAYING
            self.update_status()
            self.flash_status(f"AI 出错: {msg[2][:100]}")

    def _on_ai_move(self, move_color: str, result: str):
        result = result.strip()
        if not result:
            self.state = PLAYING
            self.update_status()
            self.flash_status("AI 返回空响应，请重试")
            return
        result_lower = result.lower()
        if result_lower == "resign":
            self.resigned_by = move_color
            self._end_game("resign")
            return

        if result_lower == "pass":
            self.game_moves.append((move_color, "pass"))
            self.passes += 1
            self.log(f"{move_color} pass")
            if self.passes >= 2:
                self._end_game("pass")
                return
        else:
            self.game_moves.append((move_color, result))
            r, c = self._gtp_to_pos(result)
            row_1, col_1 = gtp_to_point(result)
            self.board.play(move_color, row_1, col_1)
            self.last_stone = (r, c)
            self.passes = 0
            self.log(f"{move_color} 落子: {result}")

        self.state = PLAYING
        self.draw_board()
        self.update_status()
        self._update_buttons()

        # AIvsAI: 调度下一手（0.5s 延迟便于观察）
        if self._is_ai_vs_ai() and not self._paused and self.state == PLAYING:
            self.root.after(500, self._ai_move_async)

    def _poll_analyze(self):
        while True:
            try:
                msg = self.analyze_queue.get_nowait()
            except queue.Empty:
                break
            self._on_analyze(msg)
        self.root.after(200, self._poll_analyze)

    def _on_analyze(self, msg: tuple):
        kind = msg[0]
        if kind != "analyze":
            return
        gen = msg[1]
        info_text = msg[2]
        if gen != self.gen:
            return

        # 解析 info 行
        for line in info_text.splitlines():
            line = line.strip()
            if not line.startswith("info "):
                continue
            winrate = self._extract_field(line, "winrate")
            visits = self._extract_field(line, "visits")
            pv = self._extract_pv(line)
            if winrate:
                wr = float(winrate) / 100.0
                self.lbl_winrate.config(text=f"胜率: {wr:.1%}")
            if visits:
                self.lbl_visits.config(text=f"访问: {int(visits):,}")
            if pv:
                self.lbl_pv.config(text=f"PV: {pv}")
            break  # 只取第一行 info

    @staticmethod
    def _extract_field(line: str, field: str) -> str | None:
        m = re.search(rf"\b{field}\s+(\S+)", line)
        return m.group(1) if m else None

    @staticmethod
    def _extract_pv(line: str) -> str:
        m = re.search(r"\bpv\s+(.+?)(?:\b(?:move|visits|winrate|scoreLead|prior|lcb|utility|order|pv)\s|\s*$)", line)
        if m:
            return m.group(1).strip()
        m = re.search(r"\bpv\s+(.+)", line)
        return m.group(1).strip() if m else ""

    # ── 状态更新 ──

    def update_status(self):
        if not self._eng_ready:
            self.lbl_status.config(text="正在加载引擎...（首次启动可能需 1-2 分钟）")
            return

        if self.state == BAN_PHASE:
            if self.bc.is_finished:
                self.lbl_status.config(text="Ban 阶段结束，正式对局开始")
            else:
                player = self.bc.current_player
                if self._is_human_vs_human():
                    role = "选手A(白)" if player == "A" else "选手B(黑)"
                elif self._is_ai_vs_ai() or player != self.human_player:
                    role = "AI"
                else:
                    role = "您"
                color = "黑" if player == "B" else "白"
                step = self.bc.step + 1
                pause = " [已暂停]" if self._paused else ""
                self.lbl_status.config(
                    text=f"Ban 阶段 — 第 {step}/{self.ban_cfg.ban_count} 次 "
                         f"({role}/选手{player}/{color}){pause}")
        elif self.state == PLAYING:
            turn = self._whose_turn()
            if self._is_human_vs_human():
                role = "黑方" if turn == "B" else "白方"
            elif self._is_ai_vs_ai() or turn != self.human_color:
                role = "AI"
            else:
                role = "您"
            color = "黑" if turn == "B" else "白"
            pause = " [已暂停]" if self._paused else ""
            self.lbl_status.config(text=f"正式对局 — 轮到 {role}({color}){pause}")
        elif self.state == AI_THINKING:
            max_t = self.settings.get("maxTime", 10.0)
            if not self.bc.is_finished:
                self.lbl_status.config(text=f"Ban 阶段 — AI 选禁点中...")
            else:
                self.lbl_status.config(text=f"AI 思考中... (最多 {max_t:.0f} 秒)")
        elif self.state == MARK_DEAD:
            self.lbl_status.config(text=f"标记死子模式 — 点击死子标记/取消，确认后数子（已标记 {len(self.dead_stones)} 个）")
        elif self.state == GAME_OVER:
            self.lbl_status.config(text=f"对局结束: {self.game_result}")

        self._update_buttons()

    def _update_buttons(self):
        playing = self.state == PLAYING
        ban_phase = self.state == BAN_PHASE
        ai_vs_ai = self._is_ai_vs_ai()
        human_turn = playing and (self._is_human_vs_human() or self._whose_turn() == self.human_color)

        # 人vsAI 才显示 Pass/认输；AIvsAI 才显示 暂停/继续
        self.buttons["Pass"].config(
            state=tk.NORMAL if (human_turn and not ai_vs_ai) else tk.DISABLED)
        self.buttons["认输"].config(
            state=(tk.NORMAL if (playing or self.state == AI_THINKING) and not ai_vs_ai
                   else tk.DISABLED))
        self.buttons["暂停/继续"].config(
            state=tk.NORMAL if (ai_vs_ai and self.state in (PLAYING, AI_THINKING, BAN_PHASE))
            else tk.DISABLED)
        self.buttons["导出 SGF"].config(
            state=tk.NORMAL if (self.game_moves or self.bc.banned) else tk.DISABLED)
        self.buttons["新对局"].config(
            state=tk.NORMAL if self.state != AI_THINKING else tk.DISABLED)
        self.buttons["确认数子"].config(
            state=tk.NORMAL if self.state == MARK_DEAD else tk.DISABLED)

    def _update_ban_label(self):
        if not self.bc.banned:
            if self.state == BAN_PHASE:
                self.lbl_bans.config(text="（等待选禁点...）")
            else:
                self.lbl_bans.config(text="（无禁点）")
        else:
            labels = sorted(point_to_gtp(r, c) for r, c in self.bc.banned)
            self.lbl_bans.config(text=f"({len(labels)} 个): {' '.join(labels)}")

    def flash_status(self, text: str):
        self.lbl_status.config(text=text)
        self.root.after(4000, self.update_status)

    def log(self, text: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── 关闭 ──

    def _on_close(self):
        if self.eng:
            self.eng.close()
        self.root.destroy()


# ── 入口 ────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app = BanGoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
