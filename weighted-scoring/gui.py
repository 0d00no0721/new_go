# -*- coding: utf-8 -*-
"""
gui.py — 19路加权点目围棋 GUI（tkinter）

职责：
  1. 图形化棋盘（19×19 Canvas）+ 人 vs AI / AI vs AI / 人 vs 人
  2. AI 思考实时显示（kata-analyze 流式 → winrate/visits/PV）
  3. 权重热力图叠加（色阶映射：天元 1.72 亮、星位 0.79 暗）
  4. 终局加权分（引擎 final_score + scoring.py 明细）+ SGF 导出

线程模型（严格遵循，否则 tkinter 崩溃）：
  - AI 落子：后台线程 eng.genmove() → ai_queue → root.after(100, _poll_ai) 消费
  - AI 思考：后台线程 eng.analyze() → analyze_queue → root.after(200, _poll_analyze) 消费
  - 禁止后台线程直接调 tkinter，所有 UI 更新在主线程 after 回调里

复用模块：
  - cli_player.GtpEngine / ascii_safe_copy（subprocess GTP 通信）
  - sgf_io.ReplayBoard / SgfGame / export_sgf / coords（SGF + 坐标 + 复盘棋盘）
  - scoring.score_game / load_weights（加权数子，RULES 模块）
  - settings.load_settings / save_settings（settings.json 持久化）

坐标系：内部 (r,c) 0-indexed，r=0 顶部；scoring.py 用 1-based，调用时转换。
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

from cli_player import GtpEngine, ascii_safe_copy
from scoring import load_weights, score_game
from sgf_io import (
    COL_LETTERS,
    N,
    ReplayBoard,
    SgfGame,
    export_sgf,
    gtp_to_rc,
    rc_to_gtp,
)
from settings import (
    DEFAULT_SETTINGS,
    PRESETS,
    build_override_configs,
    load_settings,
    save_settings,
    settings_exist,
)

# ── 常量 ────────────────────────────────────────────────────────────────────

BOARD_SIZE = N  # 19

# 状态机
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

# 19 路星位（r, c 0-indexed）：标准 9 星
STAR_POINTS = [
    (3, 3), (3, 9), (3, 15),
    (9, 3), (9, 9), (9, 15),
    (15, 3), (15, 9), (15, 15),
]


# ── 权重色阶（diverging colormap）───────────────────────────────────────────
# W∈[0.66, 1.97]（D4 对称化后）：<1 偏冷蓝、>1 偏暖红、1.0 中性（浅米）。

def weight_color(w: float) -> tuple[int, int, int]:
    """权重 → RGB（0-255）。以 log2(w) 为色阶基准：w=1→0（中性），w=2→+1（暖端）。"""
    import math
    t = math.log2(w) if w > 0 else 0.0
    t = max(-1.0, min(1.0, t))
    if t >= 0:
        r = int(238 + (200 - 238) * t)
        g = int(232 + (50 - 232) * t)
        b = int(196 + (40 - 196) * t)
    else:
        tt = -t
        r = int(238 + (50 - 238) * tt)
        g = int(232 + (110 - 232) * tt)
        b = int(196 + (190 - 196) * tt)
    return (r, g, b)


def weight_hex(w: float) -> str:
    """权重 → '#rrggbb' 字符串。"""
    r, g, b = weight_color(w)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── 设置对话框 ──────────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    """AI / 规则设置对话框（Toplevel）。确定后 self.result 存 settings dict，取消为 None。"""

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
        self.v_threads = tk.StringVar(value=str(current.get("numSearchThreads", 20)))
        ttk.Entry(frm, textvariable=self.v_threads, width=12).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # ponderingEnabled
        self.v_ponder = tk.BooleanVar(value=bool(current.get("ponderingEnabled", False)))
        ttk.Checkbutton(frm, text="后台思考（开启会占 GPU 可能卡顿）",
                        variable=self.v_ponder).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 贴目
        ttk.Label(frm, text="贴目（komi）").grid(row=row, column=0, sticky="w", pady=3)
        self.v_komi = tk.StringVar(value=str(current.get("komi", 7.5)))
        ttk.Entry(frm, textvariable=self.v_komi, width=12).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # 引擎文件
        ttk.Label(frm, text="引擎文件 (katago.exe)").grid(row=row, column=0, sticky="w", pady=3)
        eng_frm = ttk.Frame(frm)
        eng_frm.grid(row=row, column=1, sticky="w", pady=3)
        self.v_engine = tk.StringVar(value=current.get("engine_path", "katago.exe"))
        ttk.Entry(eng_frm, textvariable=self.v_engine, width=28).pack(side="left")
        ttk.Button(eng_frm, text="浏览", command=lambda: self._browse_file(
            self.v_engine, "选择引擎文件", [("KataGo 引擎", "*.exe"), ("所有文件", "*.*")]),
            width=6).pack(side="left", padx=4)
        row += 1

        # 引擎配置
        ttk.Label(frm, text="引擎配置 (default_gtp.cfg)").grid(row=row, column=0, sticky="w", pady=3)
        cfg_frm = ttk.Frame(frm)
        cfg_frm.grid(row=row, column=1, sticky="w", pady=3)
        self.v_config = tk.StringVar(value=current.get("config_path", "default_gtp.cfg"))
        ttk.Entry(cfg_frm, textvariable=self.v_config, width=28).pack(side="left")
        ttk.Button(cfg_frm, text="浏览", command=lambda: self._browse_file(
            self.v_config, "选择引擎配置", [("GTP 配置", "*.cfg"), ("所有文件", "*.*")]),
            width=6).pack(side="left", padx=4)
        row += 1

        # 神经网络权重（模型）
        ttk.Label(frm, text="神经网络权重 (.bin.gz)").grid(row=row, column=0, sticky="w", pady=3)
        path_frm = ttk.Frame(frm)
        path_frm.grid(row=row, column=1, sticky="w", pady=3)
        self.v_model = tk.StringVar(value=current.get("model_path", "28b.bin.gz"))
        ttk.Entry(path_frm, textvariable=self.v_model, width=28).pack(side="left")
        ttk.Button(path_frm, text="浏览", command=lambda: self._browse_file(
            self.v_model, "选择网络权重", [("KataGo 权重", "*.bin.gz *.bin"), ("所有文件", "*.*")]),
            width=6).pack(side="left", padx=4)
        row += 1

        # 加权表
        ttk.Label(frm, text="加权表 (weight_table)").grid(row=row, column=0, sticky="w", pady=3)
        wt_frm = ttk.Frame(frm)
        wt_frm.grid(row=row, column=1, sticky="w", pady=3)
        self.v_weights = tk.StringVar(value=current.get("weights_path", "weight_table_final.txt"))
        ttk.Entry(wt_frm, textvariable=self.v_weights, width=28).pack(side="left")
        ttk.Button(wt_frm, text="浏览", command=lambda: self._browse_file(
            self.v_weights, "选择加权表", [("加权表", "*.txt"), ("所有文件", "*.*")]),
            width=6).pack(side="left", padx=4)
        row += 1

        # 对局模式
        ttk.Label(frm, text="对局模式").grid(row=row, column=0, sticky="w", pady=3)
        self.v_mode = tk.StringVar(value=current.get("game_mode", "人vsAI"))
        ttk.Combobox(frm, textvariable=self.v_mode, state="readonly",
                     values=["人vsAI", "AIvsAI", "人vs人"], width=10).grid(
            row=row, column=1, sticky="w", pady=3)
        row += 1

        # 热力图
        self.v_heatmap = tk.BooleanVar(value=bool(current.get("show_heatmap", False)))
        ttk.Checkbutton(frm, text="显示权重热力图",
                        variable=self.v_heatmap).grid(row=row, column=1, sticky="w", pady=3)
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

    def _browse_file(self, var: tk.StringVar, title: str, filetypes: list):
        path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=os.path.dirname(var.get()) or ".",
        )
        if path:
            var.set(path)

    def _ok(self):
        try:
            visits = int(self.v_visits.get())
            t = float(self.v_time.get())
            threads = int(self.v_threads.get())
            komi = float(self.v_komi.get())
        except ValueError:
            messagebox.showerror("设置", "数值格式错误，请检查", parent=self)
            return

        model = self.v_model.get().strip()
        engine = self.v_engine.get().strip()
        config = self.v_config.get().strip()
        if not os.path.isfile(model):
            messagebox.showwarning("设置", f"网络权重文件不存在：\n{model}", parent=self)
            return

        self.result = {
            "level": self.v_level.get(),
            "maxVisits": visits,
            "maxTime": t,
            "numSearchThreads": threads,
            "ponderingEnabled": bool(self.v_ponder.get()),
            "komi": komi,
            "engine_path": engine,
            "config_path": config,
            "model_path": model,
            "weights_path": self.v_weights.get().strip(),
            "game_mode": self.v_mode.get(),
            "show_heatmap": bool(self.v_heatmap.get()),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ── 主应用 ──────────────────────────────────────────────────────────────────

class WeightedGoApp:
    """19路加权点目围棋 GUI 主应用。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("19路加权点目围棋")
        root.resizable(False, False)

        # 设置
        self.settings = load_settings()
        _first_launch = not settings_exist()

        self.rows = N
        self.cols = N
        self.cell = 28
        self.margin = 36
        self.px_x = 2 * self.margin + self.cell * (self.cols - 1)
        self.px_y = 2 * self.margin + self.cell * (self.rows - 1)

        # 棋色：人=黑(B先手)，AI=白(W后手)
        self.human_color = "B"
        self.ai_color = "W"

        # 游戏状态
        self.state = PLAYING
        self.board = ReplayBoard(N)          # 带提子的影子棋盘（0-indexed）
        self.dead_stones: set[tuple[int, int]] = set()   # 标记的死子（0-indexed）
        self.last_stone: tuple[int, int] | None = None
        self.game_moves: list[tuple[str, str]] = []      # (color, gtp_coord or "pass")
        self.passes = 0
        self.resigned_by: str | None = None
        self.game_result = ""
        self.weights_2d = None               # 加载的加权表（scoring.py 2D 格式）
        self._paused = False                 # AIvsAI 暂停

        # 引擎
        self.eng: GtpEngine | None = None
        self._eng_ready = False

