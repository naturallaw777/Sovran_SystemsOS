{ config, lib, ... }:

{
  options.sovran_systemsOS = {
    roles = {
      server-desktop = lib.mkOption {
        type = lib.types.bool;
        default = !config.sovran_sovransystemsOS.roles.desktop && !config.sovran_systemsOS.roles.node;
      };
      desktop = lib.mkEnableOption "Desktop Role";
      node = lib.mkEnableOption "Bitcoin Node Only Role";
    };

    features = {
      coturn = lib.mkEnableOption "TURN server";
      synapse = lib.mkEnableOption "Matrix Synapse";
      bitcoin = lib.mkEnableOption "Bitcoin Ecosystem";
      vaultwarden = lib.mkEnableOption "Vaultwarden";
      haven = lib.mkEnableOption "Haven NOSTR relay";
      bip110 = lib.mkEnableOption "BIP-110 Bitcoin Better Money";
      mempool = lib.mkEnableOption "Bitcoin Mempool Explorer";
      element-calling = lib.mkEnableOption "Element Video and Audio Calling";
      bitcoin-core = lib.mkEnableOption "Bitcoin Core";
      rdp = lib.mkEnableOption "Gnome Remote Desktop";
    };
  };
}
