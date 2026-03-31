"""Square tile widget representing a single systemd unit."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import systemctl  # noqa: E402

LOADING_STATES = {"reloading", "activating", "deactivating", "maintenance"}

# Icon directory injected by the Nix derivation via environment variable
ICON_DIR = os.environ.get("SOVRAN_HUB_ICONS", "")


class ServiceTile(Gtk.Box):
    """A square tile showing a service logo, name, status, toggle, and restart."""

    def __init__(
        self,
        name: str,
        unit: str,
        scope: str = "system",
        method: str = "systemctl",
        icon_name: str = "",
        **kwargs,
    ):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            width_request=140,
            height_request=160,
            css_classes=["card", "sovran-tile"],
            margin_top=6,
            margin_bottom=6,
            margin_start=6,
            margin_end=6,
            **kwargs,
        )

        self._unit = unit
        self._scope = scope
        self._method = method
        self._name = name

        # ── Logo ──
        self._logo = Gtk.Image(
            pixel_size=48,
            margin_top=12,
            halign=Gtk.Align.CENTER,
            css_classes=["sovran-tile-icon"],
        )
        self._set_logo(icon_name)
        self.append(self._logo)

        # ── Service name ──
        label = Gtk.Label(
            label=name,
            css_classes=["heading"],
            halign=Gtk.Align.CENTER,
            ellipsize=3,  # PANGO_ELLIPSIZE_END
            max_width_chars=14,
        )
        self.append(label)

        # ── Status label ──
        self._status_label = Gtk.Label(
            css_classes=["caption"],
            halign=Gtk.Align.CENTER,
        )
        self.append(self._status_label)

        # ── Controls row (switch + restart) ──
        controls = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
            margin_bottom=8,
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

        # Initial state
        self.refresh()

    def _set_logo(self, icon_name: str):
        """Set the tile logo from a PNG in the icons dir, or fall back to a symbolic icon."""
        if icon_name and ICON_DIR:
            png_path = os.path.join(ICON_DIR, f"{icon_name}.png")
            if os.path.isfile(png_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    png_path, 48, 48, True
                )
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                self._logo.set_from_paintable(texture)
                return

        # Fallback: themed symbolic icon
        self._logo.set_from_icon_name("system-run-symbolic")

    # ── public API ──

    def refresh(self):
        """Poll systemctl and update the tile."""
        active_state = systemctl.is_active(self._unit, self._scope)
        enabled_state = systemctl.is_enabled(self._unit, self._scope)

        is_active = active_state == "active"
        is_loading = active_state in LOADING_STATES
        is_failed = active_state == "failed"

        # Block the handler so we don't trigger a start/stop
        self._switch.handler_block_by_func(self._on_toggled)
        self._switch.set_active(is_active)
        self._switch.handler_unblock_by_func(self._on_toggled)

        self._switch.set_sensitive(not is_loading)

        # Status text + color
        if is_failed:
            self._status_label.set_label("● failed")
            self._status_label.set_css_classes(["caption", "error"])
        elif is_active:
            self._status_label.set_label("● running")
            self._status_label.set_css_classes(["caption", "success"])
        elif is_loading:
            self._status_label.set_label(f"● {active_state}")
            self._status_label.set_css_classes(["caption", "warning"])
        else:
            self._status_label.set_label(f"● {active_state}")
            self._status_label.set_css_classes(["caption", "dim-label"])

    # ── signal handlers ──

    def _on_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        action = "start" if state else "stop"
        systemctl.run_action(action, self._unit, self._scope, self._method)
        GLib.timeout_add(1500, self.refresh)
        return False

    def _on_restart(self, _btn: Gtk.Button):
        systemctl.run_action("restart", self._unit, self._scope, self._method)
        GLib.timeout_add(1500, self.refresh)