# 线程通信队列
        self.ai_queue: queue.Queue = queue.Queue()
        self.analyze_queue: queue.Queue = queue.Queue()
        self.gen = 0                         # 代数（防过期回调）
        self.analyze_gen: int | None = None  # 当前分析线程代数
        self.analyze_stop: threading.Event | None = None
        self._conn_lock = threading.Lock()   # 串行化引擎命令（analyze 与 genmove 互斥）

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

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="设置", command=self._open_settings)
        m_file.add_command(label="新对局", command=self.new_game)
        m_file.add_separator()
        m_file.add_command(label="导入 SGF", command=self.import_sgf)
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

        # 加权表信息
        tk.Label(side, text="加权表", font=("Microsoft YaHei", 11, "bold"),
                 anchor="w").pack(fill="x", pady=(4, 4))
        self.lbl_wt = tk.Label(side, text="（未加载）", anchor="w",
                               font=("Microsoft YaHei", 9), wraplength=240,
                               justify="left", fg="#666")
        self.lbl_wt.pack(fill="x")

        ttk.Separator(side, orient="horizontal").pack(fill="x", pady=8)

        # 按钮
        btn_frame = tk.Frame(side)
        btn_frame.pack(fill="x", pady=4)
        self.buttons: dict[str, tk.Button] = {}
        for text, cmd in [
            ("Pass", self.human_pass),
            ("认输", self.human_resign),
            ("暂停/继续", self._toggle_pause),
            ("热力图", self.toggle_heatmap),
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

    def _draw_heatmap(self):
        """在网格线下方绘制权重热力图色块（每点按其 W 着色）。"""
        if not self.weights_2d or not self.settings.get("show_heatmap", False):
            return
        cv = self.canvas
        cell, m = self.cell, self.margin
        for r in range(self.rows):
            for c in range(self.cols):
                w = self.weights_2d[r][c]
                x = m + c * cell
                y = m + r * cell
                color = weight_hex(w)
                cv.create_rectangle(
                    x - cell / 2, y - cell / 2, x + cell / 2, y + cell / 2,
                    fill=color, outline=color,
                )

    def draw_board(self):
        cv = self.canvas
        cv.delete("all")
        cv.configure(bg=BOARD_BG)
        rows, cols_n = self.rows, self.cols
        cell, m = self.cell, self.margin
        px_x = self.px_x
        px_y = self.px_y

        # 热力图色块（网格线之下）
        self._draw_heatmap()

        # 网格线
        for r in range(rows):
            y = m + r * cell
            cv.create_line(m, y, m + (cols_n - 1) * cell, y, fill=LINE_COLOR)
        for c in range(cols_n):
            x = m + c * cell
            cv.create_line(x, m, x, m + (rows - 1) * cell, fill=LINE_COLOR)

        # 星位
        for r, c in STAR_POINTS:
            if r < rows and c < cols_n:
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

        # 棋子（self.board.stones 为 0-indexed (r,c)，Canvas 同坐标）
        for (r, c), color in self.board.stones.items():
            self._draw_stone(r, c, color)

        # 最后一手标记
        if self.last_stone:
            r, c = self.last_stone
            x, y = m + c * cell, m + r * cell
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=MARK_RED, outline="")

        # 死子标记（标记死子模式下，红色 X 叠在棋子上）
        if self.state == MARK_DEAD:
            for (r, c) in self.dead_stones:
                x, y = m + c * cell, m + r * cell
                d = cell * 0.3
                cv.create_line(x - d, y - d, x + d, y + d, fill=MARK_RED, width=2)
                cv.create_line(x - d, y + d, x + d, y - d, fill=MARK_RED, width=2)

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
        """Canvas (r=0..rows-1, c=0..cols-1, 顶部/左侧) → GTP 坐标。"""
        return rc_to_gtp(r, c)

    # ── 引擎启动 ──

    @staticmethod
    def _resolve_path(p: str) -> str:
        """将相对路径解析为绝对路径：frozen 模式相对 exe 目录，开发模式相对脚本目录。"""
        if os.path.isabs(p):
            return p
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, p)

    def _start_engine(self):
        self._eng_ready = False
        self.lbl_status.config(text="正在加载引擎...（首次启动可能需 1-2 分钟）")
        s = self.settings
        engine = self._resolve_path(s.get("engine_path", "katago.exe"))
        model = self._resolve_path(s.get("model_path", "28b.bin.gz"))
        config = self._resolve_path(s.get("config_path", "default_gtp.cfg"))
        extra_cfg = self._resolve_path(s.get("extra_config_path", "gtp_override.cfg"))
        komi = float(s.get("komi", 7.5))
        override = build_override_configs(s) + [f"ignoreGTPAndForceKomi={komi}"]
        extra = [extra_cfg] if os.path.isfile(extra_cfg) else []

        def worker():
            try:
                self.eng = GtpEngine(
                    engine, model, config,
                    boardsize=N, stderr_path="engine_gui.log",
                    extra_configs=extra,
                    override_configs=override,
                )
