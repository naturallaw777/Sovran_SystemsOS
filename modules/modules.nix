{ config, pkgs, lib, ... }:

{
<<<<<<< HEAD
  imports = [
    ./core/roles.nix
    ./core/role-logic.nix
    ./core/caddy.nix
    ./core/sovran-manage.nix
    ./php.nix
    ./Sovran_SystemsOS_File_Fixes_And_New_Services.nix
    ./synapse.nix
    ./coturn.nix
    ./wordpress.nix
    ./nextcloud.nix
    ./btcpayserver.nix
=======
 
  imports = [
    
    ./core/roles.nix
    ./core/role-logic.nix
    ./php.nix
    ./Sovran_SystemsOS_File_Fixes_And_New_Services.nix

    # Always imported feature modules
    ./synapse.nix
    ./coturn.nix
    ./bitcoinecosystem.nix
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
    ./vaultwarden.nix
    ./haven.nix
    ./bip110.nix
    ./element-calling.nix
    ./mempool.nix
    ./bitcoin-core.nix
    ./rdp.nix
<<<<<<< HEAD
    ./bitcoinecosystem.nix
  ];
=======

  ];

>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
}
