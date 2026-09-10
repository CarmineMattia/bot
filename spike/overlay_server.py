"""GTK4 overlay process (docs/overlay.md).

Reads JSON lines from stdin:
  {"cmd":"show","status":"...","phase":"announce","target":{"kind":"point","x":1,"y":2}}
  {"cmd":"clear","reason":"done"}

Prefers Gtk4LayerShell when the compositor supports it (Sway/KDE/…).
On GNOME Mutter (no zwlr_layer_shell), falls back to a fullscreen transparent
window with an empty input region (click-through).
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

_HAS_LAYER = False
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell  # noqa: E402

    _HAS_LAYER = True
except (ValueError, ImportError):
    Gtk4LayerShell = None  # type: ignore[misc, assignment]


PHASE_COLORS = {
    "announce": (0.15, 0.75, 0.95, 0.95),
    "acting": (0.95, 0.75, 0.15, 0.95),
    "done": (0.25, 0.85, 0.35, 0.95),
    "cancelled": (0.7, 0.7, 0.7, 0.9),
    "failed": (0.95, 0.25, 0.25, 0.95),
}


class OverlayApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="local.bot.overlay")
        self._status = ""
        self._phase = "announce"
        self._target: dict[str, Any] | None = None
        self._visible = False
        self._window: Gtk.Window | None = None
        self._area: Gtk.DrawingArea | None = None
        self._clear_source: int | None = None
        self._mode = "fallback"

    def do_activate(self) -> None:  # noqa: N802
        if self._window:
            return

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window.bot-overlay {
              background-color: transparent;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = Gtk.ApplicationWindow(application=self)
        win.add_css_class("bot-overlay")
        win.set_decorated(False)
        win.set_resizable(True)
        win.set_title("bot-overlay")

        use_layer = bool(
            _HAS_LAYER and Gtk4LayerShell is not None and Gtk4LayerShell.is_supported()
        )
        if use_layer:
            self._mode = "layer-shell"
            Gtk4LayerShell.init_for_window(win)
            Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
            Gtk4LayerShell.set_namespace(win, "bot-overlay")
            Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, True)
            Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.BOTTOM, True)
            Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.LEFT, True)
            Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.RIGHT, True)
            Gtk4LayerShell.set_exclusive_zone(win, -1)
            Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)
        else:
            self._mode = "fullscreen-fallback"
            # GNOME Mutter: no zwlr_layer_shell — cover the primary monitor.
            display = Gdk.Display.get_default()
            monitor = display.get_monitors().get_item(0) if display else None
            if monitor is not None:
                geo = monitor.get_geometry()
                win.set_default_size(geo.width, geo.height)
            else:
                win.set_default_size(1920, 1080)
            win.fullscreen()

        print(f"overlay_mode={self._mode}", file=sys.stderr, flush=True)

        area = Gtk.DrawingArea()
        area.set_hexpand(True)
        area.set_vexpand(True)
        area.set_draw_func(self._draw)
        win.set_child(area)

        win.connect("realize", self._on_realize)
        self._window = win
        self._area = area
        win.present()
        GLib.idle_add(self._hide_surface)
        GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, self._on_stdin)

    def _on_realize(self, win: Gtk.Window) -> None:
        surface = win.get_surface()
        if surface is None:
            return
        try:
            import cairo

            surface.set_input_region(cairo.Region())
        except Exception as e:
            print(f"input_region: {e}", file=sys.stderr, flush=True)

    def _hide_surface(self) -> bool:
        if self._window:
            self._window.set_visible(False)
        self._visible = False
        return False

    def _show_surface(self) -> None:
        if self._window:
            self._window.set_visible(True)
            if self._mode == "fullscreen-fallback":
                self._window.fullscreen()
            self._window.present()
            # Re-apply empty input region after present (compositor may reset).
            GLib.idle_add(self._reapply_input_region)
        self._visible = True

    def _reapply_input_region(self) -> bool:
        if self._window:
            self._on_realize(self._window)
        return False

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:  # noqa: ANN001
        import cairo

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if not self._visible and not self._status:
            return

        color = PHASE_COLORS.get(self._phase, PHASE_COLORS["announce"])

        bar_h = 44
        cr.set_source_rgba(0.05, 0.07, 0.1, 0.82)
        cr.rectangle(0, height - bar_h, width, bar_h)
        cr.fill()
        cr.set_source_rgba(*color)
        cr.rectangle(0, height - bar_h, 6, bar_h)
        cr.fill()

        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(16)
        label = f"[{self._phase}] {self._status}"
        cr.move_to(18, height - 16)
        cr.show_text(label[:120])

        tgt = self._target
        if not tgt:
            return
        kind = tgt.get("kind")
        if kind == "point":
            x, y = float(tgt.get("x", 0)), float(tgt.get("y", 0))
            self._crosshair(cr, x, y, color)
        elif kind == "rect":
            x, y = float(tgt.get("x", 0)), float(tgt.get("y", 0))
            w, h = float(tgt.get("w", 0)), float(tgt.get("h", 0))
            cr.set_source_rgba(*color[:3], 0.35)
            cr.rectangle(x, y, w, h)
            cr.fill()
            cr.set_source_rgba(*color)
            cr.set_line_width(2)
            cr.rectangle(x, y, w, h)
            cr.stroke()
            self._crosshair(cr, x + w / 2, y + h / 2, color)

    def _crosshair(self, cr, x: float, y: float, color: tuple) -> None:  # noqa: ANN001
        size = 18
        cr.set_source_rgba(*color)
        cr.set_line_width(2)
        cr.move_to(x - size, y)
        cr.line_to(x + size, y)
        cr.move_to(x, y - size)
        cr.line_to(x, y + size)
        cr.stroke()
        cr.arc(x, y, 6, 0, 2 * math.pi)
        cr.stroke()

    def _on_stdin(self, _source, condition) -> bool:  # noqa: ANN001
        if condition & GLib.IO_HUP:
            self.quit()
            return False
        line = sys.stdin.readline()
        if not line:
            self.quit()
            return False
        line = line.strip()
        if not line:
            return True
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"bad json: {e}", file=sys.stderr, flush=True)
            return True
        self._handle(msg)
        return True

    def _handle(self, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        if self._clear_source is not None:
            GLib.source_remove(self._clear_source)
            self._clear_source = None

        if cmd == "show":
            self._status = str(msg.get("status") or "")
            self._phase = str(msg.get("phase") or "announce")
            self._target = msg.get("target")
            self._show_surface()
            if self._area:
                self._area.queue_draw()
            if self._phase in {"done", "failed", "cancelled"}:
                delay = 700 if self._phase == "done" else 1200

                def _later() -> bool:
                    self._handle({"cmd": "clear", "reason": self._phase})
                    return False

                self._clear_source = GLib.timeout_add(delay, _later)
        elif cmd == "clear":
            self._status = ""
            self._target = None
            self._phase = "announce"
            if self._window:
                self._window.set_visible(False)
            self._visible = False
            if self._area:
                self._area.queue_draw()
        else:
            print(f"unknown cmd: {cmd}", file=sys.stderr, flush=True)


def main() -> int:
    app = OverlayApp()
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
