{ config, lib, ... }:
with lib;
{
  # Stubs for services that vendored nix-bitcoin modules reference
  # but are not provided by nixpkgs/nixos-unstable 2026-08-08.
  # Sovran never enables these — they just need to exist so evaluation doesn't throw
  # "option does not exist".

  options.services.clightning = mkOption { type = types.attrs; default = {}; description = "stub"; };
  options.services.clightning.enable = mkOption { type = types.bool; default = false; };
  options.services.clightning.port = mkOption { type = types.port; default = 9735; };
  options.services.clightning.dataDir = mkOption { type = types.path; default = "/var/lib/clightning"; };
  options.services.clightning.user = mkOption { type = types.str; default = "clightning"; };
  options.services.clightning.group = mkOption { type = types.str; default = "clightning"; };
  options.services.clightning.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.clightning.rpc = mkOption { type = types.attrs; default = {}; };
  options.services.clightning.networkDir = mkOption { type = types.path; default = "/var/lib/clightning/bitcoin"; };
  options.services.clightning.plugins = mkOption { type = types.attrs; default = {}; };
  options.services.clightning.plugins.clnrest = mkOption { type = types.attrs; default = {}; };
  options.services.clightning.plugins.clnrest.enable = mkOption { type = types.bool; default = false; };
  options.services.clightning.plugins.clnrest.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.clightning.plugins.clnrest.port = mkOption { type = types.port; default = 3010; };

  options.services.clightning-rest = mkOption { type = types.attrs; default = {}; };
  options.services.clightning-rest.enable = mkOption { type = types.bool; default = false; };

  options.services.liquidd = mkOption { type = types.attrs; default = {}; };
  options.services.liquidd.enable = mkOption { type = types.bool; default = false; };
  options.services.liquidd.dataDir = mkOption { type = types.path; default = "/var/lib/liquidd"; };
  options.services.liquidd.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.liquidd.port = mkOption { type = types.port; default = 7041; };
  options.services.liquidd.rpc = mkOption { type = types.attrs; default = {}; };
  options.services.liquidd.rpc.address = mkOption { type = types.str; default = "127.0.0.1"; };
  options.services.liquidd.rpc.port = mkOption { type = types.port; default = 7040; };
  options.services.liquidd.rpcuser = mkOption { type = types.str; default = "liquiddrpc"; };
  options.services.liquidd.whitelistedPort = mkOption { type = types.port; default = 7042; };
  options.services.liquidd.group = mkOption { type = types.str; default = "liquidd"; };

  options.services.fulcrum = mkOption { type = types.attrs; default = {}; };
  options.services.fulcrum.enable = mkOption { type = types.bool; default = false; };

  options.services.lightning-loop = mkOption { type = types.attrs; default = {}; };
  options.services.lightning-loop.enable = mkOption { type = types.bool; default = false; };
  options.services.lightning-pool = mkOption { type = types.attrs; default = {}; };
  options.services.lightning-pool.enable = mkOption { type = types.bool; default = false; };
  options.services.joinmarket = mkOption { type = types.attrs; default = {}; };
  options.services.joinmarket.enable = mkOption { type = types.bool; default = false; };
  options.services.joinmarket-ob-watcher = mkOption { type = types.attrs; default = {}; };
  options.services.joinmarket-ob-watcher.enable = mkOption { type = types.bool; default = false; };
}
