"""Sovran_SystemsOS_Hub — Main GTK4 Application."""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .config import load_config
from .service_tile import ServiceTile

APP_ID = "com.sovransystems.hub"

Adw.init()

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

AUTOSTART_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "autostart",
)
USER_AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "sovran-hub.desktop")
SYSTEM_AUTOSTART_FILE = "/etc/xdg/autostart/sovran-hub.desktop"

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

UPDATE_COMMAND = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
    "root@localhost",
    "cd /etc/nixos && nix flake update && nixos-rebuild switch && flatpak update -y",
]

REBOOT_COMMAND = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
    "root@localhost",
    "reboot",
]


def get_autostart_enabled() -> bool:
    if os.path.isfile(USER_AUTOSTART_FILE):
        try:
            with open(USER_AUTOSTART_FILE, "r") as f:
                for line in f:
                    if line.strip().lower() == "x-gnome-autostart-enabled=false":
                        return False
                    if line.strip().lower() == "hidden=true":
                        return False
            return True
        except Exception:
            return True
    return os.path.isfile(SYSTEM_AUTOSTART_FILE)


def set_autostart_enabled(enabled: bool):
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    if enabled:
        if os.path.isfile(USER_AUTOSTART_FILE):
            os.remove(USER_AUTOSTART_FILE)
    else:
        with open(USER_AUTOSTART_FILE, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write("Type=Application\n")
            f.write("Name=Sovran_SystemsOS Hub\n")
            f.write("Exec=sovran-hub\n")
            f.write("X-GNOME-Autostart-enabled=false\n")
            f.write("Hidden=true\n")


class UpdateDialog(Adw.Window):
    """Modal window that streams the system update output."""

    def __init__(self, parent):
        super().__init__(
            title="Sovran_SystemsOS Update",
            default_width=900,
            default_height=700,
            modal=True,
            transient_for=parent,
        )

        self._process = None
        self._full_log = ""

        header = Adw.HeaderBar()

        # ── Close button (disabled during update) ────────────────
        self._close_btn = Gtk.Button(label="Close", sensitive=False)
        self._close_btn.connect("clicked", lambda _b: self.close())
        header.pack_end(self._close_btn)

        # ── Reboot button (hidden until update succeeds) ─────────
        self._reboot_btn = Gtk.Button(
            label="Reboot",
            css_classes=["destructive-action"],
            tooltip_text="Reboot the system now",
            visible=False,
        )
        self._reboot_btn.connect("clicked", self._on_reboot_clicked)
        header.pack_end(self._reboot_btn)

        # ── Save error report button (hidden until failure) ──────
        self._save_btn = Gtk.Button(
            label="Save Error Report",
            css_classes=["warning"],
            tooltip_text="Save full log to ~/Downloads",
            visible=False,
        )
        self._save_btn.connect("clicked", self._on_save_report)
        header.pack_start(self._save_btn)

        self._spinner = Gtk.Spinner(spinning=True)
        header.pack_start(self._spinner)

        self._status_label = Gtk.Label(
            label="Updating…",
            css_classes=["title-4"],
            halign=Gtk.Align.CENTER,
            margin_top=12,
            margin_bottom=8,
        )

        self._textview = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=8,
            bottom_margin=8,
            left_margin=12,
            right_margin=12,
        )
        self._buffer = self._textview.get_buffer()

        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
            child=self._textview,
        )

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        content.append(self._status_label)
        content.append(scrolled)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(content)
        self.set_content(toolbar_view)

        self._start_update()

    def _append_text(self, text):
        self._full_log += text
        end_iter = self._buffer.get_end_iter()
        self._buffer.insert(end_iter, text)
        mark = self._buffer.create_mark(None, self._buffer.get_end_iter(), False)
        self._textview.scroll_mark_onscreen(mark)
        self._buffer.delete_mark(mark)

    def _start_update(self):
        self._append_text(
            "$ ssh root@localhost 'cd /etc/nixos && nix flake update "
            "&& nixos-rebuild switch && flatpak update -y'\n\n"
        )
        thread = threading.Thread(target=self._run_update, daemon=True)
        thread.start()

    def _run_update(self):
        try:
            self._process = subprocess.Popen(
                UPDATE_COMMAND,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in self._process.stdout:
                GLib.idle_add(self._append_text, line)

            self._process.wait()
            rc = self._process.returncode

            if rc == 0:
                GLib.idle_add(self._on_finished, True, "Update complete!")
            else:
                GLib.idle_add(self._on_finished, False, f"Update failed (exit code {rc})")

        except Exception as e:
            GLib.idle_add(self._on_finished, False, f"Error: {e}")

    def _on_finished(self, success, message):
        self._spinner.set_spinning(False)
        self._close_btn.set_sensitive(True)

        if success:
            self._status_label.set_label("✓ " + message)
            self._status_label.set_css_classes(["title-4", "success"])
            self._reboot_btn.set_visible(True)
        else:
            self._status_label.set_label("✗ " + message)
            self._status_label.set_css_classes(["title-4", "error"])
            self._save_btn.set_visible(True)

        self._append_text(f"\n{'─' * 60}\n{message}\n")

    def _on_save_report(self, _btn):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"sovran-update-error-{timestamp}.log"
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        try:
            with open(filepath, "w") as f:
                f.write(f"Sovran_SystemsOS Update Error Report\n")
                f.write(f"Date: {datetime.now().isoformat()}\n")
                f.write(f"{'═' * 60}\n\n")
                f.write(self._full_log)
            self._save_btn.set_label(f"Saved: {filename}")
            self._save_btn.set_sensitive(False)
            self._append_text(f"\n✓ Error report saved to ~/Downloads/{filename}\n")
        except Exception as e:
            self._append_text(f"\n✗ Failed to save report: {e}\n")

    def _on_reboot_clicked(self, _btn):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Reboot Now?",
            body="The system will restart immediately. Save any open work first.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reboot", "Reboot")
        dialog.set_response_appearance("reboot", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_reboot_confirmed)
        dialog.present()

    def _on_reboot_confirmed(self, dialog, response):
        if response == "reboot":
            try:
                subprocess.Popen(REBOOT_COMMAND)
            except Exception as e:
                self._append_text(f"\n✗ Reboot failed: {e}\n")


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

        # ── Update button (left side, prominent) ─────────────────
        update_btn = Gtk.Button(
            label="Update System",
            css_classes=["suggested-action"],
            tooltip_text="Update Sovran_SystemsOS (flake update + rebuild + flatpak)",
        )
        update_btn.connect("clicked", self._on_update_clicked)
        header.pack_start(update_btn)

        # ── Refresh button ───────────────────────────────────────
        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Refresh now",
        )
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

        # ── Settings menu ────────────────────────────────────────
        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Settings",
        )
        popover = Gtk.Popover()
        menu_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        autostart_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )
        autostart_label = Gtk.Label(
            label="Start at login",
            hexpand=True,
            halign=Gtk.Align.START,
        )
        self._autostart_switch = Gtk.Switch(
            valign=Gtk.Align.CENTER,
            active=get_autostart_enabled(),
        )
        self._autostart_switch.connect("state-set", self._on_autostart_toggled)
        autostart_row.append(autostart_label)
        autostart_row.append(self._autostart_switch)
        menu_box.append(autostart_row)

        popover.set_child(menu_box)
        menu_btn.set_popover(popover)
        header.pack_end(menu_btn)

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

        grouped = {}
        for entry in services:
            cat = entry.get("category", "other")
            grouped.setdefault(cat, []).append(entry)

        for cat_key, cat_label in CATEGORY_ORDER:
            entries = grouped.get(cat_key, [])
            if not entries:
                continue

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

    def _on_update_clicked(self, _btn):
        dialog = UpdateDialog(self)
        dialog.present()

    def _on_autostart_toggled(self, switch, state):
        set_autostart_enabled(state)
        return False

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