#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import atexit
import os
import secrets
import subprocess
import sys
import threading
import time

LOGO = "/etc/sovran/logo.png"
LOG = "/tmp/sovran-install.log"
FLAKE = "/etc/sovran/flake"

DEPLOYED_FLAKE = """\
{
  description = "Sovran_SystemsOS for the Sovran Pro from Sovran Systems";

  inputs = {
    Sovran_Systems.url = "git+https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS?ref=staging-dev";
  };

  outputs = { self, Sovran_Systems, ... }@inputs: {
    nixosConfigurations."nixos" = Sovran_Systems.inputs.nixpkgs.lib.nixosSystem {
      modules = [
        { nixpkgs.hostPlatform = "x86_64-linux"; }
        ./hardware-configuration.nix
        ./role-state.nix
        ./custom.nix
        Sovran_Systems.nixosModules.Sovran_SystemsOS
      ];
    };
  };
}
"""

DICEWARE_WORDS = [
    "apple", "barn", "brook", "cabin", "cedar", "cloud", "coral", "crane",
    "delta", "eagle", "ember", "fern", "field", "flame", "flora", "flint",
    "frost", "grove", "haven", "hedge", "holly", "heron", "jade", "juniper",
    "kelp", "larch", "lemon", "lilac", "linden", "loch", "lotus", "maple",
    "marsh", "meadow", "mist", "mossy", "mount", "oak", "ocean", "olive",
    "petal", "pine", "pixel", "plum", "pond", "prism", "quartz", "raven",
    "ridge", "river", "robin", "rocky", "rose", "rowan", "sage", "sand",
    "sierra", "silver", "slate", "snow", "solar", "spark", "spruce", "stone",
    "storm", "summit", "swift", "thorn", "tide", "timber", "torch", "trout",
    "vale", "vault", "vine", "walnut", "wave", "willow", "wren", "amber",
    "aspen", "birch", "blaze", "bloom", "bluff", "coast", "copper", "crest",
    "dune", "elder", "fjord", "forge", "glade", "glen", "glow", "gulf",
]

def generate_diceware_password():
    words = [secrets.choice(DICEWARE_WORDS) for _ in range(3)]
    digit = secrets.randbelow(10)
    return "-".join(words) + f"-{digit}"

try:
    logfile = open(LOG, "a")
    atexit.register(logfile.close)
except OSError:
    logfile = None

def log(msg):
    if logfile is not None:
        logfile.write(msg + "\n")
        logfile.flush()
    else:
        print(msg, file=sys.stderr)

def run(cmd):
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    log(result.stdout)
    if result.returncode != 0:
        log(result.stderr)
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return result.stdout.strip()

