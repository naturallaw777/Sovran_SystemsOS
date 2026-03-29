#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import atexit
import os
import subprocess
import sys
import threading
import time

LOGO = "/etc/sovran/logo.png"
LOG = "/tmp/sovran-install.log"
FLAKE = "/etc/sovran/flake"

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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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


# ── Application ────────────────────────────────────────────────────────────────

class InstallerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.sovransystems.installer")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self.win = InstallerWindow(application=app)
        self.win.present()


# ── Main Window ────────────────────────────────────────────────────────────────

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

        # Root navigation view
        self.nav = Adw.NavigationView()
        self.set_content(self.nav)

        # Check for internet before anything else
        if check_internet():
            self.push_welcome()
        else:
            self.push_no_internet()

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

    # ── Shared widgets ───────────────��─────────────────────────────────────

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

    # ── No Internet Screen ─────────────────────────────────────────────────

    def push_no_internet(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("No Internet Connection")
        status.set_description(
            "An active internet connection is required to install Sovran_SystemsOS.\n\n"
            "Please connect an Ethernet cable or configure Wi-Fi,\n"
            "then press Retry."
        )
        status.set_icon_name("network-offline-symbolic")
        status.set_vexpand(True)
        outer.append(status)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_bottom(32)

        retry_btn = Gtk.Button(label="Retry")
        retry_btn.add_css_class("suggested-action")
        retry_btn.add_css_class("pill")
        retry_btn.connect("clicked", self.on_retry_internet)
        btn_box.append(retry_btn)

        outer.append(btn_box)

        self.push_page("No Internet", outer)

    def on_retry_internet(self, btn):
        if check_internet():
            # Pop the no-internet page and proceed to welcome
            try:
                self.nav.pop()
            except Exception:
                pass
            self.push_welcome()
        else:
            dlg = Adw.MessageDialog()
            dlg.set_transient_for(self)
            dlg.set_heading("Still Offline")
            dlg.set_body(
                "Could not reach the internet.\n"
                "Please check your network connection and try again."
            )
            dlg.add_response("ok", "OK")
            dlg.present()

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
        title.set_markup("<span size='xx-large' weight='heavy'>Sovran Systems</span>")
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

        self._role_radios = []
        radio_group = None
        cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cards_box.set_margin_start(40)
        cards_box.set_margin_end(40)

        for label, desc, key in roles:
            card = Adw.ActionRow()
            card.set_title(label)
            card.set_subtitle(desc)

            radio = Gtk.CheckButton()
            radio.set_name(key)
            if radio_group is None:
                radio_group = radio
                radio.set_active(True)
            else:
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
        self.push_disk_confirm()

    # ── Step 2: Disk Confirm ───────────────────────────────────────────────

    def push_disk_confirm(self):
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
                    disks.append((parts[0], int(parts[1])))

        if not disks:
            self.show_error("No valid internal drives found. USB drives are excluded.")
            return

        disks.sort(key=lambda x: x[1])
        self.boot_disk, self.boot_size = disks[0]
        self.data_disk, self.data_size = None, None

        BYTES_2TB = 2 * 1024 ** 4
        if len(disks) >= 2:
            d, s = disks[-1]
            if s >= BYTES_2TB:
                self.data_disk, self.data_size = d, s

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Disk info group
        disk_group = Adw.PreferencesGroup()
        disk_group.set_title("Drives to be erased")
        disk_group.set_margin_top(24)
        disk_group.set_margin_start(40)
        disk_group.set_margin_end(40)

        boot_row = Adw.ActionRow()
        boot_row.set_title("Boot Disk")
        boot_row.set_subtitle(f"/dev/{self.boot_disk}  —  {human_size(self.boot_size)}")
        boot_row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))
        disk_group.add(boot_row)

        if self.data_disk:
            data_row = Adw.ActionRow()
            data_row.set_title("Data Disk")
            data_row.set_subtitle(f"/dev/{self.data_disk}  —  {human_size(self.data_size)}")
            data_row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))
            disk_group.add(data_row)
        else:
            no_row = Adw.ActionRow()
            no_row.set_title("Data Disk")
            no_row.set_subtitle("None detected  (requires 2 TB or larger)")
            no_row.add_prefix(symbolic_icon("drive-harddisk-symbolic"))
            disk_group.add(no_row)

        outer.append(disk_group)

        # Warning banner
        banner = Adw.Banner()
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
        status.set_icon_name("emblem-synchronizing-symbolic")
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

    def do_partition(self, buf):
        boot_path = f"/dev/{self.boot_disk}"

        # ── Wipe disk(s) to clear stale GPT/MBR data before disko ──
        GLib.idle_add(append_text, buf, "=== Wiping disk(s) ===\n")

        run_stream(["sudo", "sgdisk", "--zap-all", boot_path], buf)
        run_stream(["sudo", "wipefs", "--all", "--force", boot_path], buf)

        if self.data_disk:
            data_path = f"/dev/{self.data_disk}"
            run_stream(["sudo", "sgdisk", "--zap-all", data_path], buf)
            run_stream(["sudo", "wipefs", "--all", "--force", data_path], buf)

        # Inform the kernel of the wiped partition tables
        run_stream(["sudo", "partprobe", boot_path], buf)
        if self.data_disk:
            run_stream(["sudo", "partprobe", data_path], buf)

        # Short settle so the kernel finishes re-reading
        time.sleep(2)

        # ── Now run disko on a clean disk ──
        GLib.idle_add(append_text, buf, "\n=== Partitioning drives ===\n")
        cmd = [
            "sudo", "disko", "--mode", "disko",
            f"{FLAKE}/iso/disko.nix",
            "--arg", "device", f'"{boot_path}"'
        ]
        if self.data_disk:
            cmd += ["--arg", "dataDevice", f'"/dev/{self.data_disk}"']
        run_stream(cmd, buf)

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

    # ── Step 4: Ready to install ────────���──────────────────────────────────

    def push_ready(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("Drives Ready")
        status.set_description("Your drives have been partitioned successfully.")
        status.set_icon_name("emblem-ok-symbolic")
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
                "Installing Sovran SystemsOS",
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

        run_stream([
            "sudo", "nixos-install",
            "--root", "/mnt",
            "--flake", "/mnt/etc/nixos#nixos"
        ], buf)

        GLib.idle_add(self.push_complete)

    # ── Step 6: Complete ───────────────────────────────────────────────────

    def push_complete(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        status = Adw.StatusPage()
        status.set_title("Installation Complete!")
        status.set_description("Welcome to Sovran SystemsOS.")
        status.set_icon_name("emblem-ok-symbolic")
        status.set_vexpand(True)

        creds_group = Adw.PreferencesGroup()
        creds_group.set_title("⚠  Write down your login details before rebooting")
        creds_group.set_margin_start(40)
        creds_group.set_margin_end(40)

        user_row = Adw.ActionRow()
        user_row.set_title("Username")
        user_row.set_subtitle("free")
        creds_group.add(user_row)

        pass_row = Adw.ActionRow()
        pass_row.set_title("Password")
        pass_row.set_subtitle("free")
        creds_group.add(pass_row)

        note_row = Adw.ActionRow()
        note_row.set_title("App Passwords")
        note_row.set_subtitle(
            "After rebooting, all app passwords (Nextcloud, Bitcoin, Matrix, etc.) "
            "will be saved to a secure PDF in your Documents folder."
        )
        creds_group.add(note_row)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.append(status)
        content_box.append(creds_group)
        outer.append(content_box)

        reboot_btn = Gtk.Button(label="Reboot Now")
        reboot_btn.add_css_class("suggested-action")
        reboot_btn.add_css_class("pill")
        reboot_btn.add_css_class("destructive-action")
        reboot_btn.connect("clicked", lambda b: subprocess.run(["sudo", "reboot"]))

        nav = Gtk.Box()
        nav.set_margin_bottom(24)
        nav.set_margin_end(40)
        nav.set_halign(Gtk.Align.END)
        nav.append(reboot_btn)
        outer.append(nav)

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
