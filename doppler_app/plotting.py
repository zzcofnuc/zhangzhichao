from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import numpy as np


class PlotCanvas(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        title: str,
        x_label: str,
        y_label: str,
        line_color: str,
        *,
        background: str = "#F6F1E7",
        foreground: str = "#2B2620",
        axis_color: str = "#8B8478",
        tooltip_fill: str = "#FFF3D6",
        tooltip_outline: str = "#CC9A4E",
    ) -> None:
        super().__init__(master)
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        self.line_color = line_color
        self.background = background
        self.foreground = foreground
        self.axis_color = axis_color
        self.tooltip_fill = tooltip_fill
        self.tooltip_outline = tooltip_outline
        self.canvas = tk.Canvas(self, height=180, bg=self.background, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._schedule_redraw)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_mouse_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_pan_end)
        self.canvas.bind("<Double-Button-1>", self._on_reset_view)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.x_data = np.array([], dtype=float)
        self.y_data = np.array([], dtype=float)
        self._redraw_job: str | None = None
        self._screen_x = np.array([], dtype=float)
        self._screen_y = np.array([], dtype=float)
        self._plot_bounds = (54.0, 30.0, 100.0, 100.0)
        self._navigator_bounds = (54.0, 100.0, 100.0, 116.0)
        self._navigator_view_bounds = (54.0, 100.0, 100.0, 116.0)
        self._hover_index: int | None = None
        self._view_x_range: tuple[float, float] | None = None
        self._view_y_range: tuple[float, float] | None = None
        self._visible_x_data = np.array([], dtype=float)
        self._visible_y_data = np.array([], dtype=float)
        self._drag_start: tuple[int, int] | None = None
        self._drag_mode: str | None = None
        self.on_view_changed: Callable[[tuple[float, float]], None] | None = None
        self._marker_x: float | None = None
        self._marker_label: str | None = None
        self._marker_color = "#B03A2E"

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray) -> None:
        self.x_data = np.asarray(x_data, dtype=float)
        self.y_data = np.asarray(y_data, dtype=float)
        self._hover_index = None
        self._reset_view_state()
        self._schedule_redraw()

    def clear(self) -> None:
        self.x_data = np.array([], dtype=float)
        self.y_data = np.array([], dtype=float)
        self._screen_x = np.array([], dtype=float)
        self._screen_y = np.array([], dtype=float)
        self._hover_index = None
        self._view_x_range = None
        self._view_y_range = None
        self._drag_start = None
        self._schedule_redraw()

    def set_marker(self, x_value: float | None, label: str | None = None, *, color: str | None = None) -> None:
        self._marker_x = None if x_value is None else float(x_value)
        self._marker_label = label
        if color is not None:
            self._marker_color = color
        self._schedule_redraw()

    def get_view_ratio(self) -> tuple[float, float] | None:
        if self.x_data.size == 0 or self._view_x_range is None:
            return None
        global_x_min = float(self.x_data.min())
        global_x_max = float(self.x_data.max())
        global_span = global_x_max - global_x_min
        if global_span <= 1e-12:
            return (0.0, 1.0)
        x_min, x_max = self._view_x_range
        start_ratio = (x_min - global_x_min) / global_span
        end_ratio = (x_max - global_x_min) / global_span
        return (float(np.clip(start_ratio, 0.0, 1.0)), float(np.clip(end_ratio, 0.0, 1.0)))

    def set_view_ratio(self, start_ratio: float, end_ratio: float, *, notify: bool = False) -> None:
        if self.x_data.size == 0:
            return
        start_ratio = float(np.clip(start_ratio, 0.0, 1.0))
        end_ratio = float(np.clip(end_ratio, 0.0, 1.0))
        if end_ratio - start_ratio <= 1e-6:
            end_ratio = min(1.0, start_ratio + 1e-6)

        global_x_min = float(self.x_data.min())
        global_x_max = float(self.x_data.max())
        global_span = global_x_max - global_x_min
        if global_span <= 1e-12:
            self._view_x_range = (global_x_min, global_x_max + 1.0)
        else:
            self._view_x_range = (
                global_x_min + start_ratio * global_span,
                global_x_min + end_ratio * global_span,
            )
        self._schedule_redraw()
        if notify:
            self._notify_view_changed()

    def _schedule_redraw(self, _: tk.Event | None = None) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(30, self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        self.canvas.delete("all")
        width = max(10, self.canvas.winfo_width())
        height = max(10, self.canvas.winfo_height())
        self.canvas.create_rectangle(0, 0, width, height, fill=self.background, outline="")
        self.canvas.create_rectangle(8, 8, width - 8, height - 8, outline="#D8CEBD", width=1)
        self.canvas.create_text(18, 20, text=self.title, anchor="w", fill=self.foreground, font=("Georgia", 12, "bold"))
        left, top = 64, 34
        right = max(left + 40, width - 20)
        bottom = max(top + 40, height - 56)
        self._plot_bounds = (left, top, right, bottom)
        nav_top = max(bottom + 8, height - 34)
        nav_bottom = max(nav_top + 12, height - 18)
        self._navigator_bounds = (left, nav_top, right, nav_bottom)
        self.canvas.create_line(left, top, left, bottom, fill=self.axis_color)
        self.canvas.create_line(left, bottom, right, bottom, fill=self.axis_color)
        self.canvas.create_text(22, (top + bottom) / 2, text=self.y_label, angle=90, anchor="center", fill="#756B5B", font=("Segoe UI", 8))
        self.canvas.create_text((left + right) / 2, height - 6, text=self.x_label, anchor="s", fill="#756B5B", font=("Segoe UI", 8))
        if self.x_data.size == 0 or self.y_data.size == 0:
            self.canvas.create_text((left + right) / 2, (top + bottom) / 2, text="暂无数据", fill="#8A8177", font=("Segoe UI", 10))
            return

        if self._view_x_range is None or self._view_y_range is None:
            self._reset_view_state()
        x_min, x_max = self._view_x_range
        global_y_min, global_y_max = self._view_y_range
        if abs(x_max - x_min) < 1e-12:
            x_max = x_min + 1.0

        visible_x_mask = (self.x_data >= x_min) & (self.x_data <= x_max)
        plot_x = self.x_data[visible_x_mask]
        plot_y = self.y_data[visible_x_mask]
        if plot_x.size == 0:
            plot_x = self.x_data
            plot_y = self.y_data

        y_min = float(plot_y.min())
        y_max = float(plot_y.max())
        if abs(y_max - y_min) < 1e-12:
            y_max = y_min + 1.0
        y_padding = 0.08 * (y_max - y_min)
        y_min -= y_padding
        y_max += y_padding

        visible_mask = (plot_y >= y_min) & (plot_y <= y_max)
        plot_x = plot_x[visible_mask]
        plot_y = plot_y[visible_mask]
        if plot_x.size == 0:
            plot_x = self.x_data[visible_x_mask]
            plot_y = self.y_data[visible_x_mask]

        x_pos = left + (plot_x - x_min) / (x_max - x_min) * (right - left)
        y_pos = bottom - (plot_y - y_min) / (y_max - y_min) * (bottom - top)
        self._screen_x = x_pos
        self._screen_y = y_pos
        self._visible_x_data = plot_x
        self._visible_y_data = plot_y
        points = np.column_stack((x_pos, y_pos)).ravel().tolist()
        if len(points) >= 4:
            self.canvas.create_line(*points, fill=self.line_color, width=2, smooth=False)

        self._draw_marker(left, top, right, bottom, x_min, x_max)

        self._draw_navigator(left, nav_top, right, nav_bottom, x_min, x_max, global_y_min, global_y_max)

        if self._hover_index is not None and 0 <= self._hover_index < self._visible_x_data.size:
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
        x_value = float(self._visible_x_data[index])
        y_value = float(self._visible_y_data[index])

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
            fill=self.tooltip_fill,
            outline=self.tooltip_outline,
        )
        self.canvas.create_text(
            box_x + 8,
            box_y + 8,
            text=tooltip,
            anchor="nw",
            fill=self.foreground,
            font=("Consolas", 9),
        )

    def _draw_marker(self, left: float, top: float, right: float, bottom: float, x_min: float, x_max: float) -> None:
        if self._marker_x is None or self.x_data.size == 0:
            return
        if self._marker_x < x_min or self._marker_x > x_max or abs(x_max - x_min) < 1e-12:
            return

        marker_x = left + (self._marker_x - x_min) / (x_max - x_min) * (right - left)
        self.canvas.create_line(marker_x, top, marker_x, bottom, fill=self._marker_color, width=2, dash=(6, 4))
        self.canvas.create_polygon(
            marker_x,
            top + 4,
            marker_x - 6,
            top + 16,
            marker_x + 6,
            top + 16,
            fill=self._marker_color,
            outline="",
        )
        label = self._marker_label or f"{self._marker_x:.2f}"
        label_width = max(96, min(180, 14 + int(len(label) * 7)))
        label_left = min(max(marker_x - label_width / 2, left + 4), right - label_width - 4)
        label_top = top + 6
        self.canvas.create_rectangle(
            label_left,
            label_top,
            label_left + label_width,
            label_top + 22,
            fill="#FFF1DD",
            outline=self._marker_color,
            width=1,
        )
        self.canvas.create_text(
            label_left + label_width / 2,
            label_top + 11,
            text=label,
            fill=self.foreground,
            font=("Segoe UI Semibold", 9),
        )

    def _reset_view_state(self) -> None:
        if self.x_data.size == 0 or self.y_data.size == 0:
            self._view_x_range = None
            self._view_y_range = None
            return
        x_min = float(self.x_data.min())
        x_max = float(self.x_data.max())
        y_min = float(self.y_data.min())
        y_max = float(self.y_data.max())
        if abs(x_max - x_min) < 1e-12:
            x_max = x_min + 1.0
        if abs(y_max - y_min) < 1e-12:
            y_max = y_min + 1.0
        y_padding = 0.08 * (y_max - y_min)
        self._view_x_range = (x_min, x_max)
        self._view_y_range = (y_min - y_padding, y_max + y_padding)
        self._drag_mode = None
        self._notify_view_changed()

    def _on_zoom(self, event: tk.Event) -> None:
        if self.x_data.size == 0 or self._view_x_range is None or self._view_y_range is None:
            return
        left, top, right, bottom = self._plot_bounds
        if event.x < left or event.x > right or event.y < top or event.y > bottom:
            return

        zoom_factor = 0.88 if event.delta > 0 else 1.14
        x_min, x_max = self._view_x_range
        x_anchor = x_min + (event.x - left) / max(1.0, (right - left)) * (x_max - x_min)
        new_x_span = max(1e-6, (x_max - x_min) * zoom_factor)

        new_range = (
            x_anchor - (x_anchor - x_min) * zoom_factor,
            x_anchor + (x_max - x_anchor) * zoom_factor,
        )
        if new_range[1] - new_range[0] > new_x_span * 4:
            new_range = (x_min, x_max)
        self._set_view_x_range(new_range)

    def _on_pan_start(self, event: tk.Event) -> None:
        left, top, right, bottom = self._plot_bounds
        nav_left, nav_top, nav_right, nav_bottom = self._navigator_bounds
        if left <= event.x <= right and top <= event.y <= bottom:
            self._drag_start = (event.x, event.y)
            self._drag_mode = "plot"
        elif nav_left <= event.x <= nav_right and nav_top <= event.y <= nav_bottom:
            view_left, _, view_right, _ = self._navigator_view_bounds
            if view_left - 10 <= event.x <= view_right + 10:
                self._drag_start = (event.x, event.y)
                self._drag_mode = "navigator"

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._drag_start is None or self._view_x_range is None or self._view_y_range is None:
            return
        start_x, start_y = self._drag_start
        dx = event.x - start_x
        dy = event.y - start_y
        x_min, x_max = self._view_x_range
        if self._drag_mode == "plot":
            left, top, right, bottom = self._plot_bounds
            x_span = x_max - x_min
            if right > left:
                shift_x = -dx / (right - left) * x_span
                self._set_view_x_range((x_min + shift_x, x_max + shift_x), schedule=False)
        elif self._drag_mode == "navigator":
            nav_left, _, nav_right, _ = self._navigator_bounds
            global_x_min = float(self.x_data.min())
            global_x_max = float(self.x_data.max())
            global_span = max(1e-9, global_x_max - global_x_min)
            window_span = x_max - x_min
            if nav_right > nav_left:
                shift_x = dx / (nav_right - nav_left) * global_span
                new_min = x_min + shift_x
                new_max = new_min + window_span
                if new_min < global_x_min:
                    new_min = global_x_min
                    new_max = new_min + window_span
                if new_max > global_x_max:
                    new_max = global_x_max
                    new_min = new_max - window_span
                self._set_view_x_range((new_min, new_max), schedule=False)
        self._drag_start = (event.x, event.y)
        self._schedule_redraw()

    def _on_pan_end(self, _: tk.Event) -> None:
        self._drag_start = None
        self._drag_mode = None

    def _on_reset_view(self, _: tk.Event) -> None:
        self._reset_view_state()
        self._schedule_redraw()

    def _draw_navigator(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        current_x_min: float,
        current_x_max: float,
        global_y_min: float,
        global_y_max: float,
    ) -> None:
        self.canvas.create_rectangle(left, top, right, bottom, fill="#EFE4D4", outline="#CBBEAA")
        global_x_min = float(self.x_data.min())
        global_x_max = float(self.x_data.max())
        global_x_span = max(1e-9, global_x_max - global_x_min)
        global_y_span = max(1e-9, global_y_max - global_y_min)

        nav_x = left + (self.x_data - global_x_min) / global_x_span * (right - left)
        nav_y = bottom - (self.y_data - global_y_min) / global_y_span * (bottom - top)
        nav_points = np.column_stack((nav_x, nav_y)).ravel().tolist()
        if len(nav_points) >= 4:
            self.canvas.create_line(*nav_points, fill="#B2906A", width=1, smooth=False)

        view_left = left + (current_x_min - global_x_min) / global_x_span * (right - left)
        view_right = left + (current_x_max - global_x_min) / global_x_span * (right - left)
        self._navigator_view_bounds = (view_left, top, view_right, bottom)
        self.canvas.create_rectangle(
            view_left,
            top + 1,
            view_right,
            bottom - 1,
            fill="#E8B384",
            outline="#C76632",
            width=2,
        )
        handle_width = 6
        self.canvas.create_rectangle(view_left, top + 1, min(view_left + handle_width, view_right), bottom - 1, fill="#C76632", outline="")
        self.canvas.create_rectangle(max(view_right - handle_width, view_left), top + 1, view_right, bottom - 1, fill="#C76632", outline="")
        grip_y = (top + bottom) / 2
        grip_center = (view_left + view_right) / 2
        self.canvas.create_line(grip_center - 8, grip_y, grip_center + 8, grip_y, fill="#7A3517", width=2)
        self.canvas.create_line(grip_center - 8, grip_y - 3, grip_center + 8, grip_y - 3, fill="#7A3517", width=1)

    def _set_view_x_range(self, view_range: tuple[float, float], *, schedule: bool = True) -> None:
        if self.x_data.size == 0:
            return
        global_x_min = float(self.x_data.min())
        global_x_max = float(self.x_data.max())
        global_span = global_x_max - global_x_min
        if global_span <= 1e-12:
            self._view_x_range = (global_x_min, global_x_max + 1.0)
            if schedule:
                self._schedule_redraw()
            self._notify_view_changed()
            return

        requested_min, requested_max = view_range
        min_window = global_span / max(1000.0, float(self.x_data.size))
        window_span = max(min_window, requested_max - requested_min)
        window_span = min(window_span, global_span)
        new_min = requested_min
        new_max = requested_min + window_span

        if new_min < global_x_min:
            new_min = global_x_min
            new_max = new_min + window_span
        if new_max > global_x_max:
            new_max = global_x_max
            new_min = new_max - window_span
        if new_min < global_x_min:
            new_min = global_x_min

        self._view_x_range = (new_min, new_max)
        if schedule:
            self._schedule_redraw()
        self._notify_view_changed()

    def _notify_view_changed(self) -> None:
        if self.on_view_changed is None:
            return
        ratio = self.get_view_ratio()
        if ratio is not None:
            self.on_view_changed(ratio)
