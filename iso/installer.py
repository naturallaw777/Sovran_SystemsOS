#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango, GdkPixbuf
import subprocess
import threading
import os
import sys

LOGO = "/etc/sovran/logo.png"
LOG = "/tmp/sovran-install.log"
FLAKE = "/etc/sovran/flake"
logfile = open(LOG, "a")

def log(msg):
    logfile.write(msg + "\n")
    logfile.flush()

def run(cmd, **kwargs):
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    log(result.stdout)
    if result.returncode != 0:
        log(result.stderr)
        raise RuntimeError(result.stderr or f"Command failed: {cmd}")
    return result.stdout.strip()

def run_stream(cmd, text_buffer):
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        log(line.rstrip())
        GLib.idle_add(append_text, text_buffer, line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with code {proc.returncode}. See {LOG}")

def append_text(buf, text):
    buf.insert(buf.get_end_iter(), text)
    return False

def human_size(nbytes):
    for unit in ["B","KB","MB","GB","TB"]:
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"

# ── Window base ────────────────────────────────────────────────────────────────

class InstallerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sovran_SystemsOS Installer")
        self.set_default_size(800, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        if os.path.exists(LOGO):
            self.set_icon_from_file(LOGO)
        self.connect("delete-event", Gtk.main_quit)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        self.stack.set_transition_duration(300)
        self.add(self.stack)

        self.role = None
        self.boot_disk = None
        self.boot_size = None
        self.data_disk = None
        self.data_size = None

        self.show_welcome()
        self.show_all()

    # ── Helpers ────────────────────────────────────────────────────────────

    def clear_stack(self):
        for child in self.stack.get_children():
            self.stack.remove(child)

    def set_page(self, widget, name="page"):
        self.clear_stack()
        self.stack.add_named(widget, name)
        self.stack.set_visible_child_name(name)
        self.show_all()

    def make_header(self, title, subtitle=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(32)
        box.set_margin_bottom(16)
        box.set_margin_start(40)
        box.set_margin_end(40)

        lbl = Gtk.Label()
        lbl.set_markup(f"<span font='24' weight='heavy'>{title}</span>")
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        if subtitle:
            sub = Gtk.Label()
            sub.set_markup(f"<span font='13' foreground='#888888'>{subtitle}</span>")
            sub.set_halign(Gtk.Align.START)
            box.pack_start(sub, False, False, 0)

        sep = Gtk.Separator()
        sep.set_margin_top(12)
        box.pack_start(sep, False, False, 0)
        return box

    def make_nav(self, back_label=None, back_cb=None, next_label="Continue", next_cb=None):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_top(8)
        bar.set_margin_bottom(20)
        bar.set_margin_start(40)
        bar.set_margin_end(40)

        if back_label and back_cb:
            btn = Gtk.Button(label=back_label)
            btn.connect("clicked", back_cb)
            bar.pack_start(btn, False, False, 0)

        bar.pack_start(Gtk.Label(), True, True, 0)

        if next_cb:
            btn = Gtk.Button(label=next_label)
            btn.get_style_context().add_class("suggested-action")
            btn.connect("clicked", next_cb)
            bar.pack_end(btn, False, False, 0)

        return bar

    def error(self, msg):
        GLib.idle_add(self._show_error, msg)

    def _show_error(self, msg):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.make_header("Installation Error", "Something went wrong."), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_margin_start(40)
        body.set_margin_end(40)

        icon = Gtk.Label()
        icon.set_markup("<span font='48'>❌</span>")
        body.pack_start(icon, False, False, 0)

        lbl = Gtk.Label(label=msg)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(60)
        lbl.set_justify(Gtk.Justification.CENTER)
        body.pack_start(lbl, False, False, 0)

        log_lbl = Gtk.Label()
        log_lbl.set_markup(f"<span font='11' foreground='#888'>Full log: {LOG}</span>")
        body.pack_start(log_lbl, False, False, 0)

        page.pack_start(body, True, True, 0)

        quit_btn = Gtk.Button(label="Close Installer")
        quit_btn.connect("clicked", Gtk.main_quit)
        nav = Gtk.Box()
        nav.set_margin_bottom(20)
        nav.set_margin_end(40)
        nav.pack_end(quit_btn, False, False, 0)
        page.pack_start(nav, False, False, 0)

        self.set_page(page)
        return False

    # ── Step 1: Welcome & Role ─────────────────────────────────────────────

    def show_welcome(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Hero banner
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hero.set_margin_top(36)
        hero.set_margin_bottom(20)

        if os.path.exists(LOGO):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(LOGO, 80, 80, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                hero.pack_start(img, False, False, 0)
            except Exception:
                pass

        title = Gtk.Label()
        title.set_markup("<span font='28' weight='heavy'>Sovran Systems</span>")
        hero.pack_start(title, False, False, 0)

        sub = Gtk.Label()
        sub.set_markup("<span font='14' style='italic' foreground='#888888'>Be Digitally Sovereign</span>")
        hero.pack_start(sub, False, False, 0)

        page.pack_start(hero, False, False, 0)

        sep = Gtk.Separator()
        sep.set_margin_start(40)
        sep.set_margin_end(40)
        page.pack_start(sep, False, False, 0)

        # Role selection
        lbl = Gtk.Label()
        lbl.set_markup("<span font='13'>Select your installation type:</span>")
        lbl.set_margin_top(20)
        lbl.set_margin_start(40)
        lbl.set_halign(Gtk.Align.START)
        page.pack_start(lbl, False, False, 0)

        roles = [
            ("Server + Desktop",
             "The full Sovran experience: beautiful desktop + your own cloud, secure messaging, Bitcoin node, and more.",
             "Server+Desktop"),
            ("Desktop Only",
             "A beautiful, easy-to-use desktop without the background server applications.",
             "Desktop Only"),
            ("Node Only",
             "Full Bitcoin node with Lightning and non-KYC buying and selling. No desktop.",
             "Node (Bitcoin-only)"),
        ]

        radio_group = None
        self._role_radios = []
        role_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        role_box.set_margin_start(40)
        role_box.set_margin_end(40)
        role_box.set_margin_top(8)

        for label, desc, key in roles:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row.set_margin_bottom(8)

            radio = Gtk.RadioButton(group=radio_group, label=label)
            radio.set_name(key)
            if radio_group is None:
                radio_group = radio
                radio.set_active(True)
            radio.get_style_context().add_class("role-radio")
            self._role_radios.append(radio)

            desc_lbl = Gtk.Label(label=desc)
            desc_lbl.set_line_wrap(True)
            desc_lbl.set_max_width_chars(70)
            desc_lbl.set_halign(Gtk.Align.START)
            desc_lbl.set_margin_start(28)
            desc_lbl.get_style_context().add_class("dim-label")

            row.pack_start(radio, False, False, 0)
            row.pack_start(desc_lbl, False, False, 0)
            role_box.pack_start(row, False, False, 0)

        page.pack_start(role_box, False, False, 0)
        page.pack_start(Gtk.Label(), True, True, 0)
        page.pack_start(self.make_nav(next_label="Next →", next_cb=self.on_role_next), False, False, 0)
        self.set_page(page, "welcome")

    def on_role_next(self, btn):
        for radio in self._role_radios:
            if radio.get_active():
                self.role = radio.get_name()
                break
        self.show_disk_confirm()

    # ── Step 2: Disk Confirm ───────────────────────────────────────────────

    def show_disk_confirm(self):
        # Detect disks
        try:
            raw = run(["lsblk", "-b", "-dno", "NAME,SIZE,TYPE,RO,TRAN", "-e", "7,11"])
        except Exception as e:
            self.error(str(e))
            return

        disks = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "disk" and parts[3] == "0":
                tran = parts[4] if len(parts) >= 5 else ""
                if tran != "usb":
                    disks.append((parts[0], int(parts[1])))

        if not disks:
            self.error("No valid internal drives found. USB drives are excluded.")
            return

        disks.sort(key=lambda x: x[1])
        self.boot_disk, self.boot_size = disks[0]
        self.data_disk, self.data_size = None, None

        BYTES_2TB = 2 * 1024 ** 4
        if len(disks) >= 2:
            d, s = disks[-1]
            if s >= BYTES_2TB:
                self.data_disk, self.data_size = d, s

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.make_header(
            "Confirm Installation",
            "Review the disks below. ALL DATA will be permanently erased."
        ), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_start(40)
        body.set_margin_end(40)
        body.set_margin_top(8)

        # Disk info box
        disk_frame = Gtk.Frame()
        disk_frame.set_shadow_type(Gtk.ShadowType.IN)
        disk_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        disk_inner.set_margin_top(12)
        disk_inner.set_margin_bottom(12)
        disk_inner.set_margin_start(16)
        disk_inner.set_margin_end(16)

        boot_lbl = Gtk.Label()
        boot_lbl.set_markup(f"<b>Boot disk:</b>  /dev/{self.boot_disk}  ({human_size(self.boot_size)})")
        boot_lbl.set_halign(Gtk.Align.START)
        disk_inner.pack_start(boot_lbl, False, False, 0)

        if self.data_disk:
            data_lbl = Gtk.Label()
            data_lbl.set_markup(f"<b>Data disk:</b>  /dev/{self.data_disk}  ({human_size(self.data_size)})")
            data_lbl.set_halign(Gtk.Align.START)
            disk_inner.pack_start(data_lbl, False, False, 0)
        else:
            no_data = Gtk.Label()
            no_data.set_markup("<b>Data disk:</b>  none detected (requires 2TB+)")
            no_data.set_halign(Gtk.Align.START)
            disk_inner.pack_start(no_data, False, False, 0)

        disk_frame.add(disk_inner)
        body.pack_start(disk_frame, False, False, 0)

        warn = Gtk.Label()
        warn.set_markup(
            "<span foreground='#cc0000' weight='bold'>⚠  This action cannot be undone. "
            "All existing data on the above disk(s) will be permanently destroyed.</span>"
        )
        warn.set_line_wrap(True)
        warn.set_max_width_chars(65)
        warn.set_halign(Gtk.Align.START)
        body.pack_start(warn, False, False, 0)

        # Confirm entry
        confirm_lbl = Gtk.Label(label='Type  ERASE  to confirm:')
        confirm_lbl.set_halign(Gtk.Align.START)
        body.pack_start(confirm_lbl, False, False, 0)

        self._confirm_entry = Gtk.Entry()
        self._confirm_entry.set_placeholder_text("ERASE")
        body.pack_start(self._confirm_entry, False, False, 0)

        page.pack_start(body, False, False, 0)
        page.pack_start(Gtk.Label(), True, True, 0)
        page.pack_start(self.make_nav(
            back_label="← Back", back_cb=lambda b: self.show_welcome(),
            next_label="Begin Installation", next_cb=self.on_confirm_next
        ), False, False, 0)
        self.set_page(page, "disks")

    def on_confirm_next(self, btn):
        if self._confirm_entry.get_text().strip() != "ERASE":
            dlg = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="You must type ERASE exactly to continue."
            )
            dlg.run()
            dlg.destroy()
            return
        self.show_progress("Preparing Drives", "Partitioning and formatting your drives...", self.do_partition)

    # ── Step 3 & 5: Progress with live log ────────────────────────────────

    def show_progress(self, title, subtitle, worker_fn):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.make_header(title, subtitle), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_start(40)
        body.set_margin_end(40)

        spinner = Gtk.Spinner()
        spinner.set_size_request(48, 48)
        spinner.start()
        body.pack_start(spinner, False, False, 0)

        # Scrollable live log
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_size_request(-1, 260)

        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.modify_font(Pango.FontDescription("Monospace 9"))
        tv.get_style_context().add_class("log-view")
        buf = tv.get_buffer()
        sw.add(tv)
        body.pack_start(sw, True, True, 0)

        # Auto-scroll to bottom
        def on_changed(b):
            adj = sw.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
        buf.connect("changed", on_changed)

        page.pack_start(body, True, True, 0)
        self.set_page(page, "progress")

        def thread_fn():
            try:
                worker_fn(buf)
            except Exception as e:
                self.error(str(e))

        t = threading.Thread(target=thread_fn, daemon=True)
        t.start()

    # ── Worker: partition ─────────────────────────────────────────────────

    def do_partition(self, buf):
        GLib.idle_add(append_text, buf, "=== Partitioning drives ===\n")
        boot_path = f"/dev/{self.boot_disk}"
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

        GLib.idle_add(self.show_install_step)

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

    # ── Step 4: Confirm before full install ───────────────────────────────

    def show_install_step(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.make_header(
            "Drives Ready",
            "Your drives have been partitioned. Ready to install Sovran SystemsOS."
        ), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_start(40)
        body.set_margin_end(40)
        body.set_margin_top(16)

        icon = Gtk.Label()
        icon.set_markup("<span font='48'>✅</span>")
        body.pack_start(icon, False, False, 0)

        info = Gtk.Label()
        info.set_markup(
            f"<b>Role:</b>  {self.role}\n"
            f"<b>Boot disk:</b>  /dev/{self.boot_disk}  ({human_size(self.boot_size)})\n" +
            (f"<b>Data disk:</b>  /dev/{self.data_disk}  ({human_size(self.data_size)})"
             if self.data_disk else "<b>Data disk:</b>  none")
        )
        info.set_halign(Gtk.Align.CENTER)
        info.set_justify(Gtk.Justification.CENTER)
        body.pack_start(info, False, False, 0)

        note = Gtk.Label()
        note.set_markup(
            "<span foreground='#888'>The next step will install the full system.\n"
            "This may take <b>20–40 minutes</b> depending on your internet speed.\n"
            "Do not turn off your computer.</span>"
        )
        note.set_justify(Gtk.Justification.CENTER)
        note.set_line_wrap(True)
        body.pack_start(note, False, False, 0)

        page.pack_start(body, True, True, 0)
        page.pack_start(self.make_nav(
            next_label="Install Now", next_cb=lambda b: self.show_progress(
                "Installing Sovran SystemsOS",
                "Building and installing your system. This will take a while...",
                self.do_install
            )
        ), False, False, 0)
        self.set_page(page, "ready")
        return False

    # ── Worker: install ───────────────────────────────────────────────────

    def do_install(self, buf):
        GLib.idle_add(append_text, buf, "=== Running nixos-install ===\n")
        run_stream([
            "sudo", "nixos-install",
            "--root", "/mnt",
            "--flake", "/mnt/etc/nixos#nixos"
        ], buf)
        GLib.idle_add(self.show_complete)

    # ── Step 6: Complete ──────────────────────────────────────────────────

    def show_complete(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.pack_start(self.make_header("Installation Complete! 🎉", "Welcome to Sovran SystemsOS."), False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_margin_start(40)
        body.set_margin_end(40)
        body.set_margin_top(16)

        icon = Gtk.Label()
        icon.set_markup("<span font='48'>🎉</span>")
        body.pack_start(icon, False, False, 0)

        creds_frame = Gtk.Frame(label=" Write down your login details ")
        creds_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        creds_inner.set_margin_top(10)
        creds_inner.set_margin_bottom(10)
        creds_inner.set_margin_start(16)
        creds_inner.set_margin_end(16)

        user_lbl = Gtk.Label()
        user_lbl.set_markup("<b>Username:</b>  free")
        user_lbl.set_halign(Gtk.Align.START)
        creds_inner.pack_start(user_lbl, False, False, 0)

        pass_lbl = Gtk.Label()
        pass_lbl.set_markup("<b>Password:</b>  free")
        pass_lbl.set_halign(Gtk.Align.START)
        creds_inner.pack_start(pass_lbl, False, False, 0)

        creds_frame.add(creds_inner)
        body.pack_start(creds_frame, False, False, 0)

        note = Gtk.Label()
        note.set_markup(
            "🚨 <b>Do not lose this password</b> — you will be permanently locked out if you forget it.\n\n"
            "📁 After rebooting, your system will finish setting up and save all app passwords\n"
            "(Nextcloud, Bitcoin, Matrix, etc.) to a secure PDF in your <b>Documents</b> folder."
        )
        note.set_line_wrap(True)
        note.set_max_width_chars(65)
        note.set_justify(Gtk.Justification.CENTER)
        body.pack_start(note, False, False, 0)

        page.pack_start(body, True, True, 0)

        reboot_btn = Gtk.Button(label="Reboot Now")
        reboot_btn.get_style_context().add_class("suggested-action")
        reboot_btn.connect("clicked", lambda b: subprocess.run(["sudo", "reboot"]))
        nav = Gtk.Box()
        nav.set_margin_bottom(20)
        nav.set_margin_end(40)
        nav.pack_end(reboot_btn, False, False, 0)
        page.pack_start(nav, False, False, 0)

        self.set_page(page, "complete")
        return False


if __name__ == "__main__":
    win = InstallerWindow()
    Gtk.main()