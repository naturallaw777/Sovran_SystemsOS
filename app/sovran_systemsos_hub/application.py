"""Sovran_SystemsOS_Hub — Main GTK4 Application."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .config import load_config
from .service_tile import ServiceTile

APP_ID = "com.sovransystems.hub"


class SovranHubWindow(Adw.ApplicationWindow):

    def __init__(self, app, config):
        super().__init__(
            application=app, title="Sovran_SystemsOS Hub",
            default_width=680, default_height=700,
        )
        self._config = config
        self._tiles = []

        css_path = os.environ.get("SOVRAN_HUB_CSS", "")
        if css_path and os.path.isfile(css_path):
            provider = Gtk.CssProvider()
            provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        header = Adw.HeaderBar()
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh now")
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

        self._flowbox = Gtk.FlowBox(
            max_children_per_line=4, min_children_per_line=2,
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
            row_spacing=12, column_spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.START,
        )

        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True, child=self._flowbox,
        )

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(scrolled)
        self.set_content(toolbar_view)

        self._build_tiles()
        interval = config.get("refresh_interval", 5)
        if interval and interval > 0:
            GLib.timeout_add_seconds(interval, self._auto_refresh)

    def _build_tiles(self):
        for entry in self._config.get("services", []):
            tile = ServiceTile(
                name=entry.get("name", entry["unit"]),
                unit=entry["unit"],
                scope=entry.get("type", "system"),
                method=self._config.get("command_method", "systemctl"),
                icon_name=entry.get("icon", ""),
            )
            self._flowbox.append(tile)
            self._tiles.append(tile)

    def _refresh_all(self):
        for t in self._tiles:
            t.refresh()

    def _auto_refresh(self):
        self._refresh_all()
        return True


class SovranHubApp(Adw.Application):

    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._config = load_config()

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = SovranHubWindow(self, self._config)
        win.present()