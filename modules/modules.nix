{ config, pkgs, lib, ... }:

{
 
  imports = [
    
    ./core/roles.nix
    ./core/role-logic.nix
    ./php.nix
    ./Sovran_SystemsOS_File_Fixes_And_New_Services.nix

    # Always imported feature modules
    ./synapse.nix
    ./coturn.nix
    ./bitcoinecosystem.nix
    ./vaultwarden.nix
    ./haven.nix
    ./bip110.nix
    ./element-calling.nix
    ./mempool.nix
    ./bitcoin-core.nix
    ./rdp.nix

  ];

}
