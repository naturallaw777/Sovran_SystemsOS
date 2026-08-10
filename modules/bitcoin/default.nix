# Sovran Bitcoin stack - tailored from nix-bitcoin, lnd-only, nixpkgs packages
# Original: https://github.com/fort-nix/nix-bitcoin
{
  imports = [
    ./common.nix
    ./bitcoind.nix
    ./electrs.nix
    ./lnd.nix
    ./lndconnect.nix
    ./rtl.nix
    ./btcpayserver.nix
    ./mempool.nix
    ./stubs.nix
  ];

  disabledModules = [ "services/networking/bitcoind.nix" ];
}
