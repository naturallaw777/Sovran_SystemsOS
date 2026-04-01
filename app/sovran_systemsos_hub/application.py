"""Sovran_SystemsOS_Hub — Main GTK4 Application."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import urllib.request
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

FLAKE_LOCK_PATH = "/etc/nixos/flake.lock"
FLAKE_INPUT_NAME = "Sovran_Systems"

GITEA_API_BASE = "https://git.sovransystems.com/api/v1/repos/Sovran_Systems/Sovran_SystemsOS/commits"

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

UPDATE_CHECK_INTERVAL = 1800

TILE_GRID_WIDTH = 640


# ── Autostart helpers ────────────────────────────────────────────

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


# ── Update check helpers ────────────────────────────────────────

def _get_locked_info():
    try:
        with open(FLAKE_LOCK_PATH, "r") as f:
            lock = json.load(f)
        nodes = lock.get("nodes", {})
        node = nodes.get(FLAKE_INPUT_NAME, {})
        locked = node.get("locked", {})
        rev = locked.get("rev")
        branch = locked.get("ref")
        if not branch:
            branch = node.get("original", {}).get("ref")
        return rev, branch
    except Exception:
        pass
    return None, None


def _get_remote_rev(branch=None):
    try:
        url = GITEA_API_BASE + "?limit=1"
        if branch:
            url += f"&sha={branch}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("sha")
    except Exception:
        pass
    return None


def check_for_updates() -> bool:
    locked_rev, branch = _get_locked_info()
    remote_rev = _get_remote_rev(branch)
    if locked_rev and remote_rev:
        return locked_rev != remote_rev
    return False


# ── IP address helpers ───────────────────────────────────────────

def _get_internal_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return "unavailable"


def _get_external_ip():
    for url in [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                ip = resp.read().decode().strip()
                if ip and len(ip) < 46:
                    return ip
        except Exception:
            continue
    return "unavailable"


# ── UpdateDialog ─────────────────────────────────────────────────

class UpdateDialog(Adw.Window):

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

        self._close_btn = Gtk.Button(label="Close", sensitive=False)
        self._close_btn.connect("clicked", lambda _b: self.close())
        header.pack_end(self._close_btn)

        self._reboot_btn = Gtk.Button(
            label="Reboot",
            css_classes=["destructive-action"],
            tooltip_text="Reboot the system now",
            visible=False,
        )
        self._reboot_btn.connect("clicked", self._on_reboot_clicked)
        header.pack_end(self._reboot_btn)

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


# ── Main Window ──────────────────────────────────────────────────

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
        self._update_available = False

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

        self._update_btn = Gtk.Button(
            label="Update System",
            css_classes=["suggested-action"],
            tooltip_text="System is up to date",
        )
        self._update_btn.connect("clicked", self._on_update_clicked)
        header.pack_start(self._update_btn)

        self._badge = Gtk.Label(
            label=" ●",
            css_classes=["update-badge"],
            visible=False,
        )
        header.pack_start(self._badge)

        refresh_btn = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Refresh now",
        )
        refresh_btn.connect("clicked", lambda _b: self._refresh_all())
        header.pack_end(refresh_btn)

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

        # ── Main content area ────────────────────────────────────
        self._main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        # ── IP Address Banner ────────────────────────────────────
        self._ip_bar = self._build_ip_bar()
        self._main_box.append(self._ip_bar)

        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vexpand=True,
        )

        self._tiles_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        scrolled.set_child(self._tiles_box)
        self._main_box.append(scrolled)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self._main_box)
        self.set_content(toolbar_view)

        self._build_tiles()

        interval = config.get("refresh_interval", 5)
        if interval and interval > 0:
            GLib.timeout_add_seconds(interval, self._auto_refresh)

        GLib.timeout_add_seconds(5, self._check_for_updates_once)
        GLib.timeout_add_seconds(UPDATE_CHECK_INTERVAL, self._periodic_update_check)

        GLib.timeout_add_seconds(1, self._fetch_ips_once)

    # ── IP Address Bar ───────────────────────────────────────────

    def _build_ip_bar(self):
        bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=24,
            halign=Gtk.Align.CENTER,
            margin_top=12,
            margin_bottom=4,
            margin_start=24,
            margin_end=24,
            css_classes=["ip-bar"],
        )

        internal_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
        )
        internal_icon = Gtk.Image(
            icon_name="network-wired-symbolic",
            pixel_size=16,
            css_classes=["dim-label"],
        )
        internal_label = Gtk.Label(
            label="Internal:",
            css_classes=["caption", "dim-label"],
        )
        self._internal_ip_label = Gtk.Label(
            label="…",
            css_classes=["caption", "ip-value"],
            selectable=True,
        )
        internal_box.append(internal_icon)
        internal_box.append(internal_label)
        internal_box.append(self._internal_ip_label)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)

        external_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
        )
        external_icon = Gtk.Image(
            icon_name="network-server-symbolic",
            pixel_size=16,
            css_classes=["dim-label"],
        )
        external_label = Gtk.Label(
            label="External:",
            css_classes=["caption", "dim-label"],
        )
        self._external_ip_label = Gtk.Label(
            label="…",
            css_classes=["caption", "ip-value"],
            selectable=True,
        )
        external_box.append(external_icon)
        external_box.append(external_label)
        external_box.append(self._external_ip_label)

        bar.append(internal_box)
        bar.append(sep)
        bar.append(external_box)

        return bar

    def _fetch_ips_once(self):
        thread = threading.Thread(target=self._do_fetch_ips, daemon=True)
        thread.start()
        return False

    def _do_fetch_ips(self):
        internal = _get_internal_ip()
        GLib.idle_add(self._internal_ip_label.set_label, internal)
        external = _get_external_ip()
        GLib.idle_add(self._external_ip_label.set_label, external)

    # ── Title box ────────────────────────────────────────────────

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

    # ── Service tiles ────────────────────────────────────────────

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

            # Fixed-width container for label + separator + tiles
            container = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                halign=Gtk.Align.CENTER,
                css_classes=["tiles-container"],
            )
            container.set_size_request(TILE_GRID_WIDTH, -1)

            section_label = Gtk.Label(
                label=cat_label,
                css_classes=["title-4"],
                halign=Gtk.Align.START,
                margin_top=20,
                margin_bottom=4,
                margin_start=16,
            )
            container.append(section_label)

            sep = Gtk.Separator(
                orientation=Gtk.Orientation.HORIZONTAL,
                margin_start=16,
                margin_end=16,
                margin_bottom=8,
            )
            container.append(sep)

            flowbox = Gtk.FlowBox(
                max_children_per_line=4,
                min_children_per_line=2,
                selection_mode=Gtk.SelectionMode.NONE,
                homogeneous=False,
                row_spacing=12,
                column_spacing=12,
                margin_top=4,
                margin_bottom=8,
                margin_start=16,
                margin_end=16,
                halign=Gtk.Align.START,
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

            container.append(flowbox)
            self._tiles_box.append(container)

        GLib.idle_add(self._refresh_all)

    # ── Update check ─────────────────────────────────────────────

    def _check_for_updates_once(self):
        thread = threading.Thread(target=self._do_update_check, daemon=True)
        thread.start()
        return False

    def _periodic_update_check(self):
        thread = threading.Thread(target=self._do_update_check, daemon=True)
        thread.start()
        return True

    def _do_update_check(self):
        available = check_for_updates()
        GLib.idle_add(self._set_update_indicator, available)

    def _set_update_indicator(self, available):
        self._update_available = available
        if available:
            self._update_btn.set_label("Update Available")
            self._update_btn.set_css_classes(["update-available"])
            self._update_btn.set_tooltip_text("A new version of Sovran_SystemsOS is available!")
            self._badge.set_visible(True)
        else:
            self._update_btn.set_label("Update System")
            self._update_btn.set_css_classes(["suggested-action"])
            self._update_btn.set_tooltip_text("System is up to date")
            self._badge.set_visible(False)

    # ── Callbacks ────────────────────────────────────────────────

    def _on_update_clicked(self, _btn):
        dialog = UpdateDialog(self)
        dialog.connect("close-request", lambda _w: self._after_update())
        dialog.present()

    def _after_update(self):
        GLib.timeout_add_seconds(3, self._check_for_updates_once)
        return False

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
