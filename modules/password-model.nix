{ config, pkgs, lib, ... }:

# Sovran_SystemsOS -- password model cleanup (GNOME 50 / gnome-keyring 50)
#
#   * /etc/shadow is the only source of truth for authentication (Hub login == GDM login).
#   * /var/lib/secrets/{free,root}-password are root-only DISPLAY copies for the Hub, written
#     by exactly one module (system_password.py) and verified against shadow before shown.
#   * The GNOME login keyring is decoupled from the login password: it is created with a
#     blank password and pam_gnome_keyring never hands the login password to the daemon.
#     => no "unlock your login keyring" prompts, ever (also on the autologin live ISO);
#        Brave's cookie/password key survives every password change; no *.keyring wiping.
#   * Legacy machines (password unknown to the Hub) are handled by the Hub's existing
#     onboarding "migration password" step -- not by a boot service any more.
#
# Import from configuration.nix and DELETE these lines there:
#   security.pam.services.gdm-password.enableGnomeKeyring = true;
#   security.pam.services.gdm-autologin.enableGnomeKeyring = true;
#   the four systemd.tmpfiles.rules for /home/free/.local/share/keyrings/{,default}
# and in modules/credentials.nix delete root-password-setup, free-password-setup,
# free-password-migration and the `rm -f /home/free/.local/share/keyrings/*.keyring` lines.

let
  user = "free";
  home = "/home/${user}";

  # A login keyring with a blank password. gnome-keyring stores those in this textual
  # format and auto-unlocks them on demand without any prompt (verified on 48; the rule in
  # gkm-secret-collection.c that picks the textual format for a blank master is unchanged
  # in 50 and the 50.0 release notes contain no behavioural changes).
  blankLoginKeyring = pkgs.writeText "login.keyring" ''
    [keyring]
    display-name=login
    ctime=0
    mtime=0
    lock-on-idle=false
    lock-after=false
  '';

  # Apply the installer's plaintext password ONCE: only while the account still has no
  # usable hash (nixos-install --no-root-password leaves both accounts locked). After that
  # the file is display-only and the Hub (system_password.py) is the only thing that
  # writes it. This replaces the old services, which re-applied the file on EVERY boot
  # and silently reverted any password changed elsewhere.
  # On already-installed machines the case below matches `*)` (real hash) -> no-op:
  # an upgrade can never change or generate a password.
  applyOnce = { account, fallback ? false }: ''
    set -euo pipefail
    f=/var/lib/secrets/${account}-password
    hash="$(getent shadow ${account} | cut -d: -f2 || true)"
    case "$hash" in
      ""|"!"*|"*"*)
        if [ -s "$f" ] && ! grep -qE '^[0-9a-f]{32}:[0-9a-f]{64,}$' "$f"; then
          echo "${account}:$(head -n1 "$f")" | chpasswd
        ${lib.optionalString fallback ''
        else
          # Installer left no usable file: generate one so GDM is always reachable
          # (the user reads it in the Hub). Never runs once the account has a password.
          W="apple barn brook cabin cedar cloud coral crane delta eagle ember fern field flame
             flora flint frost grove haven hedge holly heron jade juniper kelp larch lemon lilac
             linden loch lotus maple marsh meadow mist mossy mount oak ocean olive petal pine
             pixel plum pond prism quartz raven ridge river robin rocky rose rowan sage sand
             sierra silver slate snow solar spark spruce stone storm summit swift thorn tide
             timber torch trout vale vault vine walnut wave willow wren"
          pw=$(for i in 1 2 3 4; do set -- $W; eval echo \${$((RANDOM % $# + 1))}; done | paste -sd- -)-$(printf '%02d' $((RANDOM % 100)))
          umask 077; printf '%s\n' "$pw" > "$f"
          echo "${account}:$pw" | chpasswd
        ''}
        fi ;;
      *) ;;  # password already set: never touch it here again
    esac
  '';
in
{
  # ── 1. Keyring: never learns the login password ───────────────────────────
  # nixpkgs' gnome-keyring module turns this on for `login` (gdm-password includes it).
  # If the daemon ever receives the login password it re-encrypts the blank keyring with
  # it on the next save -- so it must be off everywhere.
  security.pam.services.login.enableGnomeKeyring = lib.mkForce false;
  security.pam.services.gdm-password.enableGnomeKeyring = lib.mkForce false;
  security.pam.services.gdm-autologin.enableGnomeKeyring = lib.mkForce false;
  security.pam.services.passwd.enableGnomeKeyring = lib.mkForce false;

  # Seed the blank keyring. `C` copies only if the file does not exist, so an existing
  # keyring is never overwritten -- which is also what makes a reset's `rm *.keyring`
  # harmless: the next boot re-seeds a fresh blank keyring.
  systemd.tmpfiles.rules = [
    "d ${home}/.local 0700 ${user} users -"
    "d ${home}/.local/share 0700 ${user} users -"
    "d ${home}/.local/share/keyrings 0700 ${user} users -"
    "C ${home}/.local/share/keyrings/login.keyring 0600 ${user} users - ${blankLoginKeyring}"
  ];

  # One-time migration for machines that already have a keyring encrypted with the
  # (old) login password: move it aside and seed the blank one. Runs before GDM; the old
  # file is kept. Same cost users pay today on every password change (Brave logs you out
  # of sites once) -- but only once, ever.
  system.activationScripts.sovranBlankKeyring = lib.stringAfter [ "users" ] ''
    d=${home}/.local/share/keyrings
    if [ -f "$d/login.keyring" ] && ! head -c 9 "$d/login.keyring" | grep -q '^\[keyring\]'; then
      mv "$d/login.keyring" "$d/login.keyring.encrypted-$(date +%Y%m%d)"
      install -o ${user} -g users -m 0600 ${blankLoginKeyring} "$d/login.keyring"
    fi
  '';

  # ── 2. First-boot password hand-off (unit names kept: the Hub's "System Passwords"
  #       service card is bound to root-password-setup.service) ───────────────────────
  systemd.services.free-password-setup = {
    description = "Apply the installer's 'free' password (first boot only)";
    wantedBy = [ "multi-user.target" ];
    before = [ "display-manager.service" ];
    serviceConfig = { Type = "oneshot"; RemainAfterExit = true; };
    path = [ pkgs.shadow pkgs.coreutils pkgs.gnugrep pkgs.getent ];
    script = applyOnce { account = user; fallback = true; };
  };
  systemd.services.root-password-setup = {
    description = "Apply the installer's root password (first boot only)";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = { Type = "oneshot"; RemainAfterExit = true; };
    path = [ pkgs.shadow pkgs.coreutils pkgs.gnugrep pkgs.getent ];
    script = applyOnce { account = "root"; };
  };
  # Legacy detection now lives in the Hub (system_password.ensure_migration_pending).
  systemd.services.free-password-migration.enable = false;

  # ── 3. The Hub verifies passwords against /etc/shadow via libxcrypt ───────
  systemd.services.sovran-hub-web.environment.LIBCRYPT = "${pkgs.libxcrypt}/lib/libcrypt.so.1";
}
