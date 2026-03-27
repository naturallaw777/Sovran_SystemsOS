{ config, lib, ... }:

{
  config = lib.mkMerge [

    # Server-Desktop Role most services enabled
    (lib.mkIf config.sovran_systemsOS.roles.server-desktop {
      sovran_systemsOS.features = {
        synapse = true;
        bitcoin = true;
        coturn = true;
        vaultwarden = true;
        haven = false;
        mempool = false;
        bip110 = false;
        element-calling = false;
        bitcoin-core = false;
        rdp = false;
      };
    })

    # Desktop role
    (lib.mkIf config.sovran_systemsOS.roles.desktop {
      services.xserver.enable = true;
      services.desktopManager.gnome.enable = true;
    })

    # Bitcoin node role
    (lib.mkIf config.sovran_systemsOS.roles.node {
      sovran_systemsOS.features = {
        bitcoin = true;
        bip110 = false;
      };
    })

  ];
}
