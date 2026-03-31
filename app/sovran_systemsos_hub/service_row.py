"""Adw.ActionRow subclass representing a single systemd unit."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import systemctl  # noqa: E402

LOADING_STATES = {"reloading", "activating", "deactivating", "maintenance"}


class ServiceRow(Adw.ActionRow):
    """A row showing one systemd unit with a toggle switch and action buttons."""

    def __init__(
        self,
        name: str,
        unit: str,
        scope: str = "system",
        method: str = "systemctl",
        **kwargs,
    ):
        super().__init__(title=name, subtitle=unit, **kwargs)
        self._unit = unit
        self._scope = scope
        self._method = method

        # ── Active / Inactive switch ──
        self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._switch.connect("state-set", self._on_toggled)
        self.add_suffix(self._switch)
        self.set_activatable_widget(self._switch)

        # ── Restart button ──
        restart_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            valign=Gtk.Align.CENTER,
            tooltip_text="Restart",
            css_classes=["flat"],
        )
        restart_btn.connect("clicked", self._on_restart)
        self.add_suffix(restart_btn)

        # ── Status pill ──
        self._status_label = Gtk.Label(
            css_classes=["caption", "dim-label"],
            valign=Gtk.Align.CENTER,
            margin_end=4,
        )
        self.add_suffix(self._status_label)

        # Initial state
        self.refresh()

    # ── public API ──

    def refresh(self):
        """Poll systemctl and update the row."""
        active_state = systemctl.is_active(self._unit, self._scope)
        enabled_state = systemctl.is_enabled(self._unit, self._scope)

        is_active = active_state == "active"
        is_loading = active_state in LOADING_STATES
        is_failed = active_state == "failed"

        # Block the handler so we don't trigger a start/stop when we
        # programmatically flip the switch.
        self._switch.handler_block_by_func(self._on_toggled)
        self._switch.set_active(is_active)
        self._switch.handler_unblock_by_func(self._on_toggled)

        self._switch.set_sensitive(not is_loading)

        # Status text
        label = enabled_state
        if is_failed:
            label = "failed"
        elif is_loading:
            label = active_state
        self._status_label.set_label(label)

        # Visual cue for failures
        if is_failed:
            self.add_css_class("error")
        else:
            self.remove_css_class("error")

    # ── signal handlers ──

    def _on_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        action = "start" if state else "stop"
        systemctl.run_action(action, self._unit, self._scope, self._method)
        # Delay refresh so systemd has a moment to change state
        GLib.timeout_add(1500, self.refresh)
        return False  # let GTK update the switch position

    def _on_restart(self, _btn: Gtk.Button):
        systemctl.run_action("restart", self._unit, self._scope, self._method)
        GLib.timeout_add(1500, self.refresh)