# 加载加权表
                wpath = self._resolve_path(s.get("weights_path", "weight_table_final.txt"))
                if os.path.isfile(wpath):
                    self.eng.load_weights(ascii_safe_copy(wpath))
                    self.weights_2d = load_weights(wpath)
                else:
                    self.weights_2d = None
                self._eng_ready = True
                komi_actual = self.eng.send("get_komi").strip()
                self.ai_queue.put(("engine_ready", komi_actual))
            except Exception as e:
                self.ai_queue.put(("engine_error", str(e)))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_engine_ready(self, komi: str):
        self.log(f"引擎就绪，komi={komi}")
        if self.weights_2d:
            wsum = sum(sum(row) for row in self.weights_2d)
            wmin = min(min(row) for row in self.weights_2d)
            wmax = max(max(row) for row in self.weights_2d)
            self.lbl_wt.config(text=f"ΣW={wsum:.2f}  范围 [{wmin:.3f}, {wmax:.3f}]\n"
                                    f"天元={self.weights_2d[9][9]:.2f} "
                                    f"星位D16={self.weights_2d[3][3]:.2f}")
            if self.settings.get("show_heatmap", False):
                self.draw_board()
        self.update_status()
        # 若 AI 先手（AIvsAI 黑先），自动触发
        if self._is_ai_vs_ai():
            self.root.after(500, self._ai_move_async)

    def _on_engine_error(self, err: str):
        s = self.settings
        engine = self._resolve_path(s.get("engine_path", "katago.exe"))
        self.lbl_status.config(text=f"引擎启动失败: {err}")
        messagebox.showerror("引擎错误",
                             f"无法启动 KataGo 引擎:\n{err}\n\n"
                             f"引擎路径: {engine}\n\n"
                             f"请在「文件 → 设置」中检查引擎、配置、权重文件路径。")

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
                 f"time={self.settings['maxTime']}s komi={self.settings['komi']}")
        if first_launch:
            self._start_engine()
        else:
            if messagebox.askyesno("设置", "新设置将在下一局生效。\n是否立即开始新对局？"):
                self.new_game(restart=True)

    def restart_engine(self):
        """关闭当前引擎，用当前 settings 重新启动，重置对局。"""
        self.gen += 1
        self._eng_ready = False
        if self.eng:
            self.eng.close()
            self.eng = None
        self._reset_game()
        self._start_engine()

    def _reset_game(self):
        """重置对局状态（保留棋盘尺寸与设置）。"""
        self.board = ReplayBoard(N)
        self.dead_stones = set()
        self.game_moves.clear()
        self.last_stone = None
        self.passes = 0
        self.resigned_by = None
        self.game_result = ""
        self._paused = False
        self.state = PLAYING
        self.lbl_winrate.config(text="胜率: --")
        self.lbl_visits.config(text="访问: --")
        self.lbl_pv.config(text="PV: --")
        self.draw_board()
        self._update_buttons()

    # ── 鼠标点击 ──

    def on_click(self, event):
        if not self._eng_ready and not self._is_human_vs_human():
            return
        if self._is_ai_vs_ai():
            return
        pos = self._event_to_pos(event)
        if pos is None:
            return
        r, c = pos

        if self.state == PLAYING:
            self._on_play_click(r, c)
        elif self.state == MARK_DEAD:
            self._on_dead_click(r, c)

    def _on_play_click(self, r: int, c: int):
        if self.state != PLAYING:
            return
        turn = self._whose_turn()
        if not self._is_human_vs_human() and turn != self.human_color:
            self.flash_status("当前轮到 AI 落子...")
            return

        gtp = self._pos_to_gtp(r, c)
        if (r, c) in self.board.stones:
            messagebox.showwarning("落子无效", f"{gtp} 已有棋子")
            return

        self._do_move(turn, gtp)
        if not self._is_human_vs_human():
            self._ai_move_async()

    def _on_dead_click(self, r: int, c: int):
        """标记死子模式下：点击棋子切换死子标记，点击空点忽略。"""
        if (r, c) in self.board.stones:
            if (r, c) in self.dead_stones:
                self.dead_stones.discard((r, c))
            else:
                self.dead_stones.add((r, c))
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
            r, c = gtp_to_rc(gtp)
            self.board.play(color, r, c)
            self.last_stone = (r, c)
            color_gtp = "black" if color == "B" else "white"
            if self.eng and self._eng_ready:
                try:
                    self.eng.play(color_gtp, gtp)
                except RuntimeError as e:
                    self.log(f"play 同步失败: {e}")
        self.passes = 0
        self.draw_board()
        self.update_status()

    # ── 引擎同步辅助（人 vs AI 时人类落子后启动 AI）──

    def _ai_move_async(self):
        if self._is_ai_vs_ai():
            turn = self._whose_turn()
        else:
            turn = self.ai_color
        color_gtp = "black" if turn == "B" else "white"
        self.state = AI_THINKING
        self.gen += 1
        gen = self.gen
        self.update_status()
        self._start_analyze(gen, turn)

        max_t = self.settings.get("maxTime", 10.0)
        timeout = max_t + 30

        def worker():
            try:
                with self._conn_lock:
                    result = self.eng.send(f"genmove {color_gtp}", timeout=timeout).strip()
                self.ai_queue.put(("move", gen, turn, result))
            except Exception as e:
                self.ai_queue.put(("error", gen, str(e)))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    # ── AI 思考（kata-analyze 流式）──

    def _start_analyze(self, gen: int, turn: str):
        """启动 AI 思考流（后台线程持续 analyze → analyze_queue）。

        与 genmove 通过 self._conn_lock 互斥：analyze 与 genmove 共用同一 GTP 管道，
        若不互斥会因流式 info 行与 genmove 响应交错而损坏协议（ban-selection 同理）。
        """
        if self.analyze_gen is not None and self.analyze_stop is not None:
            self.analyze_stop.set()   # 停止旧的分析线程

        stop = threading.Event()
        self.analyze_gen = gen
        self.analyze_stop = stop

        def worker():
            while not stop.is_set() and self.eng:
                try:
                    with self._conn_lock:
                        info = self.eng.analyze(interval=0.5)
                    if info:
                        self.analyze_queue.put(("analyze", gen, info))
                except Exception:
                    break

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    # ── 人类操作 ──

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
        self.resigned_by = self._whose_turn() if self._is_human_vs_human() else self.human_color
        self._end_game("resign")

    def _toggle_pause(self):
        if not self._is_ai_vs_ai():
            return
        self._paused = not self._paused
        if self._paused:
            self.log("已暂停")
            self.flash_status("已暂停（AIvsAI）")
        else:
            self.log("继续")
            self.update_status()
            if self.state == PLAYING:
                self.root.after(300, self._ai_move_async)

    def toggle_heatmap(self):
        """切换权重热力图显示。"""
        self.settings["show_heatmap"] = not self.settings.get("show_heatmap", False)
        self.draw_board()
        self.update_status()

    # ── 模式判断 ──

    def _is_ai_vs_ai(self) -> bool:
        return self.settings.get("game_mode", "人vsAI") == "AIvsAI"

    def _is_human_vs_human(self) -> bool:
        return self.settings.get("game_mode", "人vs人") == "人vs人"

    # ── 终局 ──

    def _end_game(self, reason: str):
        self.state = GAME_OVER
        self.gen += 1
        if self.analyze_stop is not None:
            self.analyze_stop.set()

        if reason == "resign":
            winner = "W" if self.resigned_by == "B" else "B"
            self.game_result = f"{winner}+R"
            score = self.game_result
            messagebox.showinfo("终局", f"对局结束\n\n{'白' if winner == 'W' else '黑'}方认输，"
                                        f"{'黑' if winner == 'B' else '白'}胜")
        else:
            try:
                score = self.eng.final_score()
                self.game_result = score
            except RuntimeError as e:
                self.log(f"final_score 失败: {e}")
                score = ""
                self.game_result = ""

            # scoring.py 盘面加权明细
            try:
                res = score_game(
                    {(r + 1, c + 1): col for (r, c), col in self.board.stones.items()},
                    self.weights_2d,
                    komi=float(self.settings.get("komi", 7.5)),
                    dead_stones={(r + 1, c + 1) for (r, c) in self.dead_stones},
                )
                d = res["detail"]
                msg = (
                    f"对局结束\n\n"
                    f"引擎 final_score（加权）: {score}\n\n"
                    f"scoring.py 加权明细:\n"
                    f"  黑 {res['black_weighted']:.2f} "
                    f"(子 {d['black_stones_weight']:.1f} + 空 {d['black_territory_weight']:.1f})\n"
                    f"  白 {res['white_weighted']:.2f} "
                    f"(子 {d['white_stones_weight']:.1f} + 空 {d['white_territory']:.1f})\n"
                    f"  中性空 {d['neutral']} 点  贴目 {res['komi']}\n"
                    f"  差分 → {res['result']}"
                )
                messagebox.showinfo("终局（加权分）", msg)
            except Exception as e:
                self.log(f"scoring 明细失败: {e}")
                messagebox.showinfo("终局", f"对局结束\n\n结果（加权）: {score}")

        self._export_sgf_internal()
        self.update_status()
        self._update_buttons()

    def _confirm_dead(self):
        """确认死子标记，UI 层数子（人vs人，不依赖引擎）。"""
        res = score_game(
            {(r + 1, c + 1): col for (r, c), col in self.board.stones.items()},
            self.weights_2d,
            komi=float(self.settings.get("komi", 7.5)),
            dead_stones={(r + 1, c + 1) for (r, c) in self.dead_stones},
        )
        self.game_result = res["result"]
        d = res["detail"]
        messagebox.showinfo(
            "终局（加权分）",
            f"对局结束\n\n加权分: {res['result']}\n\n"
            f"黑 {res['black_weighted']:.2f} "
            f"(子 {d['black_stones_weight']:.1f} + 空 {d['black_territory_weight']:.1f})\n"
            f"白 {res['white_weighted']:.2f} "
            f"(子 {d['white_stones_weight']:.1f} + 空 {d['white_territory']:.1f})\n"
            f"中性空 {d['neutral']}  贴目 {res['komi']}",
        )
        self.state = GAME_OVER
        self._export_sgf_internal()
        self.update_status()
        self._update_buttons()
    # ── SGF ──

    def _build_sgf_game(self) -> SgfGame:
        wt = self._resolve_path(self.settings.get("weights_path", "weight_table_final.txt"))
        return SgfGame(
            boardsize=N,
            komi=float(self.settings.get("komi", 7.5)),
            player_b="人类" if (not self._is_ai_vs_ai() and self.human_color == "B") else "AI",
            player_a="人类" if (not self._is_ai_vs_ai() and self.human_color == "W") else "AI",
            date=datetime.date.today().isoformat(),
            weights_file=wt,
            moves=self.game_moves,
            result=self.game_result,
        )

    def _export_sgf_internal(self) -> str:
        sgf_path = f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf"
        try:
            export_sgf(self._build_sgf_game(), sgf_path)
            self.log(f"SGF 已导出: {sgf_path}")
        except Exception as e:
            self.log(f"SGF 导出失败: {e}")
        return sgf_path

    def export_sgf(self):
        if not self.game_moves:
            messagebox.showinfo("导出", "尚无对局数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".sgf",
            filetypes=[("SGF 棋谱", "*.sgf"), ("所有文件", "*.*")],
            initialfile=f"game_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sgf",
        )
        if not path:
            return
        try:
            export_sgf(self._build_sgf_game(), path)
            messagebox.showinfo("导出", f"已导出: {path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def import_sgf(self):
        path = filedialog.askopenfilename(
            title="导入 SGF 复盘",
            filetypes=[("SGF 棋谱", "*.sgf"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            from sgf_io import import_sgf
            game = import_sgf(path)
            self.board = ReplayBoard(game.boardsize)
            for color, coord in game.moves:
                if coord.lower() == "pass":
                    continue
                r, c = gtp_to_rc(coord)
                self.board.play(color, r, c)
            self.game_moves = list(game.moves)
            self.game_result = game.result
            self.last_stone = None
            self.passes = 0
            self.state = GAME_OVER
            self.draw_board()
            self.update_status()
            self.log(f"已导入 SGF: {path} ({len(game.moves)} 手)")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    # ── 新对局 ──

    def new_game(self, restart: bool = False):
        if self.state == AI_THINKING and not restart:
            return
        self.gen += 1
        if self.analyze_stop is not None:
            self.analyze_stop.set()
        if restart:
            self.restart_engine()
            return
        self._reset_game()
        if self.eng and self._eng_ready:
            try:
                self.eng.send("clear_board")
            except RuntimeError:
                pass
        if self._is_ai_vs_ai() and self._eng_ready:
            self.root.after(500, self._ai_move_async)

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
            self._on_engine_ready(msg[1])
            return
        if kind == "engine_error":
            self._on_engine_error(msg[1])
            return
        gen = msg[1]
        if gen != self.gen:
            return
        if kind == "move":
            self._on_ai_move(msg[2], msg[3])
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
            r, c = gtp_to_rc(result)
            self.board.play(move_color, r, c)
            self.last_stone = (r, c)
            self.passes = 0
            self.log(f"{move_color} 落子: {result}")

        self.state = PLAYING
        self.draw_board()
        self.update_status()
        self._update_buttons()
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
            break

    @staticmethod
    def _extract_field(line: str, field: str) -> str | None:
        m = re.search(rf"\b{field}\s+(\S+)", line)
        return m.group(1) if m else None

    @staticmethod
    def _extract_pv(line: str) -> str:
        m = re.search(r"\bpv\s+(.+?)(?:\b(?:move|visits|winrate|scoreLead|prior|lcb|utility|order)\s|\s*$)", line)
        return m.group(1).strip() if m else ""

    # ── 状态更新 ──

    def update_status(self):
        if self.state == PLAYING:
            turn = self._whose_turn()
            if self._is_human_vs_human():
                role = "黑方" if turn == "B" else "白方"
            elif self._is_ai_vs_ai() or turn != self.human_color:
                role = "AI"
            else:
                role = "您"
            pause = " [已暂停]" if self._paused else ""
            self.lbl_status.config(text=f"正式对局 — 轮到 {role}({'黑' if turn == 'B' else '白'}){pause}")
        elif self.state == AI_THINKING:
            max_t = self.settings.get("maxTime", 10.0)
            self.lbl_status.config(text=f"AI 思考中... (最多 {max_t:.0f} 秒)")
        elif self.state == MARK_DEAD:
            self.lbl_status.config(text=f"标记死子模式 — 点击死子标记/取消，确认后数子（已标记 {len(self.dead_stones)} 个）")
        elif self.state == GAME_OVER:
            heat = " · 热力图开" if self.settings.get("show_heatmap", False) else ""
            self.lbl_status.config(text=f"对局结束: {self.game_result}{heat}")
        self._update_buttons()

    def _update_buttons(self):
        playing = self.state == PLAYING
        ai_vs_ai = self._is_ai_vs_ai()
        human_turn = playing and (self._is_human_vs_human() or self._whose_turn() == self.human_color)
        self.buttons["Pass"].config(
            state=tk.NORMAL if (human_turn and not ai_vs_ai) else tk.DISABLED)
        self.buttons["认输"].config(
            state=tk.NORMAL if (playing or self.state == AI_THINKING) and not ai_vs_ai else tk.DISABLED)
        self.buttons["暂停/继续"].config(
            state=tk.NORMAL if (ai_vs_ai and self.state in (PLAYING, AI_THINKING)) else tk.DISABLED)
        self.buttons["热力图"].config(state=tk.NORMAL)
        self.buttons["确认数子"].config(
            state=tk.NORMAL if self.state == MARK_DEAD else tk.DISABLED)
        self.buttons["导出 SGF"].config(
            state=tk.NORMAL if self.game_moves else tk.DISABLED)
        self.buttons["新对局"].config(
            state=tk.NORMAL if self.state != AI_THINKING else tk.DISABLED)

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
    app = WeightedGoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
