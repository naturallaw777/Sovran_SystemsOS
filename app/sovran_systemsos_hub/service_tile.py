"""Square tile widget representing a single systemd unit."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from . import systemctl

LOADING_STATES = {"reloading", "activating", "deactivating", "maintenance"}

ICON_DIR = os.environ.get("SOVRAN_HUB_ICONS", "")
ICON_EXTENSIONS = [".svg", ".png"]

TILE_SIZE = 140


class ServiceTile(Gtk.Box):

    def __init__(self, name, unit, scope="system", method="systemctl",
                 icon_name="", enabled=True, **kw):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            css_classes=["card", "sovran-tile"],
            **kw,
        )
        # Force exact tile dimensions
        self.set_size_request(TILE_SIZE, TILE_SIZE + 30)
        self.set_hexpand(False)
        self.set_vexpand(False)

        self._unit = unit
        self._scope = scope
        self._method = method
        self._enabled = enabled

        # ── Icon ─────────────────────────────────────────────────
        self._logo = Gtk.Image(
            pixel_size=36,
            margin_top=14,
            halign=Gtk.Align.CENTER,
        )
        self._set_logo(icon_name)
        self.append(self._logo)

        # ── Name label (wraps within tile width) ─────────────────
        self._name_label = Gtk.Label(
            label=name,
            css_classes=["heading", "tile-name"],
            halign=Gtk.Align.CENTER,
            justify=Gtk.Justification.CENTER,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            lines=2,
            ellipsize=Pango.EllipsizeMode.END,
            margin_start=6,
            margin_end=6,
            margin_top=4,
        )
        # Clamp the label width so it wraps inside the tile
        self._name_label.set_size_request(TILE_SIZE - 16, -1)
        self._name_label.set_max_width_chars(1)  # forces natural width to be small
        self.append(self._name_label)

        # ── Status label ─────────────────────────────────────────
        self._status_label = Gtk.Label(
            label="● …",
            css_classes=["caption", "dim-label"],
            halign=Gtk.Align.CENTER,
            margin_top=1,
        )
        self.append(self._status_label)

        # ── Spacer ───────────────────────────────────────────────
        spacer = Gtk.Box(vexpand=True)
        self.append(spacer)

        # ── Controls ─────────────────────────────────────────────
        controls = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
            margin_bottom=10,
        )
        self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._switch.connect("state-set", self._on_toggled)
        controls.append(self._switch)

        restart_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            valign=Gtk.Align.CENTER,
            tooltip_text="Restart",
            css_classes=["flat", "circular"],
        )
        restart_btn.connect("clicked", self._on_restart)
        controls.append(restart_btn)
        self.append(controls)

        # If the feature is disabled in custom.nix, lock the tile
        if not self._enabled:
            self._switch.set_active(False)
            self._switch.set_sensitive(False)
            self._status_label.set_label("○ disabled")
            self._status_label.set_css_classes(["caption", "disabled-label"])
            self._logo.set_opacity(0.35)
            self.set_tooltip_text(f"{name} is not enabled in custom.nix")

    def _set_logo(self, icon_name):
        if icon_name and ICON_DIR:
            for ext in ICON_EXTENSIONS:
                path = os.path.join(ICON_DIR, f"{icon_name}{ext}")
                if os.path.isfile(path):
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 36, 36, True)
                        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                        self._logo.set_from_paintable(texture)
                        return
                    except Exception:
                        break
        self._logo.set_from_icon_name("system-run-symbolic")

    def refresh(self):
        if not self._enabled:
            return

        active = systemctl.is_active(self._unit, self._scope)
        is_on = active == "active"
        is_loading = active in LOADING_STATES
        is_failed = active == "failed"

        self._switch.handler_block_by_func(self._on_toggled)
        self._switch.set_active(is_on)
        self._switch.handler_unblock_by_func(self._on_toggled)
        self._switch.set_sensitive(not is_loading)

        if is_failed:
            self._status_label.set_label("● failed")
            self._status_label.set_css_classes(["caption", "error"])
        elif is_on:
            self._status_label.set_label("● running")
            self._status_label.set_css_classes(["caption", "success"])
        elif is_loading:
            self._status_label.set_label(f"● {active}")
            self._status_label.set_css_classes(["caption", "warning"])
        else:
            self._status_label.set_label(f"● {active}")
            self._status_label.set_css_classes(["caption", "dim-label"])

    def _on_toggled(self, switch, state):
        if not self._enabled:
            return True
        systemctl.run_action("start" if state else "stop", self._unit, self._scope, self._method)
        GLib.timeout_add(1500, self.refresh)
        return False

    def _on_restart(self, _btn):
        if not self._enabled:
            return
        systemctl.run_action("restart", self._unit, self._scope, self._method)
        GLib.timeout_add(1500, self.refresh)