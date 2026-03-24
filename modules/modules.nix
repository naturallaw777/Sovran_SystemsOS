{ config, pkgs, lib, ... }:

{
  imports =
    [
      ./core/roles.nix
      ./core/role-logic.nix
      ./php.nix
      ./Sovran_SystemsOS_File_Fixes_And_New_Services.nix
    ]
    ++ lib.optional config.sovran_systemsOS.features.synapse ./synapse.nix
    ++ lib.optional config.sovran_systemsOS.features.coturn ./coturn.nix
    ++ lib.optional config.sovran_systemsOS.features.bitcoin ./bitcoinecosystem.nix
    ++ lib.optional config.sovran_systemsOS.features.vaultwarden ./vaultwarden.nix
    ++ lib.optional config.sovran_systemsOS.features.haven ./haven.nix
    ++ lib.optional config.sovran_systemsOS.features.bip110 ./bip110.nix
    ++ lib.optional config.sovran_systemsOS.features.element-calling ./element-calling.nix
    ++ lib.optional config.sovran_systemsOS.features.mempool ./mempool.nix
    ++ lib.optional config.sovran_systemsOS.features.bitcoin-core ./bitcoin-core.nix
    ++ lib.optional config.sovran_systemsOS.features.rdp ./rdp.nix;
}
