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