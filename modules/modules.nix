{ config, pkgs, lib, ... }:

{
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
    ./vaultwarden.nix
    ./haven.nix
    ./bip110.nix
    ./element-calling.nix
    ./mempool.nix
    ./bitcoin-core.nix
    ./rdp.nix
    ./bitcoinecosystem.nix
  ];
}
