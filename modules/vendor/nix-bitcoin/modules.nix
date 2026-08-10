# Vendored nix-bitcoin — MINIMAL subset used by Sovran_SystemsOS
# Original source: https://github.com/fort-nix/nix-bitcoin
# Only services actually used by Sovran are kept (6 services vs 20+ upstream)
# - backups.nix removed: Sovran uses rsnapshot to Second_Drive (configuration.nix)
# - netns-isolation.nix is now a stub (requires false for nwc-wallets)
# - stubs.nix provides options for services referenced but not in nixpkgs unstable 2026-08
{
  imports = [
    ./stubs.nix
    ./nix-bitcoin.nix
    ./secrets/secrets.nix
    ./operator.nix
    ./bitcoind.nix
    ./electrs.nix
    ./lnd.nix
    ./lndconnect.nix
    ./rtl.nix
    ./btcpayserver.nix
    ./mempool.nix
    ./security.nix
    ./onion-addresses.nix
    ./onion-services.nix
    ./netns-isolation.nix
    ./nodeinfo.nix
    ./versioning.nix
  ];

  disabledModules = [ "services/networking/bitcoind.nix" ];
}
