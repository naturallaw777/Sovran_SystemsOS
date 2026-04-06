{ config, lib, pkgs, ... }:

{
  # ── Always-on localhost SSH ────────────────────────────────────
  # Provides "ssh root@localhost" for local root access and Hub
  # operations. Binds exclusively to 127.0.0.1 — zero network exposure.
  # The sshd *feature flag* in sshd.nix extends this to 0.0.0.0 and
  # opens port 22 on the firewall when the user enables remote SSH.

  services.openssh = {
    enable = true;
    listenAddresses = lib.mkDefault [
      { addr = "127.0.0.1"; port = 22; }
    ];
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "yes";
    };
  };
}