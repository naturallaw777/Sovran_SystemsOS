"""Sovran_SystemsOS_Hub — Main GTK4 Application."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .config import load_config  # noqa: E402
from .service_row import ServiceRow  # noqa: E402

APP_ID = "com.sovransystems.hub"


class SovranHubWindow(Adw.ApplicationWindow):
    """Primary window: a list of service rows with auto-refresh."""

    def __init__(self, app: Adw.Application, config: dict):
        super().__init__(
            application=app,
            title="Sovran_SystemsOS Hub",
            default_width=560,
            default_height=620,
        )
        self._config = config
        self._rows: list[ServiceRow] = []

        # ── Header bar ──
        header = Adw.HeaderBar()

        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Refresh now",
        )
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

        # ── Content ──
        self._group = Adw.PreferencesGroup(title="Services")

        page = Adw.PreferencesPage()
        page.add(self._group)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(page)

        self.set_content(toolbar_view)

        # ── Populate ──
        self._build_rows()
        self._start_auto_refresh()

    def _build_rows(self):
        """Create ServiceRow widgets from config."""
        for entry in self._config.get("services", []):
            row = ServiceRow(
                name=entry.get("name", entry["unit"]),
                unit=entry["unit"],
                scope=entry.get("type", "system"),
                method=self._config.get("command_method", "systemctl"),
            )
            self._group.add(row)
            self._rows.append(row)

    def _refresh_all(self):
        for row in self._rows:
            row.refresh()

    def _start_auto_refresh(self):
        interval = self._config.get("refresh_interval", 5)
        if interval and interval > 0:
            GLib.timeout_add_seconds(interval, self._auto_refresh_cb)

    def _auto_refresh_cb(self) -> bool:
        self._refresh_all()
        return True  # keep the timer alive


class SovranHubApp(Adw.Application):
    """Sovran_SystemsOS_Hub Adw.Application."""

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