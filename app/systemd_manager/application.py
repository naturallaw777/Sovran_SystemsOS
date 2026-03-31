from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk
from .config import load_config
from .service_row import ServiceRow

APP_ID = "com.sovransystems.systemd-manager"


class SystemdManagerWindow(Adw.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Systemd Manager",
                         default_width=560, default_height=620)
        self._config = config
        self._rows = []

        header = Adw.HeaderBar()
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh now")
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

        self._group = Adw.PreferencesGroup(title="Services")
        page = Adw.PreferencesPage()
        page.add(self._group)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(page)
        self.set_content(toolbar_view)

        self._build_rows()
        interval = config.get("refresh_interval", 5)
        if interval and interval > 0:
            GLib.timeout_add_seconds(interval, self._auto_refresh)

    def _build_rows(self):
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

    def _auto_refresh(self):
        self._refresh_all()
        return True


class SystemdManagerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._config = load_config()

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = SystemdManagerWindow(self, self._config)
        win.present()
