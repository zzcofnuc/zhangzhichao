from __future__ import annotations

import ctypes
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np

from .models import AnalysisResult, ProcessingConfig, SignalData
from .plotting import PlotCanvas
from .processing import analyze_signal
from .signal_io import generate_synthetic_signal, read_signal_file, save_analysis_csv


MOTION_MODES = [
    ("constant", "匀速"),
    ("accelerate", "匀加速"),
    ("decelerate", "匀减速"),
    ("piecewise", "分段速度轨迹"),
    ("curve", "自定义速度曲线"),
]


class DopplerApp(tk.Tk):
    def __init__(self) -> None:
        self._setup_dpi_awareness()
        super().__init__()
        self.colors = {
            "page_bg": "#E9E0D3",
            "panel": "#F6F1E7",
            "panel_alt": "#E1D2BF",
            "ink": "#2D2823",
            "muted": "#756B5B",
            "accent": "#C76632",
            "accent_dark": "#99451D",
            "accent_soft": "#E9B07D",
            "shadow": "#D4C4B0",
            "line": "#D8CEBD",
            "deep": "#3C342C",
        }
        self.title("运动目标多普勒测速软件")
        self.geometry("1460x920")
        self.minsize(1260, 780)
        self.configure(bg=self.colors["page_bg"])

        self.current_signal: SignalData | None = None
        self.current_result: AnalysisResult | None = None
        self.project_root = Path(__file__).resolve().parent.parent
        self.analysis_in_progress = False
        self._syncing_views = False
        self._table_row_count = 0

        self._build_style()
        self._build_variables()
        self._build_layout()
        self._refresh_mode_fields()

    def _setup_dpi_awareness(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=self.colors["page_bg"], foreground=self.colors["ink"], font=("Segoe UI", 10))
        style.configure("Shell.TFrame", background=self.colors["page_bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("PanelAlt.TFrame", background=self.colors["panel_alt"])
        style.configure("Header.TLabel", font=("Georgia", 13, "bold"), background=self.colors["panel"], foreground=self.colors["ink"])
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 10), background=self.colors["panel"], foreground=self.colors["muted"])
        style.configure("Data.Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Data.Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("Data.Treeview", background="#FBF7F0", fieldbackground="#FBF7F0", foreground=self.colors["ink"], bordercolor=self.colors["line"])
        style.configure("Accent.TButton", background=self.colors["accent"], foreground="white", padding=(12, 8), borderwidth=0, font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", self.colors["accent_dark"])])
        style.configure("Soft.TButton", background=self.colors["panel_alt"], foreground=self.colors["ink"], padding=(12, 8), borderwidth=0)
        style.map("Soft.TButton", background=[("active", "#D7C5AD")])
        style.configure("Nav.TNotebook", background=self.colors["panel"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("Nav.TNotebook.Tab", padding=(18, 10), font=("Segoe UI Semibold", 10), background="#E9DDCB", foreground=self.colors["muted"], borderwidth=0)
        style.map("Nav.TNotebook.Tab", background=[("selected", self.colors["accent"])], foreground=[("selected", "white")])

    def _build_variables(self) -> None:
        self.sample_rate_var = tk.StringVar(value="24000")
        self.carrier_freq_var = tk.StringVar(value="24.125")
        self.frame_size_var = tk.StringVar(value="2048")
        self.overlap_var = tk.StringVar(value="0.5")
        self.min_freq_var = tk.StringVar(value="20")
        self.max_freq_var = tk.StringVar(value="6000")

        self.motion_mode_var = tk.StringVar(value="piecewise")
        self.target_speed_var = tk.StringVar(value="12.0")
        self.acceleration_var = tk.StringVar(value="0.8")
        self.end_acceleration_var = tk.StringVar(value="1.5")
        self.duration_var = tk.StringVar(value="4.0")
        self.noise_var = tk.StringVar(value="0.18")
        self.piecewise_segments_var = tk.StringVar(value="0.0,8.0;1.5,12.0;3.0,18.0;4.0,10.0")
        self.curve_file_var = tk.StringVar(value="")

        self.signal_label_var = tk.StringVar(value="未加载信号")
        self.summary_dominant_speed_var = tk.StringVar(value="--")
        self.summary_average_speed_var = tk.StringVar(value="--")
        self.summary_last_speed_var = tk.StringVar(value="--")
        self.summary_freq_var = tk.StringVar(value="--")
        self.status_var = tk.StringVar(value="待命")

    def _build_layout(self) -> None:
        shell = ttk.Frame(self, padding=14, style="Shell.TFrame")
        shell.pack(fill="both", expand=True)

        title_bar = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        title_bar.pack(fill="x", pady=(0, 12))
        badge = tk.Label(title_bar, text="DOPPLER CONSOLE", bg=self.colors["deep"], fg="#F6E9D7", font=("Consolas", 9, "bold"), padx=10, pady=4)
        badge.pack(anchor="w")
        tk.Label(title_bar, text="运动目标多普勒测速软件", bg=self.colors["panel"], fg=self.colors["ink"], font=("Georgia", 22, "bold")).pack(anchor="w", pady=(10, 0))
        tk.Label(title_bar, text="暖色工业仪表台风格，多工况仿真、频谱测频、速度计算与结果导出", bg=self.colors["panel"], fg=self.colors["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))

        main = ttk.Panedwindow(shell, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, style="Panel.TFrame", padding=12)
        right = ttk.Frame(main, style="Panel.TFrame", padding=14)
        main.add(left, weight=1)
        main.add(right, weight=3)

        self._build_left(left)
        self._build_right(right)

        status_bar = ttk.Frame(shell, style="Panel.TFrame", padding=(14, 8))
        status_bar.pack(fill="x", pady=(12, 0))
        tk.Label(status_bar, text="状态", bg=self.colors["panel"], fg=self.colors["muted"], font=("Consolas", 8, "bold")).pack(side="left")
        tk.Label(status_bar, textvariable=self.status_var, bg=self.colors["panel"], fg=self.colors["ink"], font=("Segoe UI Semibold", 10)).pack(side="left", padx=(10, 0))
        tk.Label(
            status_bar,
            text="图表操作: 滚轮缩放 / 左键拖拽平移 / 双击复位 / 悬浮读数",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
        ).pack(side="right")

    def _build_left(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent, style="Nav.TNotebook")
        notebook.pack(fill="both", expand=True)

        param_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=10)
        sim_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=10)
        action_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=10)

        notebook.add(param_tab, text="处理参数")
        notebook.add(sim_tab, text="仿真工况")
        notebook.add(action_tab, text="操作导出")

        intro = ttk.Frame(param_tab, style="PanelAlt.TFrame", padding=12)
        intro.pack(fill="x", pady=(0, 12))
        tk.Label(intro, text="参数控制台", bg=self.colors["panel_alt"], fg=self.colors["ink"], font=("Georgia", 14, "bold")).pack(anchor="w")
        tk.Label(intro, text="调节采样率、载频和频率搜索范围，建立适合当前实验场景的测速基线。", bg=self.colors["panel_alt"], fg=self.colors["muted"], justify="left", wraplength=280).pack(anchor="w", pady=(6, 0))
        ttk.Label(param_tab, text="采集与处理配置", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        for label, variable in [
            ("采样率 (Hz)", self.sample_rate_var),
            ("载频 (GHz)", self.carrier_freq_var),
            ("帧长", self.frame_size_var),
            ("重叠系数", self.overlap_var),
            ("最小频率 (Hz)", self.min_freq_var),
            ("最大频率 (Hz)", self.max_freq_var),
            ("持续时间 (s)", self.duration_var),
            ("噪声系数", self.noise_var),
        ]:
            self._add_entry(param_tab, label, variable)

        sim_intro = ttk.Frame(sim_tab, style="PanelAlt.TFrame", padding=12)
        sim_intro.pack(fill="x", pady=(0, 12))
        tk.Label(sim_intro, text="运动工况实验台", bg=self.colors["panel_alt"], fg=self.colors["ink"], font=("Georgia", 14, "bold")).pack(anchor="w")
        tk.Label(sim_intro, text="在匀速、加减速、分段轨迹和自定义曲线之间切换，快速构造测试样本。", bg=self.colors["panel_alt"], fg=self.colors["muted"], justify="left", wraplength=280).pack(anchor="w", pady=(6, 0))
        ttk.Label(sim_tab, text="运动模型选择", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(sim_tab, text="运动模式", style="Section.TLabel").pack(anchor="w")
        self.mode_combo = ttk.Combobox(sim_tab, values=[label for _, label in MOTION_MODES], state="readonly")
        self.mode_combo.current(3)
        self.mode_combo.pack(fill="x", pady=(6, 10))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
        self.mode_fields_frame = ttk.Frame(sim_tab, style="Panel.TFrame")
        self.mode_fields_frame.pack(fill="x")

        action_intro = ttk.Frame(action_tab, style="PanelAlt.TFrame", padding=12)
        action_intro.pack(fill="x", pady=(0, 12))
        tk.Label(action_intro, text="执行与导出", bg=self.colors["panel_alt"], fg=self.colors["ink"], font=("Georgia", 14, "bold")).pack(anchor="w")
        tk.Label(action_intro, text="从文件导入、生成仿真，到分析、导出明细，全链路在这里完成。", bg=self.colors["panel_alt"], fg=self.colors["muted"], justify="left", wraplength=280).pack(anchor="w", pady=(6, 0))
        ttk.Label(action_tab, text="操作面板", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Button(action_tab, text="导入信号文件", style="Accent.TButton", command=self.load_signal_file).pack(fill="x", pady=(0, 8))
        ttk.Button(action_tab, text="载入示例信号", style="Soft.TButton", command=self.load_demo_signal).pack(fill="x", pady=(0, 8))
        ttk.Button(action_tab, text="生成仿真信号", style="Soft.TButton", command=self.generate_signal).pack(fill="x", pady=(0, 8))
        self.analyze_button = ttk.Button(action_tab, text="执行测速分析", style="Accent.TButton", command=self.run_analysis)
        self.analyze_button.pack(fill="x", pady=(0, 8))
        ttk.Button(action_tab, text="导出 CSV 结果", style="Soft.TButton", command=self.export_csv).pack(fill="x", pady=(0, 12))

        ttk.Label(action_tab, text="当前信号", style="Section.TLabel").pack(anchor="w", pady=(8, 6))
        signal_card = ttk.Frame(action_tab, style="PanelAlt.TFrame", padding=10)
        signal_card.pack(fill="x")
        tk.Label(signal_card, textvariable=self.signal_label_var, bg=self.colors["panel_alt"], fg=self.colors["ink"], justify="left", anchor="w", wraplength=320).pack(fill="x")

        ttk.Label(action_tab, text="运行日志", style="Section.TLabel").pack(anchor="w", pady=(14, 6))
        self.log_text = tk.Text(action_tab, height=14, bg="#FBF7F0", fg=self.colors["ink"], relief="flat", font=("Consolas", 9), padx=10, pady=10, insertbackground=self.colors["accent"])
        self.log_text.pack(fill="both", expand=True)
        self.log("系统初始化完成。")

    def _build_right(self, parent: ttk.Frame) -> None:
        metrics = ttk.Frame(parent, style="Panel.TFrame")
        metrics.pack(fill="x")
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._metric_card(metrics, "主频", self.summary_freq_var, 0)
        self._metric_card(metrics, "主导速度", self.summary_dominant_speed_var, 1)
        self._metric_card(metrics, "平均速度", self.summary_average_speed_var, 2)
        self._metric_card(metrics, "最后一帧", self.summary_last_speed_var, 3)

        charts_shell = ttk.Frame(parent, style="Panel.TFrame")
        charts_shell.pack(fill="both", expand=True, pady=(10, 10))
        ttk.Label(charts_shell, text="分析视图", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        charts_notebook = ttk.Notebook(charts_shell, style="Nav.TNotebook")
        charts_notebook.pack(fill="both", expand=True)

        waveform_tab = ttk.Frame(charts_notebook, style="Panel.TFrame", padding=8)
        spectrum_tab = ttk.Frame(charts_notebook, style="Panel.TFrame", padding=8)
        speed_tab = ttk.Frame(charts_notebook, style="Panel.TFrame", padding=8)
        charts_notebook.add(waveform_tab, text="时域波形")
        charts_notebook.add(spectrum_tab, text="频谱曲线")
        charts_notebook.add(speed_tab, text="速度趋势")

        self.waveform_plot = PlotCanvas(
            waveform_tab,
            "时域波形",
            "时间 / s",
            "幅值",
            "#C76632",
            background="#FBF7F0",
            foreground=self.colors["ink"],
            axis_color="#9B8F80",
        )
        self.waveform_plot.pack(fill="both", expand=True)
        self.spectrum_plot = PlotCanvas(
            spectrum_tab,
            "频谱曲线",
            "频率 / Hz",
            "幅度 / dB",
            "#2F6B7A",
            background="#FBF7F0",
            foreground=self.colors["ink"],
            axis_color="#9B8F80",
        )
        self.spectrum_plot.pack(fill="both", expand=True)
        self.speed_plot = PlotCanvas(
            speed_tab,
            "速度趋势",
            "时间 / s",
            "速度 / m/s",
            "#547A38",
            background="#FBF7F0",
            foreground=self.colors["ink"],
            axis_color="#9B8F80",
        )
        self.speed_plot.pack(fill="both", expand=True)
        self._plots = [self.waveform_plot, self.spectrum_plot, self.speed_plot]
        self._time_sync_plots = [self.waveform_plot, self.speed_plot]
        for plot in self._time_sync_plots:
            plot.on_view_changed = lambda ratio, source=plot: self._sync_views_from_plot(source, ratio)

        columns = ("time", "freq", "speed", "speed_kmh", "amplitude", "snr")
        table_frame = ttk.Frame(parent, style="Panel.TFrame")
        table_frame.pack(fill="both", expand=False)
        ttk.Label(table_frame, text="逐帧结果", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        tk.Label(
            table_frame,
            text="图表视图会同步带动结果表定位，支持横向滚动查看扩展字段。",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 6))
        table_body = ttk.Frame(table_frame, style="Panel.TFrame")
        table_body.pack(fill="both", expand=False)

        self.result_table = ttk.Treeview(table_body, columns=columns, show="headings", height=10, style="Data.Treeview")
        for col, text, width in [
            ("time", "时间 (s)", 150),
            ("freq", "频率 (Hz)", 180),
            ("speed", "速度 (m/s)", 180),
            ("speed_kmh", "速度 (km/h)", 180),
            ("amplitude", "幅值", 150),
            ("snr", "SNR (dB)", 150),
        ]:
            self.result_table.heading(col, text=text)
            self.result_table.column(col, anchor="center", width=width, minwidth=width, stretch=False)
        table_scrollbar = ttk.Scrollbar(table_body, orient="vertical", command=self.result_table.yview)
        table_x_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.result_table.xview)
        self.result_table.configure(yscrollcommand=table_scrollbar.set, xscrollcommand=table_x_scrollbar.set)
        self.result_table.pack(side="left", fill="both", expand=True)
        table_scrollbar.pack(side="right", fill="y")
        table_x_scrollbar.pack(fill="x", pady=(6, 0))
        self.result_table.tag_configure("odd", background="#FBF7F0")
        self.result_table.tag_configure("even", background="#F1E7D8")

    def _sync_views_from_plot(self, source_plot: PlotCanvas, ratio: tuple[float, float]) -> None:
        if self._syncing_views:
            return
        self._syncing_views = True
        try:
            start_ratio, end_ratio = ratio
            for plot in self._time_sync_plots:
                if plot is not source_plot:
                    plot.set_view_ratio(start_ratio, end_ratio, notify=False)
            self._sync_result_table(start_ratio, end_ratio)
        finally:
            self._syncing_views = False

    def _sync_result_table(self, start_ratio: float, end_ratio: float) -> None:
        if self._table_row_count <= 0:
            return
        visible_rows = max(1, int(self.result_table.cget("height")))
        max_first_row = max(0, self._table_row_count - visible_rows)
        target_first_row = int(round(start_ratio * max_first_row))
        fraction = 0.0 if max_first_row == 0 else target_first_row / max_first_row
        self.result_table.yview_moveto(float(np.clip(fraction, 0.0, 1.0)))

    def _add_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        box = ttk.Frame(parent, style="Panel.TFrame")
        box.pack(fill="x", pady=(0, 8))
        ttk.Label(box, text=label).pack(anchor="w", pady=(0, 4))
        entry = ttk.Entry(box, textvariable=variable)
        entry.pack(fill="x")

    def _metric_card(self, parent: ttk.Frame, title: str, variable: tk.StringVar, column: int) -> None:
        card = ttk.Frame(parent, style="PanelAlt.TFrame", padding=12)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
        tk.Label(card, text=title.upper(), bg=self.colors["panel_alt"], fg=self.colors["muted"], font=("Consolas", 8, "bold")).pack(anchor="w")
        tk.Label(card, textvariable=variable, bg=self.colors["panel_alt"], fg=self.colors["accent_dark"], font=("Georgia", 16, "bold")).pack(anchor="w", pady=(10, 0))

    def _on_mode_changed(self, _: object) -> None:
        selected_label = self.mode_combo.get()
        for value, label in MOTION_MODES:
            if label == selected_label:
                self.motion_mode_var.set(value)
                break
        self._refresh_mode_fields()

    def _refresh_mode_fields(self) -> None:
        for child in self.mode_fields_frame.winfo_children():
            child.destroy()

        mode = self.motion_mode_var.get()
        if mode == "constant":
            self._add_entry(self.mode_fields_frame, "匀速速度 (m/s)", self.target_speed_var)
        elif mode == "accelerate":
            self._add_entry(self.mode_fields_frame, "初始速度 (m/s)", self.target_speed_var)
            self._add_entry(self.mode_fields_frame, "加速度 (m/s²)", self.acceleration_var)
        elif mode == "decelerate":
            self._add_entry(self.mode_fields_frame, "初始速度 (m/s)", self.target_speed_var)
            self._add_entry(self.mode_fields_frame, "减速度 (m/s²)", self.acceleration_var)
        elif mode == "piecewise":
            self._add_entry(self.mode_fields_frame, "起始速度 (m/s)", self.target_speed_var)
            self._add_entry(self.mode_fields_frame, "起始加速度 (m/s²)", self.acceleration_var)
            self._add_entry(self.mode_fields_frame, "结束加速度 (m/s²)", self.end_acceleration_var)
            box = ttk.Frame(self.mode_fields_frame, style="Panel.TFrame")
            box.pack(fill="x", pady=(0, 8))
            ttk.Label(box, text="分段速度点 time,speed").pack(anchor="w", pady=(0, 4))
            ttk.Entry(box, textvariable=self.piecewise_segments_var).pack(fill="x")
            ttk.Label(box, text="示例: 0.0,8.0;1.5,12.0;3.0,18.0;4.0,10.0", foreground="#6A747C").pack(anchor="w", pady=(4, 0))
        elif mode == "curve":
            box = ttk.Frame(self.mode_fields_frame, style="Panel.TFrame")
            box.pack(fill="x", pady=(0, 8))
            ttk.Label(box, text="速度曲线文件").pack(anchor="w", pady=(0, 4))
            ttk.Entry(box, textvariable=self.curve_file_var).pack(fill="x")
            ttk.Button(box, text="选择 CSV", command=self.pick_curve_file).pack(anchor="e", pady=(6, 0))
            ttk.Label(box, text="CSV 两列: time_s,speed_mps", foreground="#6A747C").pack(anchor="w", pady=(4, 0))

    def pick_curve_file(self) -> None:
        file_path = filedialog.askopenfilename(title="选择速度曲线 CSV", filetypes=[("CSV", "*.csv *.txt"), ("All Files", "*.*")])
        if file_path:
            self.curve_file_var.set(file_path)

    def load_signal_file(self) -> None:
        file_path = filedialog.askopenfilename(title="选择待测速信号文件", filetypes=[("Signal Files", "*.csv *.txt *.wav"), ("All Files", "*.*")])
        if not file_path:
            return
        try:
            self.current_signal = read_signal_file(file_path, sample_rate_hint_hz=float(self.sample_rate_var.get()))
            self.current_result = None
            self.signal_label_var.set(f"{Path(file_path).name}\n采样率 {self.current_signal.sample_rate_hz:.1f} Hz\n时长 {self.current_signal.duration_s:.2f} s")
            self._plot_signal_preview(self.current_signal)
            self.log(f"已读取信号文件: {file_path}")
            self.status_var.set("已加载外部信号")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))

    def load_demo_signal(self) -> None:
        demo_file = self.project_root / "samples" / "demo_signal.csv"
        if not demo_file.exists():
            messagebox.showwarning("缺少示例", "请先运行 generate_sample_data.py")
            return
        try:
            self.current_signal = read_signal_file(demo_file)
            self.current_result = None
            self.signal_label_var.set(f"{demo_file.name}\n采样率 {self.current_signal.sample_rate_hz:.1f} Hz\n时长 {self.current_signal.duration_s:.2f} s")
            self._plot_signal_preview(self.current_signal)
            self.log("已载入示例信号。")
            self.status_var.set("已加载示例信号")
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))

    def generate_signal(self) -> None:
        try:
            config = self._read_config()
            duration_s = self._read_float(self.duration_var, "持续时间", minimum=0.1, maximum=600.0)
            noise_level = self._read_float(self.noise_var, "噪声系数", minimum=0.0, maximum=5.0)
            speed_profile = self._build_speed_profile(duration_s, config.sample_rate_hz)
            self.current_signal = generate_synthetic_signal(
                duration_s=duration_s,
                config=config,
                target_speed_mps=float(speed_profile[0]) if speed_profile is not None and speed_profile.size > 0 else 0.0,
                speed_profile_mps=speed_profile,
                noise_level=noise_level,
            )
            self.current_result = None
            self.signal_label_var.set(f"{self.current_signal.source_name}\n采样率 {self.current_signal.sample_rate_hz:.1f} Hz\n时长 {self.current_signal.duration_s:.2f} s")
            self._plot_signal_preview(self.current_signal)
            self.log(f"已生成仿真信号，模式: {self.mode_combo.get()}")
            self.status_var.set(f"仿真模式: {self.mode_combo.get()}")
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))

    def _build_speed_profile(self, duration_s: float, sample_rate_hz: float) -> np.ndarray | None:
        sample_count = max(1, int(duration_s * sample_rate_hz))
        time_axis_s = np.arange(sample_count, dtype=float) / sample_rate_hz
        mode = self.motion_mode_var.get()

        if mode == "constant":
            return np.full(sample_count, self._read_float(self.target_speed_var, "匀速速度"), dtype=float)
        if mode == "accelerate":
            return self._read_float(self.target_speed_var, "初始速度") + self._read_float(self.acceleration_var, "加速度") * time_axis_s
        if mode == "decelerate":
            return np.maximum(0.0, self._read_float(self.target_speed_var, "初始速度") - abs(self._read_float(self.acceleration_var, "减速度")) * time_axis_s)
        if mode == "piecewise":
            points = self._parse_piecewise_points()
            times = np.array([item[0] for item in points], dtype=float)
            speeds = np.array([item[1] for item in points], dtype=float)
            return np.interp(time_axis_s, times, speeds, left=speeds[0], right=speeds[-1])
        if mode == "curve":
            curve_path = self.curve_file_var.get().strip()
            if not curve_path:
                raise ValueError("请先选择速度曲线 CSV 文件。")
            curve_signal = read_signal_file(curve_path)
            return np.interp(time_axis_s, curve_signal.time_axis_s, curve_signal.samples, left=curve_signal.samples[0], right=curve_signal.samples[-1])
        return None

    def _parse_piecewise_points(self) -> list[tuple[float, float]]:
        raw = self.piecewise_segments_var.get().strip()
        if not raw:
            raise ValueError("请填写分段速度点。")
        points: list[tuple[float, float]] = []
        for chunk in raw.split(";"):
            parts = [item.strip() for item in chunk.split(",")]
            if len(parts) != 2:
                raise ValueError("分段速度点格式应为 time,speed;time,speed")
            points.append((float(parts[0]), float(parts[1])))
        points.sort(key=lambda item: item[0])
        if len(points) < 2:
            raise ValueError("至少需要两个分段点。")
        if points[0][0] < 0:
            raise ValueError("分段时间不能为负数。")
        for previous, current in zip(points, points[1:]):
            if current[0] <= previous[0]:
                raise ValueError("分段时间必须严格递增。")
        return points

    def run_analysis(self) -> None:
        if self.current_signal is None:
            messagebox.showwarning("缺少信号", "请先导入信号或生成仿真信号。")
            return
        if self.analysis_in_progress:
            return
        try:
            config = self._read_config()
            signal = self.current_signal
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.analysis_in_progress = True
        self.analyze_button.configure(text="分析中...", state="disabled")
        self.log("开始执行测速分析。")
        self.status_var.set("正在执行测速分析")

        def worker() -> None:
            try:
                result = analyze_signal(signal, config)
                self.after(0, lambda: self._finish_success(result))
            except Exception as exc:
                self.after(0, lambda: self._finish_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_success(self, result: AnalysisResult) -> None:
        self.analysis_in_progress = False
        self.analyze_button.configure(text="执行测速分析", state="normal")
        self.current_result = result
        self.summary_freq_var.set(f"{result.summary.dominant_frequency_hz:.2f} Hz")
        self.summary_dominant_speed_var.set(f"{result.summary.dominant_speed_mps:.2f} m/s")
        self.summary_average_speed_var.set(f"{result.summary.average_speed_mps:.2f} m/s")
        if result.frames:
            self.summary_last_speed_var.set(f"{result.frames[-1].filtered_speed_mps:.2f} m/s")
        else:
            self.summary_last_speed_var.set("--")
        self._render_result(result)
        self.log("分析完成。")
        self.status_var.set("分析完成")

    def _finish_error(self, exc: Exception) -> None:
        self.analysis_in_progress = False
        self.analyze_button.configure(text="执行测速分析", state="normal")
        messagebox.showerror("分析失败", str(exc))
        self.status_var.set("分析失败")

    def _plot_signal_preview(self, signal: SignalData) -> None:
        count = min(1200, signal.samples.size)
        if count <= 0:
            self.waveform_plot.clear()
            return
        idx = np.linspace(0, signal.samples.size - 1, count, dtype=int)
        self.waveform_plot.set_data(signal.time_axis_s[idx], signal.samples[idx])
        self.spectrum_plot.clear()
        self.spectrum_plot.set_marker(None)
        self.speed_plot.clear()
        self._table_row_count = 0
        for item in self.result_table.get_children():
            self.result_table.delete(item)

    def _render_result(self, result: AnalysisResult) -> None:
        self._syncing_views = True
        spectrum_mask = (result.spectrum_frequency_hz >= result.config.min_frequency_hz) & (result.spectrum_frequency_hz <= result.config.max_frequency_hz)
        freq = result.spectrum_frequency_hz[spectrum_mask]
        mag = result.spectrum_magnitude_db[spectrum_mask]
        if freq.size > 1200:
            idx = np.linspace(0, freq.size - 1, 1200, dtype=int)
            freq = freq[idx]
            mag = mag[idx]
        self.spectrum_plot.set_data(freq, mag)
        self.spectrum_plot.set_marker(
            result.summary.dominant_frequency_hz,
            f"主峰 {result.summary.dominant_frequency_hz:.2f} Hz",
            color=self.colors["accent_dark"],
        )

        times = np.array([frame.timestamp_s for frame in result.frames], dtype=float)
        speeds = np.array([frame.filtered_speed_mps for frame in result.frames], dtype=float)
        if times.size > 1200:
            idx = np.linspace(0, times.size - 1, 1200, dtype=int)
            times = times[idx]
            speeds = speeds[idx]
        self.speed_plot.set_data(times, speeds)

        for item in self.result_table.get_children():
            self.result_table.delete(item)
        for index, frame in enumerate(result.frames):
            self.result_table.insert(
                "",
                "end",
                values=(
                    f"{frame.timestamp_s:.3f}",
                    f"{frame.frequency_hz:.2f}",
                    f"{frame.filtered_speed_mps:.2f}",
                    f"{frame.filtered_speed_mps * 3.6:.2f}",
                    f"{frame.amplitude:.4f}",
                    f"{frame.snr_db:.2f}",
                ),
                tags=("even" if index % 2 == 0 else "odd",),
            )
        self._table_row_count = len(result.frames)
        self._syncing_views = False
        base_ratio = self.waveform_plot.get_view_ratio()
        if base_ratio is not None:
            self._sync_views_from_plot(self.waveform_plot, base_ratio)

    def export_csv(self) -> None:
        if self.current_result is None:
            messagebox.showwarning("无分析结果", "请先执行测速分析。")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="doppler_measurements.csv")
        if not save_path:
            return
        save_analysis_csv(save_path, self.current_result.frames)
        self.log(f"已导出: {save_path}")

    def _read_config(self) -> ProcessingConfig:
        sample_rate_hz = self._read_float(self.sample_rate_var, "采样率", minimum=100.0)
        carrier_frequency_ghz = self._read_float(self.carrier_freq_var, "载频", minimum=0.001)
        frame_size = self._read_int(self.frame_size_var, "帧长", minimum=256)
        overlap_ratio = self._read_float(self.overlap_var, "重叠系数", minimum=0.0, maximum=0.95)
        min_frequency_hz = self._read_float(self.min_freq_var, "最小频率", minimum=0.0)
        max_frequency_hz = self._read_float(self.max_freq_var, "最大频率", minimum=1.0)
        if max_frequency_hz <= min_frequency_hz:
            raise ValueError("最大频率必须大于最小频率。")
        return ProcessingConfig(
            sample_rate_hz=sample_rate_hz,
            carrier_frequency_hz=carrier_frequency_ghz * 1e9,
            frame_size=frame_size,
            overlap_ratio=overlap_ratio,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=max_frequency_hz,
        )

    def log(self, text: str) -> None:
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _read_float(
        self,
        variable: tk.StringVar,
        field_name: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        raw = variable.get().strip()
        if not raw:
            raise ValueError(f"{field_name}不能为空。")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{field_name}必须是数字。") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{field_name}不能小于 {minimum:g}。")
        if maximum is not None and value > maximum:
            raise ValueError(f"{field_name}不能大于 {maximum:g}。")
        return value

    def _read_int(
        self,
        variable: tk.StringVar,
        field_name: str,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        raw = variable.get().strip()
        if not raw:
            raise ValueError(f"{field_name}不能为空。")
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{field_name}必须是整数。") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{field_name}不能小于 {minimum}。")
        if maximum is not None and value > maximum:
            raise ValueError(f"{field_name}不能大于 {maximum}。")
        return value


def main() -> None:
    app = DopplerApp()
    app.mainloop()