def run_stream(cmd, buf):
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True)
    for line in proc.stdout:
        log(line.rstrip())
        GLib.idle_add(append_text, buf, line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed (exit {proc.returncode}). See {LOG}")

def append_text(buf, text):
    buf.insert(buf.get_end_iter(), text)
    return False

def human_size(nbytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"

def check_internet():
    """Return True if the machine can reach the internet."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "5", "nixos.org"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass
    # Fallback: try a second host in case DNS for nixos.org is down
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "5", "1.1.1.1"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def symbolic_icon(name):
    """Create a crisp symbolic icon suitable for use as an ActionRow prefix."""
    icon = Gtk.Image.new_from_icon_name(name)
    icon.set_icon_size(Gtk.IconSize.LARGE)
    icon.add_css_class("dim-label")
    return icon


# ── Application ──────────────────────────────────────────────────────────

class InstallerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.sovransystems.installer")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self.win = InstallerWindow(application=app)
        self.win.present()


# ── Main Window ──────────────────────────────────────────────────────────

class InstallerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Sovran_SystemsOS Installer")
        self.set_default_size(820, 600)
        self.set_resizable(False)

        self.role = None
        self.boot_disk = None
        self.boot_size = None
        self.data_disk = None
        self.data_size = None
        self.data_drive_has_timechain = False
        self.free_password = None

        # Root navigation view
        self.nav = Adw.NavigationView()
        self.set_content(self.nav)

        # Always show the landing/welcome page first
        self.push_landing()

    # ── Navigation helpers ─────────────────────────────────────────────────

    def push_page(self, title, child, show_back=False):
        page = Adw.NavigationPage(title=title, tag=title)
        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        if not show_back:
            header.set_show_start_title_buttons(False)
        toolbar.add_top_bar(header)
        toolbar.set_content(child)

        page.set_child(toolbar)
        self.nav.push(page)

    def replace_page(self, title, child):
        # Pop all and push fresh
        while self.nav.get_visible_page() is not None:
            try:
                self.nav.pop()
            except Exception:
                break
        self.push_page(title, child)

    # ── Shared widgets ────────────────────────────────────────────────────

    def make_scrolled_log(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)

        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_monospace(True)
        tv.add_css_class("log-view")
        buf = tv.get_buffer()

        def on_changed(b):
            GLib.idle_add(lambda: sw.get_vadjustment().set_value(
                sw.get_vadjustment().get_upper()
            ))
        buf.connect("changed", on_changed)

        sw.set_child(tv)
        return sw, buf

    def nav_row(self, back_label=None, back_cb=None, next_label="Continue", next_cb=None):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(24)
        box.set_margin_start(40)
        box.set_margin_end(40)

        if back_label and back_cb:
            btn = Gtk.Button(label=back_label)
            btn.connect("clicked", back_cb)
            box.append(btn)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        box.append(spacer)

        if next_cb:
            btn = Gtk.Button(label=next_label)
            btn.add_css_class("suggested-action")
            btn.add_css_class("pill")
            btn.connect("clicked", next_cb)
            box.append(btn)

        return box

    # ── Landing / Welcome Screen ───────────────────────────────────────────

    def push_landing(self):
        """First screen: always shown. Welcomes the user and checks connectivity."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Hero
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.set_margin_top(40)
        hero.set_margin_bottom(16)
        hero.set_halign(Gtk.Align.CENTER)

        if os.path.exists(LOGO):
            try:
                img = Gtk.Image.new_from_file(LOGO)
                img.set_pixel_size(320)
                hero.append(img)
            except Exception:
                pass

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='heavy'>Welcome to Sovran_SystemsOS</span>")
        title.set_margin_top(8)
        hero.append(title)

        sub = Gtk.Label()
        sub.set_markup("<span size='large' style='italic' foreground='#888888'>Be Digitally Sovereign</span>")
        hero.append(sub)

        outer.append(hero)

        sep = Gtk.Separator()
        sep.set_margin_start(40)
        sep.set_margin_end(40)
        sep.set_margin_top(8)
        outer.append(sep)

        # Internet requirement notice
        notice = Gtk.Label()
        notice.set_markup(
            "<span size='medium'>"
            "Before installation begins, please ensure you have an <b>active internet connection</b>.\n"
            "Sovran_SystemsOS downloads packages during installation and requires internet access\n"
            "to complete the process.  Connect via <b>Ethernet cable</b> or configure <b>Wi-Fi</b> now."
            "</span>"
        )
        notice.set_justify(Gtk.Justification.CENTER)
        notice.set_wrap(True)
        notice.set_margin_top(20)
        notice.set_margin_start(48)
        notice.set_margin_end(48)
        outer.append(notice)

        # Inline offline warning banner (hidden by default)
        self._offline_banner = Adw.Banner()
        self._offline_banner.set_title(
            "No internet connection detected. Please connect Ethernet or Wi-Fi and try again."
        )
        self._offline_banner.set_revealed(False)
        self._offline_banner.set_margin_top(12)
        self._offline_banner.set_margin_start(40)
        self._offline_banner.set_margin_end(40)
        outer.append(self._offline_banner)

        outer.append(Gtk.Label(label="", vexpand=True))

        # Check & Continue button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_bottom(32)

        connect_btn = Gtk.Button(label="Check Connection & Continue  →")
        connect_btn.add_css_class("suggested-action")
        connect_btn.add_css_class("pill")
        connect_btn.connect("clicked", self._on_landing_connect)
        btn_box.append(connect_btn)

        outer.append(btn_box)

        self.push_page("Sovran_SystemsOS Installer", outer)

    def _on_landing_connect(self, btn):
        if check_internet():
            self._offline_banner.set_revealed(False)
            self.push_welcome()
        else:
            self._offline_banner.set_revealed(True)

    # ── Step 1: Welcome & Role ─────────────────────────────────────────────

    def push_welcome(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Hero
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.set_margin_top(32)
        hero.set_margin_bottom(24)
        hero.set_halign(Gtk.Align.CENTER)

        if os.path.exists(LOGO):
            try:
                img = Gtk.Image.new_from_file(LOGO)
                img.set_pixel_size(480)
                hero.append(img)
            except Exception:
                pass

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='heavy'>Sovran_SystemsOS</span>")
        hero.append(title)

        sub = Gtk.Label()
        sub.set_markup("<span size='large' style='italic' foreground='#888888'>Be Digitally Sovereign</span>")
        hero.append(sub)

        outer.append(hero)

        sep = Gtk.Separator()
        sep.set_margin_start(40)
        sep.set_margin_end(40)
        outer.append(sep)

        # Role label
        role_lbl = Gtk.Label()
        role_lbl.set_markup("<span size='medium' weight='bold'>Choose your installation type:</span>")
        role_lbl.set_halign(Gtk.Align.START)
        role_lbl.set_margin_start(40)
        role_lbl.set_margin_top(20)
        role_lbl.set_margin_bottom(8)
        outer.append(role_lbl)

        # Role cards
        roles = [
            ("Server + Desktop",
             "Full sovereign experience: beautiful desktop, your own cloud, secure messaging, Bitcoin node, and more.",
             "Server+Desktop"),
            ("Desktop Only",
             "A beautiful, easy-to-use desktop without the background server applications.",
             "Desktop Only"),
            ("Node Only",
             "Full Bitcoin node with Lightning and non-KYC buying and selling. No desktop.",
             "Node (Bitcoin-only)"),
        ]

        # Detect internal (non-USB) drives to gate role availability
        try:
            raw = run(["lsblk", "-b", "-dno", "NAME,SIZE,TYPE,RO,TRAN", "-e", "7,11"])
            internal_disks = []
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[2] == "disk" and parts[3] == "0":
                    tran = parts[4] if len(parts) >= 5 else ""
                    if tran != "usb":
                        internal_disks.append(parts[0])
        except Exception:
            internal_disks = []

        has_second_drive = len(internal_disks) >= 2

        NEEDS_DATA_DRIVE = {"Server+Desktop", "Node (Bitcoin-only)"}

        self._role_radios = []
        radio_group = None
        cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cards_box.set_margin_start(40)
        cards_box.set_margin_end(40)

        for label, desc, key in roles:
            card = Adw.ActionRow()
            card.set_title(label)

            available = has_second_drive or key not in NEEDS_DATA_DRIVE
            if not available:
                card.set_subtitle(desc + "\n⚠ Requires a second internal drive (not detected)")
                card.set_sensitive(False)
            else:
                card.set_subtitle(desc)

            radio = Gtk.CheckButton()
            radio.set_name(key)
            radio.set_sensitive(available)

            if radio_group is None and available:
                radio_group = radio
                radio.set_active(True)
            elif radio_group is not None:
                radio.set_group(radio_group)

            card.add_prefix(radio)
            card.set_activatable_widget(radio)
            self._role_radios.append(radio)
            cards_box.append(card)

        outer.append(cards_box)

        outer.append(Gtk.Label(label="", vexpand=True))
        outer.append(self.nav_row(
            next_label="Next  →",
            next_cb=self.on_role_next
        ))

        self.push_page("Welcome to Sovran_SystemsOS Installer", outer)

    def on_role_next(self, btn):
        for radio in self._role_radios:
            if radio.get_active():
                self.role = radio.get_name()
                break
        self.push_disk_detect()

    # ── Step 2a: Disk Detect ──────────────────────────────────────────────

    def push_disk_detect(self):
        """Detect internal drives and show the interactive disk selection page."""
        try:
            raw = run(["lsblk", "-b", "-dno", "NAME,SIZE,TYPE,RO,TRAN", "-e", "7,11"])
        except Exception as e:
            self.show_error(str(e))
            return

        disks = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "disk" and parts[3] == "0":
                tran = parts[4] if len(parts) >= 5 else ""
                if tran != "usb":
                    disks.append((parts[0], int(parts[1]), tran))

        if not disks:
            self.show_error("No valid internal drives found. USB drives are excluded.")
            return

        self.push_disk_select(disks)

    # ── Step 2b: Disk Select ──────────────────────────────────────────────

    def push_disk_select(self, disks):
        """Interactive disk-selection page: pick OS drive and (optionally) data drive."""

        BYTES_256GB = 256 * 1024 ** 3
        BYTES_2TB   = 2 * 10 ** 12

        # Sort ascending by size so the default selection (index 0) is the smallest
        disks = sorted(disks, key=lambda x: x[1])

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ── OS Drive group ────────────────────────────────────────────
        os_group = Adw.PreferencesGroup()
        os_group.set_title("OS Drive  (NixOS Boot + Root)")
        os_group.set_description(
            "Choose the drive for the NixOS installation.  Minimum 256 GB required."
        )
        os_group.set_margin_top(24)
        os_group.set_margin_start(40)
        os_group.set_margin_end(40)

        self._os_disk_radios = []
        os_radio_group = None

        for name, size, tran in disks:
            row = Adw.ActionRow()
            row.set_title(f"/dev/{name}")
            type_label = tran.upper() if tran else "Disk"
            meets = "✓ Meets 256 GB minimum" if size >= BYTES_256GB else "✗ Below 256 GB minimum"
            row.set_subtitle(f"{human_size(size)}  ·  {type_label}  —  {meets}")
            row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))

            radio = Gtk.CheckButton()
            radio.set_name(name)
            if os_radio_group is None:
                os_radio_group = radio
                radio.set_active(True)
            else:
                radio.set_group(os_radio_group)

            row.add_suffix(radio)
            row.set_activatable_widget(radio)
            self._os_disk_radios.append(radio)
            os_group.add(row)

        inner.append(os_group)

        # ── Data Drive group (skipped for Desktop Only) ───────────────
        self._data_disk_radios = []

        if self.role != "Desktop Only":
            data_group = Adw.PreferencesGroup()
            data_group.set_title("Bitcoin Timechain & Backups Drive")
            data_group.set_description(
                "💡 Tip: Always assign your LARGEST drive here.  "
                "The full Bitcoin timechain is over 700 GB and grows continuously — "
                "a 2 TB or larger drive is required."
            )
            data_group.set_margin_top(20)
            data_group.set_margin_start(40)
            data_group.set_margin_end(40)

            data_radio_group = None

            # "None" option
            none_row = Adw.ActionRow()
            none_row.set_title("None  (skip data drive)")
            none_row.set_subtitle("Bitcoin node functionality will be unavailable")
            none_radio = Gtk.CheckButton()
            none_radio.set_name("")
            data_radio_group = none_radio
            none_radio.set_active(True)
            none_row.add_suffix(none_radio)
            none_row.set_activatable_widget(none_radio)
            self._data_disk_radios.append(none_radio)
            data_group.add(none_row)

            for name, size, tran in disks:
                row = Adw.ActionRow()
                row.set_title(f"/dev/{name}")
                type_label = tran.upper() if tran else "Disk"
                meets = "✓ Meets 2 TB minimum" if size >= BYTES_2TB else "✗ Below 2 TB minimum"
                row.set_subtitle(f"{human_size(size)}  ·  {type_label}  —  {meets}")
                row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))

                radio = Gtk.CheckButton()
                radio.set_name(name)
                radio.set_group(data_radio_group)

                row.add_suffix(radio)
                row.set_activatable_widget(radio)
                self._data_disk_radios.append(radio)
                data_group.add(row)

            inner.append(data_group)

        scroll.set_child(inner)
        outer.append(scroll)
        outer.append(self.nav_row(
            back_label="←  Back",
            back_cb=lambda b: self.nav.pop(),
            next_label="Next  →",
            next_cb=lambda b: self._on_disk_select_next(disks),
        ))

        self.push_page("Select Drives", outer, show_back=True)

    def _on_disk_select_next(self, disks):
        """Validate the user's disk selections and advance to the ERASE confirmation."""
        BYTES_256GB = 256 * 1024 ** 3
        BYTES_2TB   = 2 * 10 ** 12

        size_map = {name: size for name, size, _ in disks}

        # Read OS disk selection
        os_name = None
        for radio in self._os_disk_radios:
            if radio.get_active():
                os_name = radio.get_name()
                break

        # Read data disk selection (empty string = None chosen)
        data_name = None
        if self._data_disk_radios:
            for radio in self._data_disk_radios:
                if radio.get_active():
                    sel = radio.get_name()
                    data_name = sel if sel else None
                    break

        os_size   = size_map.get(os_name, 0)
        data_size = size_map.get(data_name, 0) if data_name else 0

        # Validate OS drive size
        if os_size < BYTES_256GB:
            dlg = Adw.MessageDialog()
            dlg.set_transient_for(self)
            dlg.set_heading("OS Drive Too Small")
            dlg.set_body(
                f"The selected OS drive (/dev/{os_name}, {human_size(os_size)}) "
                f"does not meet the 256 GB minimum.  Please choose a larger drive."
            )
            dlg.add_response("ok", "OK")
            dlg.present()
            return

        # Validate data drive size (when one was selected)
        if data_name and data_size < BYTES_2TB:
            dlg = Adw.MessageDialog()
            dlg.set_transient_for(self)
            dlg.set_heading("Bitcoin Drive Too Small")
            dlg.set_body(
                f"The selected Bitcoin Timechain & Backups drive "
                f"(/dev/{data_name}, {human_size(data_size)}) "
                f"does not meet the 2 TB minimum.  "
                f"Please choose a larger drive or select \"None\"."
            )
            dlg.add_response("ok", "OK")
            dlg.present()
            return

        # Validate no duplicate selection
        if data_name and data_name == os_name:
            dlg = Adw.MessageDialog()
            dlg.set_transient_for(self)
            dlg.set_heading("Same Drive Selected Twice")
            dlg.set_body(
                "You cannot use the same drive for both the OS and "
                "Bitcoin Timechain & Backups.  Please choose different drives."
            )
            dlg.add_response("ok", "OK")
            dlg.present()
            return

        # Commit selections
        self.boot_disk  = os_name
        self.boot_size  = os_size
        self.data_disk  = data_name
        self.data_size  = data_size if data_name else None

        self.push_disk_confirm()

    # ── Step 2c: Disk Confirm (ERASE confirmation) ────────────────────────

    def push_disk_confirm(self):
        """Show the selected drives and ask the user to type ERASE to confirm."""
        self.data_drive_has_timechain = False
        if self.data_disk:
            data_path = f"/dev/{self.data_disk}"
            self.data_drive_has_timechain = self.detect_existing_timechain_data(data_path)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Disk info group
        disk_group = Adw.PreferencesGroup()
        if self.data_disk and self.data_drive_has_timechain:
            disk_group.set_title("OS drive to be erased (data drive preserved)")
        else:
            disk_group.set_title("Drives to be erased")
        disk_group.set_margin_top(24)
        disk_group.set_margin_start(40)
        disk_group.set_margin_end(40)

        boot_row = Adw.ActionRow()
        boot_row.set_title("OS Disk")
        boot_row.set_subtitle(f"/dev/{self.boot_disk}  —  {human_size(self.boot_size)}")
        boot_row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))
        disk_group.add(boot_row)

        if self.data_disk:
            data_row = Adw.ActionRow()
            data_row.set_title("Bitcoin Timechain & Backups Disk")
            data_row.set_subtitle(f"/dev/{self.data_disk}  —  {human_size(self.data_size)}")
            data_row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))
            disk_group.add(data_row)
            if self.data_drive_has_timechain:
                note_row = Adw.ActionRow()
                note_row.set_title(f"✓ Existing Bitcoin timechain detected on /dev/{self.data_disk}")
                note_row.set_subtitle("Data will be preserved and mounted as-is.")
                note_row.add_prefix(symbolic_icon("emblem-ok-symbolic"))
                disk_group.add(note_row)

        outer.append(disk_group)

        # Warning banner
        banner = Adw.Banner()
        if self.data_disk and self.data_drive_has_timechain:
            banner.set_title("⚠  All data on the OS disk will be permanently destroyed. Existing Bitcoin data disk will be preserved.")
        else:
            banner.set_title("⚠  All data on the above disk(s) will be permanently destroyed.")
        banner.set_revealed(True)
        banner.set_margin_top(16)
        banner.set_margin_start(40)
        banner.set_margin_end(40)
        outer.append(banner)

        # Confirm entry group
        entry_group = Adw.PreferencesGroup()
        entry_group.set_title("Type  ERASE  to confirm")
        entry_group.set_margin_top(16)
        entry_group.set_margin_start(40)
        entry_group.set_margin_end(40)

        entry_row = Adw.EntryRow()
        entry_row.set_title("Confirmation")
        self._confirm_entry = entry_row
        entry_group.add(entry_row)

        outer.append(entry_group)
        outer.append(Gtk.Label(label="", vexpand=True))
        outer.append(self.nav_row(
            back_label="←  Back",
            back_cb=lambda b: self.nav.pop(),
            next_label="Begin Installation",
            next_cb=self.on_confirm_next
        ))

        self.push_page("Confirm Installation", outer, show_back=True)

    def on_confirm_next(self, btn):
        if self._confirm_entry.get_text().strip() != "ERASE":
            dlg = Adw.MessageDialog()
            dlg.set_transient_for(self)
            dlg.set_heading("Confirmation Required")
            dlg.set_body("You must type ERASE exactly to proceed.")
            dlg.add_response("ok", "OK")
            dlg.present()
            return
        self.push_progress(
            "Preparing Drives",
            "Partitioning and formatting your drives...",
            self.do_partition
        )

    # ── Step 3 & 5: Progress ──────────────────────────────────────────────

    def push_progress(self, title, subtitle, worker_fn):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title(title)
        status.set_description(subtitle)
        status.set_vexpand(False)
        outer.append(status)

        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        outer.append(spinner)

        sw, buf = self.make_scrolled_log()
        sw.set_margin_start(40)
        sw.set_margin_end(40)
        sw.set_margin_top(12)
        sw.set_margin_bottom(12)
        sw.set_vexpand(True)
        outer.append(sw)

        self.push_page(title, outer)

        def thread_fn():
            try:
                worker_fn(buf)
            except Exception as e:
                GLib.idle_add(self.show_error, str(e))

        threading.Thread(target=thread_fn, daemon=True).start()

    # ── Worker: partition ─────────────────────────────────────────────────

    def partition_path(self, dev_path, num):
        return f"{dev_path}p{num}" if "nvme" in dev_path else f"{dev_path}{num}"

    def detect_existing_timechain_data(self, data_path, buf=None):
        data_p1 = self.partition_path(data_path, 1)
        if not os.path.exists(data_p1):
            return False

        label = ""
        for cmd in (
            ["sudo", "lsblk", "-no", "LABEL", data_p1],
            ["sudo", "blkid", "-o", "value", "-s", "LABEL", data_p1],
        ):
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                label = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
                if label:
                    break

        if label != "BTCEcoandBackup":
            return False

        check_mount = "/tmp/sovran-installer-data-check"
        mounted = False
        try:
            run(["sudo", "mkdir", "-p", check_mount])
            run(["sudo", "mount", "-o", "ro", data_p1, check_mount])
            mounted = True

            has_bitcoin = os.path.isdir(f"{check_mount}/BTCEcoandBackup/Bitcoin_Node")
            has_electrs = os.path.isdir(f"{check_mount}/BTCEcoandBackup/Electrs_Data")
            if has_bitcoin and has_electrs:
                if buf is not None:
                    GLib.idle_add(
                        append_text,
                        buf,
                        "=== Existing Bitcoin timechain detected on data drive — preserving data ===\n",
                    )
                return True
            return False
        except Exception:
            return False
        finally:
            if mounted:
                subprocess.run(["sudo", "umount", check_mount], capture_output=True, text=True)
            subprocess.run(["sudo", "rmdir", check_mount], capture_output=True, text=True)

    def do_partition(self, buf):
        boot_path = f"/dev/{self.boot_disk}"
        data_path = f"/dev/{self.data_disk}" if self.data_disk else None
        self.data_drive_has_timechain = False

        if data_path:
            self.data_drive_has_timechain = self.detect_existing_timechain_data(data_path, buf)

        # ── Wipe disk(s) ──
        GLib.idle_add(append_text, buf, "=== Wiping disk(s) ===\n")

        run_stream(["sudo", "sgdisk", "--zap-all", boot_path], buf)
        run_stream(["sudo", "wipefs", "--all", "--force", boot_path], buf)

        if data_path and not self.data_drive_has_timechain:
            run_stream(["sudo", "sgdisk", "--zap-all", data_path], buf)
            run_stream(["sudo", "wipefs", "--all", "--force", data_path], buf)

        run_stream(["sudo", "partprobe", boot_path], buf)
        if data_path and not self.data_drive_has_timechain:
            run_stream(["sudo", "partprobe", data_path], buf)

        time.sleep(2)

        # ── Partition boot disk: 512M ESP + rest as root ──
        GLib.idle_add(append_text, buf, "\n=== Partitioning boot disk ===\n")
        run_stream(["sudo", "sgdisk",
                    "-n", "1:1M:+512M", "-t", "1:EF00", "-c", "1:ESP",
                    "-n", "2:0:0",      "-t", "2:8300", "-c", "2:root",
                    boot_path], buf)

        run_stream(["sudo", "partprobe", boot_path], buf)
        time.sleep(2)

        # ── Partition data disk (if selected) ──
        if data_path and not self.data_drive_has_timechain:
            GLib.idle_add(append_text, buf, "\n=== Partitioning data disk ===\n")
            run_stream(["sudo", "sgdisk",
                        "-n", "1:1M:0", "-t", "1:8300", "-c", "1:primary",
                        data_path], buf)

            run_stream(["sudo", "partprobe", data_path], buf)
            time.sleep(2)

        # ── Format partitions ──
        GLib.idle_add(append_text, buf, "\n=== Formatting partitions ===\n")
        boot_p1 = self.partition_path(boot_path, 1)
        boot_p2 = self.partition_path(boot_path, 2)

        run_stream(["sudo", "mkfs.vfat", "-F", "32", boot_p1], buf)
        run_stream(["sudo", "mkfs.ext4", "-F", "-L", "sovran_systemsos", boot_p2], buf)

        if data_path and not self.data_drive_has_timechain:
            data_p1 = self.partition_path(data_path, 1)
            run_stream(["sudo", "mkfs.ext4", "-F", "-L", "BTCEcoandBackup", data_p1], buf)

        # ── Mount filesystems ──
        GLib.idle_add(append_text, buf, "\n=== Mounting filesystems ===\n")
        run_stream(["sudo", "mount", boot_p2, "/mnt"], buf)
        run_stream(["sudo", "mkdir", "-p", "/mnt/boot/efi"], buf)
        run_stream(["sudo", "mount", "-o", "umask=0077,defaults", boot_p1, "/mnt/boot/efi"], buf)

        if data_path:
            data_p1 = self.partition_path(data_path, 1)
            run_stream(["sudo", "mkdir", "-p", "/mnt/run/media/Second_Drive"], buf)
            run_stream(["sudo", "mount", data_p1, "/mnt/run/media/Second_Drive"], buf)
            run_stream(["sudo", "mkdir", "-p", "/mnt/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node"], buf)
            run_stream(["sudo", "mkdir", "-p", "/mnt/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data"], buf)
            run_stream(["sudo", "mkdir", "-p", "/mnt/run/media/Second_Drive/BTCEcoandBackup/NixOS_Snapshot_Backup"], buf)

        GLib.idle_add(append_text, buf, "\n=== Generating hardware config ===\n")
        run_stream(["sudo", "nixos-generate-config", "--root", "/mnt"], buf)

        GLib.idle_add(append_text, buf, "\n=== Copying flake to /mnt ===\n")
        run(["sudo", "cp", "/mnt/etc/nixos/hardware-configuration.nix", "/tmp/hardware-configuration.nix"])
        run(["sudo", "rm", "-rf", "/mnt/etc/nixos/"])
        run(["sudo", "mkdir", "-p", "/mnt/etc/nixos"])
        run(["sudo", "cp", "-a", f"{FLAKE}/.", "/mnt/etc/nixos/"])
        run(["sudo", "cp", "/tmp/hardware-configuration.nix", "/mnt/etc/nixos/hardware-configuration.nix"])

        GLib.idle_add(append_text, buf, "\n=== Writing role config ===\n")
        self.write_role_state()
        GLib.idle_add(append_text, buf, "Done.\n")

        GLib.idle_add(self.push_ready)

    def write_role_state(self):
        is_server = str(self.role == "Server+Desktop").lower()
        is_desktop = str(self.role == "Desktop Only").lower()
        is_node = str(self.role == "Node (Bitcoin-only)").lower()
        content = f"""# THIS FILE IS AUTO-GENERATED BY THE INSTALLER. DO NOT EDIT.
{{ config, lib, ... }}:
{{
  sovran_systemsOS.roles.server_plus_desktop = lib.mkDefault {is_server};
  sovran_systemsOS.roles.desktop = lib.mkDefault {is_desktop};
  sovran_systemsOS.roles.node = lib.mkDefault {is_node};
}}
"""
        proc = subprocess.run(
            ["sudo", "tee", "/mnt/etc/nixos/role-state.nix"],
            input=content, text=True, capture_output=True
        )
        log(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to write role-state.nix: {proc.stderr}")
        run(["sudo", "cp", "/mnt/etc/nixos/custom.template.nix", "/mnt/etc/nixos/custom.nix"])

    # ── Step 4: Ready to install ──────────────────────────────────────────

    def push_ready(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("Drives Ready")
        status.set_description("Your drives have been partitioned successfully.")
        status.set_vexpand(True)

        details = Adw.PreferencesGroup()
        details.set_margin_start(40)
        details.set_margin_end(40)

        role_row = Adw.ActionRow()
        role_row.set_title("Installation Type")
        role_row.set_subtitle(self.role)
        details.add(role_row)

        boot_row = Adw.ActionRow()
        boot_row.set_title("Boot Disk")
        boot_row.set_subtitle(f"/dev/{self.boot_disk}  —  {human_size(self.boot_size)}")
        details.add(boot_row)

        if self.data_disk:
            data_row = Adw.ActionRow()
            data_row.set_title("Data Disk")
            data_row.set_subtitle(f"/dev/{self.data_disk}  —  {human_size(self.data_size)}")
            details.add(data_row)

        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        status_box.append(status)
        status_box.append(details)

        note = Gtk.Label()
        note.set_markup(
            "<span foreground='#888888'>The next step will install the full system.\n"
            "This may take <b>20–40 minutes</b> depending on your internet speed.\n"
            "Do not turn off your computer.</span>"
        )
        note.set_justify(Gtk.Justification.CENTER)
        note.set_wrap(True)
        note.set_margin_top(16)
        note.set_margin_start(40)
        note.set_margin_end(40)
        status_box.append(note)

        outer.append(status_box)
        outer.append(self.nav_row(
            next_label="Install Now",
            next_cb=lambda b: self.push_progress(
                "Installing Sovran_SystemsOS",
                "Building and installing your system. Please wait...",
                self.do_install
            )
        ))

        self.push_page("Ready to Install", outer)
        return False

    # ── Worker: install ───────────────────────────────────────────────────

    def do_install(self, buf):
        GLib.idle_add(append_text, buf, "=== Running nixos-install ===\n")

        for f in ["/mnt/etc/nixos/role-state.nix", "/mnt/etc/nixos/custom.nix"]:
            if not os.path.exists(f):
                raise RuntimeError(f"Required file missing: {f}")

        # The flake.nix imports /etc/nixos/role-state.nix and /etc/nixos/custom.nix
        # as absolute paths. With --impure, Nix resolves these on the live ISO host,
        # not under /mnt. Copy them so they exist on the host filesystem too.
        GLib.idle_add(append_text, buf, "Copying config files to host /etc/nixos for flake evaluation...\n")
        run(["sudo", "mkdir", "-p", "/etc/nixos"])
        run(["sudo", "cp", "/mnt/etc/nixos/role-state.nix", "/etc/nixos/role-state.nix"])
        run(["sudo", "cp", "/mnt/etc/nixos/custom.nix", "/etc/nixos/custom.nix"])
        run(["sudo", "cp", "/mnt/etc/nixos/hardware-configuration.nix", "/etc/nixos/hardware-configuration.nix"])

        run_stream([
            "sudo", "nixos-install",
            "--root", "/mnt",
            "--flake", "/mnt/etc/nixos#nixos",
            "--no-root-password",
            "--impure"
        ], buf)

        # Clean up /mnt/etc/nixos — only 5 files are needed post-install.
        # configuration.nix and modules/ were needed during nixos-install
        # for flake evaluation, but are now baked into the Nix store via
        # self.nixosModules.Sovran_SystemsOS.
        GLib.idle_add(append_text, buf, "Cleaning up /mnt/etc/nixos...\n")
        keep = {"flake.nix", "flake.lock", "hardware-configuration.nix",
                "role-state.nix", "custom.nix"}
        nixos_dir = "/mnt/etc/nixos"
        for entry in os.listdir(nixos_dir):
            if entry not in keep:
                path = os.path.join(nixos_dir, entry)
                run(["sudo", "rm", "-rf", path])

        GLib.idle_add(append_text, buf, "Writing deployed flake.nix...\n")
        proc = subprocess.run(
            ["sudo", "tee", "/mnt/etc/nixos/flake.nix"],
            input=DEPLOYED_FLAKE,
            capture_output=True,
            text=True,
        )
        log(proc.stdout)
        if proc.returncode != 0:
            log(proc.stderr)
            raise RuntimeError(proc.stderr.strip() or "Failed to write deployed flake.nix")
        GLib.idle_add(append_text, buf, "Locking flake to staging-dev...\n")
        run_stream(["sudo", "nix", "--extra-experimental-features", "nix-command flakes",
                    "flake", "lock", "/mnt/etc/nixos"], buf)

        # Generate diceware passwords and write them to the installed system
        GLib.idle_add(append_text, buf, "Setting up user passwords...\n")
        self.free_password = generate_diceware_password()
        root_password = generate_diceware_password()

        run(["sudo", "mkdir", "-p", "/mnt/var/lib/secrets"])
        run(["sudo", "chmod", "700", "/mnt/var/lib/secrets"])
        proc = subprocess.run(
            ["sudo", "tee", "/mnt/var/lib/secrets/free-password"],
            input=self.free_password, capture_output=True, text=True
        )
        if proc.returncode != 0:
            log(proc.stderr)
            raise RuntimeError(proc.stderr.strip() or "Failed to write free-password")
        run(["sudo", "chmod", "600", "/mnt/var/lib/secrets/free-password"])

        proc = subprocess.run(
            ["sudo", "tee", "/mnt/var/lib/secrets/root-password"],
            input=root_password, capture_output=True, text=True
        )
        if proc.returncode != 0:
            log(proc.stderr)
            raise RuntimeError(proc.stderr.strip() or "Failed to write root-password")
        run(["sudo", "chmod", "600", "/mnt/var/lib/secrets/root-password"])

        GLib.idle_add(self.push_complete)

    # ── Complete ───────────────────────────────────────────────────────────

    def push_complete(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("Installation Complete!")
        status.set_description("Before rebooting, write down your login password.")
        status.set_icon_name("dialog-password-symbolic")
        outer.append(status)

        pw_frame = Gtk.Frame()
        pw_frame.set_margin_start(60)
        pw_frame.set_margin_end(60)
        pw_label = Gtk.Label()
        pw_label.set_markup(
            f"<span font_family='monospace' size='xx-large' weight='bold'>"
            f"{GLib.markup_escape_text(self.free_password)}</span>"
        )
        pw_label.set_selectable(True)
        pw_label.set_margin_top(16)
        pw_label.set_margin_bottom(16)
        pw_frame.set_child(pw_label)
        outer.append(pw_frame)

        warning = Gtk.Label()
        warning.set_markup(
            "<span foreground='#e8a838' size='medium' weight='bold'>"
            "⚠  Write this password down now.\n"
            "You will need it to log in to your computer and the Sovran Hub.\n"
            "This password cannot be recovered.</span>"
        )
        warning.set_justify(Gtk.Justification.CENTER)
        warning.set_wrap(True)
        warning.set_margin_top(20)
        warning.set_margin_start(48)
        warning.set_margin_end(48)
        outer.append(warning)

        outer.append(Gtk.Label(label="", vexpand=True))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_bottom(32)
        reboot_btn = Gtk.Button(label="I Have Written Down My Password — Reboot Now")
        reboot_btn.add_css_class("suggested-action")
        reboot_btn.add_css_class("pill")
        reboot_btn.connect("clicked", lambda b: subprocess.run(["sudo", "reboot"]))
        btn_box.append(reboot_btn)
        outer.append(btn_box)

        self.push_page("Complete", outer)
        return False

    # ── Error screen ───────────────────────────────────────────────────────

    def show_error(self, msg):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("Installation Error")
        status.set_description(msg)
        status.set_icon_name("dialog-error-symbolic")
        status.set_vexpand(True)

        log_lbl = Gtk.Label()
        log_lbl.set_markup(f"<span foreground='#888888' size='small'>Full log: {LOG}</span>")
        log_lbl.set_margin_bottom(24)

        outer.append(status)
        outer.append(log_lbl)

        self.push_page("Error", outer)
        return False


if __name__ == "__main__":
    app = InstallerApp()
    app.run(None)
