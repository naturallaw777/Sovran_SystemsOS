# ── modules/mullvad.nix ───────────────────────────────────────────────────────
# Mullvad VPN client — Desktop Role only.
#
# A plain install: the daemon (pkgs.mullvad) and the graphical app
# (pkgs.mullvad-vpn) exactly as NixOS ships them, enabled and nothing more. The
# account, the relay, the kill switch and every other setting are the app's
# business; nothing here configures them, and nothing here is wired into the
# Hub or into any other part of the system.
#
# The role gate is the whole point: Server + Desktop and Bitcoin Node are
# machines that serve, and a VPN client with its own DNS and routing policy is
# not something their services asked for. Only roles.desktop builds it.
#
# Turning it off on a Desktop machine: uncomment
#   services.mullvad-vpn.enable = lib.mkForce false;
# in custom.nix (the mkForce is needed because this module sets it too).

{ config, lib, ... }:

lib.mkIf config.sovran_systemsOS.roles.desktop {

  services.mullvad-vpn = {
    # The daemon and its systemd service.
    enable = true;
    # The desktop app.
    gui.enable = true;
  };
}
