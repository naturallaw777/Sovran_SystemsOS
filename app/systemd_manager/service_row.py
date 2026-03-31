from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk
from . import systemctl

LOADING_STATES = {"reloading", "activating", "deactivating", "maintenance"}
REFRESH_DELAY_MS = 1500


class ServiceRow(Adw.ActionRow):
    def __init__(self, name, unit, scope="system", method="systemctl", **kw):
        super().__init__(title=name, subtitle=unit, **kw)
        self._unit = unit
        self._scope = scope
        self._method = method

        self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._switch.connect("state-set", self._on_toggled)
        self.add_suffix(self._switch)
        self.set_activatable_widget(self._switch)

        restart_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                                 tooltip_text="Restart", css_classes=["flat"])
        restart_btn.connect("clicked", self._on_restart)
        self.add_suffix(restart_btn)

        self._status_label = Gtk.Label(css_classes=["caption", "dim-label"],
                                       valign=Gtk.Align.CENTER, margin_end=4)
        self.add_suffix(self._status_label)
        self.refresh()

    def refresh(self):
        active_state = systemctl.is_active(self._unit, self._scope)
        enabled_state = systemctl.is_enabled(self._unit, self._scope)
        is_active = active_state == "active"
        is_loading = active_state in LOADING_STATES
        is_failed = active_state == "failed"

        self._switch.handler_block_by_func(self._on_toggled)
        self._switch.set_active(is_active)
        self._switch.handler_unblock_by_func(self._on_toggled)
        self._switch.set_sensitive(not is_loading)

        label = enabled_state
        if is_failed:
            label = "failed"
        elif is_loading:
            label = active_state
        self._status_label.set_label(label)

        if is_failed:
            self.add_css_class("error")
        else:
            self.remove_css_class("error")

    def _on_toggled(self, switch, state):
        action = "start" if state else "stop"
        systemctl.run_action(action, self._unit, self._scope, self._method)
        GLib.timeout_add(REFRESH_DELAY_MS, self.refresh)
        return False

    def _on_restart(self, _btn):
        systemctl.run_action("restart", self._unit, self._scope, self._method)
        GLib.timeout_add(REFRESH_DELAY_MS, self.refresh)
