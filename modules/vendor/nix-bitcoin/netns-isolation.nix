{ config, lib, ... }:
with lib;
{
  options.nix-bitcoin.netns-isolation = {
    enable = mkEnableOption "netns isolation (stub — disabled in Sovran_SystemsOS)";
  };
  # No config when enabled — isolation is intentionally not implemented.
  # Sovran requires enable = false (see modules/nwc-wallets.nix assertion).
  # The original nix-bitcoin implementation (365 lines, bridge nb-br, iptables,
  # ip netns, 169.254.x.x) broke Caddy/AlbyHub/RTL and is not needed for
  # desktop/server roles. Keep stub so `nix-bitcoin.netns-isolation.enable`
  # remains a valid option.
  config = mkIf config.nix-bitcoin.netns-isolation.enable {
    warnings = [ "nix-bitcoin.netns-isolation.enable is a stub in vendored Sovran and does nothing. Set it to false." ];
  };
}
