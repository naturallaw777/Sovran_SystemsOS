{ nixpkgs, system ? "x86_64-linux" }:
let
  pkgs = import nixpkgs { inherit system; };
in
pkgs.testers.runNixOSTest {
  name = "nwc-wallets-port-collision";

  nodes.machine = { lib, pkgs, ... }: {
    imports = [ ../../modules/nwc-wallets.nix ];

    options = {
      sovran_systemsOS.features = lib.mkOption {
        type = lib.types.attrsOf lib.types.bool;
        default = { };
      };
      sovran_systemsOS.domainRequirements = lib.mkOption {
        type = lib.types.listOf lib.types.attrs;
        default = [ ];
      };
      services.sovranHub.webPackage = lib.mkOption {
        type = lib.types.package;
      };
      services.lnd = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
        };
        rpcAddress = lib.mkOption {
          type = lib.types.str;
          default = "127.0.0.1";
        };
        rpcPort = lib.mkOption {
          type = lib.types.int;
          default = 10009;
        };
        restPort = lib.mkOption {
          type = lib.types.int;
          default = 8080;
        };
        certPath = lib.mkOption {
          type = lib.types.str;
          default = "/var/lib/lnd/tls.cert";
        };
        macaroons = lib.mkOption {
          type = lib.types.attrs;
          default = { };
        };
      };
    };

    config = {
      system.stateVersion = "24.11";
      networking.firewall.enable = true;

      sovran_systemsOS.features."nwc-wallets" = true;
      services.lnd.enable = true;
      services.lnd.restPort = 8080;

      services.sovranHub.webPackage = pkgs.writeShellApplication {
        name = "stub-sovran-hub-web";
        runtimeInputs = [ pkgs.python3 ];
        text = ''
          if [ "$(basename "$0")" = "nwc-lnurl" ]; then
            exec ${pkgs.python3}/bin/python -m http.server "''${NWC_LNURL_PORT:-8181}" --bind 127.0.0.1
          fi
          exec ${pkgs.coreutils}/bin/sleep infinity
        '';
      };

      systemd.services.sovran-hub-web = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = "${pkgs.coreutils}/bin/sleep infinity";
        };
      };

      systemd.services.lnd-prepare = {
        description = "Prepare mock LND cert and macaroon files";
        before = [ "lnd.service" "albyhub.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        script = ''
          mkdir -p /var/lib/lnd /run/lnd /var/lib/domains
          printf 'stub-cert\n' > /var/lib/lnd/tls.cert
          printf 'stub-macaroon\n' > /run/lnd/albyhub.macaroon
          printf 'lightning.example.com\n' > /var/lib/domains/lightning
        '';
      };

      systemd.services.lnd = {
        description = "Mock LND REST listener";
        after = [ "network.target" "lnd-prepare.service" ];
        requires = [ "lnd-prepare.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = "${pkgs.python3}/bin/python -m http.server 8080 --bind 127.0.0.1";
          Restart = "always";
        };
      };
    };
  };

  testScript = ''
    start_all()

    machine.wait_for_unit("lnd.service")
    machine.wait_for_unit("sovran-hub-web.service")
    machine.wait_for_unit("albyhub.service")
    machine.wait_for_unit("nwc-lnurl.service")

    machine.wait_for_open_port(8080)
    machine.wait_for_open_port(18080)
    machine.wait_for_open_port(8181)

    machine.succeed("ss -ltn '( sport = :8080 )' | grep -F '127.0.0.1:8080'")
    machine.succeed("ss -ltn '( sport = :18080 )' | grep -F '127.0.0.1:18080'")
    machine.succeed("ss -ltn '( sport = :8181 )' | grep -F '127.0.0.1:8181'")

    machine.fail("ss -ltn '( sport = :18080 )' | grep -E '0\\.0\\.0\\.0:18080|\\[::\\]:18080'")
    machine.fail("ss -ltn '( sport = :8181 )' | grep -E '0\\.0\\.0\\.0:8181|\\[::\\]:8181'")

    machine.succeed("${pkgs.curl}/bin/curl --fail --silent http://127.0.0.1:18080/api/info | ${pkgs.gnugrep}/bin/grep -q 'setupCompleted'")

    machine.succeed("systemctl show -p Environment nwc-lnurl.service | grep -q 'NWC_ALBY_HUB_API_BASE=http://127.0.0.1:18080'")
    machine.succeed("systemctl show -p Environment sovran-hub-web.service | grep -q 'NWC_ALBY_HUB_API_BASE=http://127.0.0.1:18080'")
  '';
}
