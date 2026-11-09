{ config, lib, ... }:

{
  ###########################################################
  #                                                         #
  #              Sovran_SystemsOS — custom.nix              #
  #                                                         #
  #  Services, features, and roles are managed by the       #
  #  Sovran Hub. Any changes you make through the Hub       #
  #  will appear in a Hub Managed section added             #
  #  automatically below.                                   #
  #                                                         #
  #  If you want to add your own NixOS modules or           #
  #  configuration, place them here — outside of the        #
  #  Hub Managed section.                                   #
  #                                                         #
  #  After making changes, rebuild with:                    #
  #                                                         #
  #       nixos-rebuild switch                               #
  #                                                         #
  ###########################################################

  # ─── Add your custom NixOS configuration below ───────────

  # ─── Mullvad VPN (Desktop Only) ───────────────────────────
  # Installed on the Desktop Role as the stock NixOS service; account, relay
  # and settings belong to the app. To take it off a Desktop machine:
  # services.mullvad-vpn.enable = lib.mkForce false;

  # ─── SSH (Desktop Only ships none by default) ─────────────
  # Desktop Only has no sshd daemon, no factory SSH key/passphrase and no
  # Hub SSH feature. To add SSH later, use the stock NixOS module here and
  # rebuild with `nixos-rebuild switch`:
  #
  # services.openssh = {
  #   enable = true;
  #   # NixOS opens TCP 22 by default; keep it closed for loopback-only SSH:
  #   # openFirewall = false;
  #   settings = {
  #     PasswordAuthentication = false;
  #     KbdInteractiveAuthentication = false;
  #     PermitRootLogin = "prohibit-password";
  #   };
  # };
  # users.users.root.openssh.authorizedKeys.keys = [
  #   "ssh-ed25519 AAAA... you@host"
  # ];
  # networking.firewall.allowedTCPPorts = [ 22 ];  # only for remote access
  #
  # Server + Desktop and Bitcoin Node already have a loopback-only sshd and
  # the Hub's SSH Remote Access toggle, so this is normally only needed on
  # Desktop Only.

  # ─── Custom Caddy virtual hosts ──────────────────────────
  # Uncomment and edit below to add your own Caddy sites:
  #
  # sovran_systemsOS.caddy.extraVirtualHosts = ''
  #   mysite.example.com {
  #     encode gzip zstd
  #     root * /var/lib/www/mysite
  #     php_fastcgi unix//run/phpfpm/mypool.sock
  #     file_server browse
  #   }
  #
  #   anotherdomain.com {
  #     reverse_proxy localhost:9090
  #   }
  # '';

}