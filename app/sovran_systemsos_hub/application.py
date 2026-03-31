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

# Initialize libadwaita BEFORE any widget creation
Adw.init()

# Category display order and labels
CATEGORY_ORDER = [
    ("infrastructure", "Infrastructure"),
    ("bitcoin-base",   "Bitcoin Base"),
    ("bitcoin-apps",   "Bitcoin Apps"),
    ("communication",  "Communication"),
    ("apps",           "Self-Hosted Apps"),
    ("nostr",          "Nostr"),
]

ROLE_LABELS = {
    "server_plus_desktop": "Server + Desktop",
    "desktop":             "Desktop Only",
    "node":                "Bitcoin Node",
}


class SovranHubWindow(Adw.ApplicationWindow):

    def __init__(self, app, config):
        super().__init__(
            application=app,
            title="Sovran_SystemsOS Hub",
            default_width=680,
            default_height=780,
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
        header.set_title_widget(self._build_title_box())

        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Refresh now",
        )
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

        self._main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
            child=self._main_box,
        )

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(scrolled)
        self.set_content(toolbar_view)

        self._build_tiles()

        interval = config.get("refresh_interval", 5)
        if interval and interval > 0:
            GLib.timeout_add_seconds(interval, self._auto_refresh)

    def _build_title_box(self):
        role = self._config.get("role", "server_plus_desktop")
        role_label = ROLE_LABELS.get(role, role)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
        )
        box.append(Gtk.Label(
            label="Sovran_SystemsOS Hub",
            css_classes=["title"],
        ))
        box.append(Gtk.Label(
            label=role_label,
            css_classes=["caption", "dim-label"],
        ))
        return box

    def _build_tiles(self):
        method = self._config.get("command_method", "systemctl")
        services = self._config.get("services", [])

        # Group services by category
        grouped = {}
        for entry in services:
            cat = entry.get("category", "other")
            grouped.setdefault(cat, []).append(entry)

        for cat_key, cat_label in CATEGORY_ORDER:
            entries = grouped.get(cat_key, [])
            if not entries:
                continue

            # Section header
            section_label = Gtk.Label(
                label=cat_label,
                css_classes=["title-4"],
                halign=Gtk.Align.START,
                margin_top=20,
                margin_bottom=4,
                margin_start=24,
            )
            self._main_box.append(section_label)

            sep = Gtk.Separator(
                orientation=Gtk.Orientation.HORIZONTAL,
                margin_start=24,
                margin_end=24,
                margin_bottom=8,
            )
            self._main_box.append(sep)

            flowbox = Gtk.FlowBox(
                max_children_per_line=4,
                min_children_per_line=2,
                selection_mode=Gtk.SelectionMode.NONE,
                homogeneous=True,
                row_spacing=12,
                column_spacing=12,
                margin_top=4,
                margin_bottom=8,
                margin_start=16,
                margin_end=16,
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.START,
            )

            for entry in entries:
                tile = ServiceTile(
                    name=entry.get("name", entry["unit"]),
                    unit=entry["unit"],
                    scope=entry.get("type", "system"),
                    method=method,
                    icon_name=entry.get("icon", ""),
                    enabled=entry.get("enabled", True),
                )
                flowbox.append(tile)
                self._tiles.append(tile)

            self._main_box.append(flowbox)

        GLib.idle_add(self._refresh_all)

    def _refresh_all(self):
        for t in self._tiles:
            t.refresh()
        return False

    def _auto_refresh(self):
        self._refresh_all()
        return True


class SovranHubApp(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._config = load_config()

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = SovranHubWindow(self, self._config)
        win.present()