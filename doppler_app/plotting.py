from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import numpy as np


class PlotCanvas(ttk.Frame):
    def __init__(self, master: tk.Misc, title: str, x_label: str, y_label: str, line_color: str) -> None:
        super().__init__(master)
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        self.line_color = line_color
        self.canvas = tk.Canvas(self, height=180, bg="#fffdf8", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._schedule_redraw)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_mouse_leave)
        self.x_data = np.array([], dtype=float)
        self.y_data = np.array([], dtype=float)
        self._redraw_job: str | None = None
        self._screen_x = np.array([], dtype=float)
        self._screen_y = np.array([], dtype=float)
        self._plot_bounds = (54.0, 30.0, 100.0, 100.0)
        self._hover_index: int | None = None

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray) -> None:
        self.x_data = np.asarray(x_data, dtype=float)
        self.y_data = np.asarray(y_data, dtype=float)
        self._hover_index = None
        self._schedule_redraw()

    def clear(self) -> None:
        self.x_data = np.array([], dtype=float)
        self.y_data = np.array([], dtype=float)
        self._screen_x = np.array([], dtype=float)
        self._screen_y = np.array([], dtype=float)
        self._hover_index = None
        self._schedule_redraw()

    def _schedule_redraw(self, _: tk.Event | None = None) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(30, self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        self.canvas.delete("all")
        width = max(10, self.canvas.winfo_width())
        height = max(10, self.canvas.winfo_height())
        self.canvas.create_text(12, 18, text=self.title, anchor="w", fill="#24313A", font=("Segoe UI Semibold", 11))
        left, top, right, bottom = 54, 30, width - 20, height - 28
        self._plot_bounds = (left, top, right, bottom)
        self.canvas.create_line(left, top, left, bottom, fill="#71808A")
        self.canvas.create_line(left, bottom, right, bottom, fill="#71808A")
        if self.x_data.size == 0 or self.y_data.size == 0:
            self.canvas.create_text((left + right) / 2, (top + bottom) / 2, text="暂无数据", fill="#7E8A90", font=("Segoe UI", 10))
            return

        x_min = float(self.x_data.min())
        x_max = float(self.x_data.max())
        y_min = float(self.y_data.min())
        y_max = float(self.y_data.max())
        if abs(x_max - x_min) < 1e-12:
            x_max = x_min + 1.0
        if abs(y_max - y_min) < 1e-12:
            y_max = y_min + 1.0

        x_pos = left + (self.x_data - x_min) / (x_max - x_min) * (right - left)
        y_pos = bottom - (self.y_data - y_min) / (y_max - y_min) * (bottom - top)
        self._screen_x = x_pos
        self._screen_y = y_pos
        points = np.column_stack((x_pos, y_pos)).ravel().tolist()
        if len(points) >= 4:
            self.canvas.create_line(*points, fill=self.line_color, width=2, smooth=False)

        if self._hover_index is not None and 0 <= self._hover_index < self.x_data.size:
            self._draw_hover_marker(self._hover_index)

    def _on_mouse_move(self, event: tk.Event) -> None:
        if self.x_data.size == 0 or self._screen_x.size == 0:
            return
        left, top, right, bottom = self._plot_bounds
        if event.x < left or event.x > right or event.y < top or event.y > bottom:
            if self._hover_index is not None:
                self._hover_index = None
                self._schedule_redraw()
            return

        distances = (self._screen_x - event.x) ** 2 + (self._screen_y - event.y) ** 2
        hover_index = int(np.argmin(distances))
        if self._hover_index != hover_index:
            self._hover_index = hover_index
            self._schedule_redraw()

    def _on_mouse_leave(self, _: tk.Event) -> None:
        if self._hover_index is not None:
            self._hover_index = None
            self._schedule_redraw()

    def _draw_hover_marker(self, index: int) -> None:
        left, top, right, bottom = self._plot_bounds
        x = float(self._screen_x[index])
        y = float(self._screen_y[index])
        x_value = float(self.x_data[index])
        y_value = float(self.y_data[index])

        self.canvas.create_line(x, top, x, bottom, fill="#C9D2D8", dash=(3, 3))
        self.canvas.create_line(left, y, right, y, fill="#C9D2D8", dash=(3, 3))
        self.canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=self.line_color, outline="")

        tooltip = f"{self.x_label}: {x_value:.3f}\n{self.y_label}: {y_value:.3f}"
        box_width = 132
        box_height = 42
        box_x = min(max(x + 10, left + 4), right - box_width)
        box_y = min(max(y - box_height - 8, top + 4), bottom - box_height)

        self.canvas.create_rectangle(
            box_x,
            box_y,
            box_x + box_width,
            box_y + box_height,
            fill="#FFF7E8",
            outline="#D9B97A",
        )
        self.canvas.create_text(
            box_x + 8,
            box_y + 8,
            text=tooltip,
            anchor="nw",
            fill="#24313A",
            font=("Consolas", 9),
        )
