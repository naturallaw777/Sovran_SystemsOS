{ lib, ... }:
with lib;
{
  # Stubs for services referenced by vendored nix-bitcoin modules but not in nixpkgs
  # clightning and clightning-rest are NOT stubbed - they exist in some nixpkgs (f13ff45) but not others (8b8c811)
  # and have different option structures (plugins only, no enable). Handled via guards, not stubs.
  # Other services don't exist in either nixpkgs version, so unconditional is safe.

  options.services.liquidd.enable = mkOption { type = types.bool; default = false; };
  options.services.liquidd.dataDir = mkOption { type = types.path; default = "/var/lib/liquidd"; };
  options.services.liquidd.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.liquidd.port = mkOption { type = types.port; default = 7041; };
  options.services.liquidd.rpc.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.liquidd.rpc.port = mkOption { type = types.port; default = 7040; };
  options.services.liquidd.rpcuser = mkOption { type = types.str; default = "liquiddrpc"; };
  options.services.liquidd.whitelistedPort = mkOption { type = types.port; default = 7042; };
  options.services.liquidd.group = mkOption { type = types.str; default = "liquidd"; };

  options.services.fulcrum.enable = mkOption { type = types.bool; default = false; };

  options.services.lightning-loop.enable = mkOption { type = types.bool; default = false; };
  options.services.lightning-pool.enable = mkOption { type = types.bool; default = false; };
  options.services.joinmarket.enable = mkOption { type = types.bool; default = false; };
  options.services.joinmarket-ob-watcher.enable = mkOption { type = types.bool; default = false; };
}
