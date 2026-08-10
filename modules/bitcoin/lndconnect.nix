{ config, lib, pkgs, ... }:

with lib;
let
  cfg = config.services.lnd;
  operatorName = config.nix-bitcoin.operator.name;
  nbLib = config.nix-bitcoin.lib;

  mkLndconnect = { name, isClightning ? false, enableOnion, onionService, port, certPath, authSecretPath }:
    let
      lnd = config.services.lnd;
      getOnionAddress = "cat ${config.nix-bitcoin.secretsDir}/onion-address-${onionService} 2>/dev/null || echo ${onionService}.onion";
    in pkgs.writeScriptBin name ''
      #!${pkgs.bash}/bin/bash
      set -e
      certPath="${certPath}"
      authSecretPath="${authSecretPath}"
      if [ "${toString enableOnion}" = "1" ]; then
        host=$(cat /var/lib/tor/onion/${onionService}/hostname 2>/dev/null || echo "${onionService}.onion")
        port="${toString port}"
      else
        host="${nbLib.address lnd.restAddress}"
        port="${toString lnd.restPort}"
      fi
      # lndconnect is provided by pkgs.lndconnect
      ${getExe pkgs.lndconnect} --host="$host" --port="$port" --cert="$certPath" --macaroon="$authSecretPath" "$@"
    '';
in {
  options.services.lnd.lndconnect = {
    enable = mkOption {
      type = types.bool;
      default = false;
      description = "Enable lndconnect for LND";
    };
    onion = mkOption {
      type = types.bool;
      default = false;
      description = "Expose lndconnect via Tor onion service";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    (mkIf cfg.lndconnect.enable {
      environment.systemPackages = [
        (mkLndconnect {
          name = "lndconnect";
          enableOnion = cfg.lndconnect.onion;
          onionService = "${operatorName}/lnd";
          port = cfg.restPort;
          certPath = cfg.certPath;
          authSecretPath = "${cfg.networkDir}/admin.macaroon";
        })
      ];
    })
    (mkIf (cfg.lndconnect.enable && cfg.lndconnect.onion) {
      services.tor.relay.onionServices.lnd = nbLib.mkOnionService {
        port = cfg.restPort;
        target = { addr = nbLib.address cfg.restAddress; port = cfg.restPort; };
      };
      nix-bitcoin.onionAddresses.access.${operatorName} = [ "lnd" ];
    })
  ]);
}
