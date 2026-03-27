{ config, lib, ... }:

{
  config = lib.mkMerge [

    # Server-Desktop Role — services already default to on,
    # so we only need to set features here
    (lib.mkIf config.sovran_systemsOS.roles.server-desktop {
      # All services are default=true, nothing to set
      # All features are default=false, nothing to set
    })

    # Desktop role
    (lib.mkIf config.sovran_systemsOS.roles.desktop {
      services.xserver.enable = true;
      services.desktopManager.gnome.enable = true;
    })

    # Bitcoin node role — only bitcoin, disable other services
    (lib.mkIf config.sovran_systemsOS.roles.node {
      sovran_systemsOS.services = {
        bitcoin = true;
        synapse = false;
        vaultwarden = false;
        wordpress = false;
        nextcloud = false;
      };
    })

  ];
}
