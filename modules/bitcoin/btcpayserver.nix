{ config, lib, pkgs, ... }:

with lib;
let
  options.services = {
    nbxplorer = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = ''
          Enable nbxplorer, a lightweight API for Bitcoin HD wallets.

          Access API documentation here:
          {option}`services.nbxplorer.address`:{option}`services.nbxplorer.port`
        '';
      };
      address = mkOption {
        type = types.str;
        default = "127.0.0.1";
        description = "Address to listen on.";
      };
      port = mkOption {
        type = types.port;
        default = 24444;
        description = "Port to listen on.";
      };
      package = mkOption {
        type = types.package;
        default = pkgs.stable.nbxplorer;
        defaultText = "pkgs.stable.nbxplorer";
        description = "The package providing nbxplorer binaries.";
      };
      dataDir = mkOption {
        type = types.path;
        default = "/var/lib/nbxplorer";
        description = "The data directory for nbxplorer.";
      };
      # TODO-EXTERNAL:
      # The shortcut link `main` in the datadir has changed to a directory
      # in version 2.3.3.
      # Add a dummy symlink, if it does not already exist, to be compatible with older modules.
      # When the old system uses a link and the new system a directory, switching fails with:
      #   mv: cannot move '/var/lib/nbxplorer/Main' to '/var/lib/nbxplorer/.Main.tmp':
      #   No such file or directory
      #
      # Remove this option when it is irrelevant (i.e. when the old system will never
      # be nix-bitcoin <=0.0.91)
      addNetworkSymlink = mkOption {
        readOnly = true;
        default = pkgs.stable.nbxplorer != cfg.nbxplorer.package;
        description = ''
          Whether to add a compatibility symlink (like `${cfg.nbxplorer.dataDir}/Main`)
          to the dataDir.
          This is enabled by default if the nbxplorer package is set to the version-locked package.
        '';
      };
      user = mkOption {
        type = types.str;
        default = "nbxplorer";
        description = "The user as which to run NBXplorer.";
      };
      group = mkOption {
        type = types.str;
        default = cfg.nbxplorer.user;
        description = "The group as which to run NBXplorer.";
      };
      tor = nbLib.tor;
    };

    btcpayserver = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = ''
          Enable BTCPay Server, a self-hosted, open-source payment processor.

          Extra recommendations:
          - Enable `services.btcpayserver.lightningBackend` to provide Lightning payment support.
          - Secure this service if the instance is publically accessible. For example, set
            {option}`services.btcpayserver.address` to `127.0.0.1` and use a reverse proxy
            that enforces TLS (Transport Layer Security).
        '';
      };
      package = mkOption {
        type = types.package;
        default = pkgs.stable.btcpayserver;
        defaultText = "pkgs.stable.btcpayserver";
        description = "The package providing BTCPay Server binaries.";
      };
      address = mkOption {
        type = types.str;
        default = "127.0.0.1";
        description = "Address to listen on.";
      };
      port = mkOption {
        type = types.port;
        default = 23000;
        description = "Port to listen on.";
      };
      lightningBackend = mkOption {
        type = types.nullOr (types.enum [ "lnd" ]);
        default = null;
        description = ''
          The lightning node to use as a backend.
          Enables the node service if not already enabled.
        '';
      };
      lbtc = mkOption {
        readOnly = true;
        default = false;
        description = ''
          Enable Liquid support.
        '';
      };
      dataDir = mkOption {
        type = types.path;
        default = "/var/lib/btcpayserver";
        description = "The data directory for BTCPay Server.";
      };
      user = mkOption {
        type = types.str;
        default = "btcpayserver";
        description = "The user as which to run BTCPay Server.";
      };
      group = mkOption {
        type = types.str;
        default = cfg.btcpayserver.user;
        description = "The group as which to run BTCPay Server.";
      };
      tor = nbLib.tor;
    };
  };

  cfg = {
    inherit (config.services)
      nbxplorer
      btcpayserver
      bitcoind;
  };

  nbLib = config.nix-bitcoin.lib;

in {
  inherit options;

  config = mkMerge [
    (mkIf cfg.nbxplorer.enable {
      # For backwards compatibility only
      systemd.tmpfiles.rules = mkIf cfg.nbxplorer.addNetworkSymlink [
        "L+ '${cfg.nbxplorer.dataDir}/Main' - - - - '${cfg.nbxplorer.dataDir}/main'"
      ];

      systemd.services.nbxplorer = rec {
        wantedBy = [ "multi-user.target" ];
        requires = [ "bitcoind.service" ];
        after = requires;
        preStart = ''
          {
            echo "btcrpcuser=${cfg.bitcoind.rpc.users.btcpayserver.name}"
            echo "btcrpcpassword=$(cat ${config.nix-bitcoin.secretsDir}/bitcoin-rpcpassword-btcpayserver)"
          } >> '${cfg.nbxplorer.dataDir}/settings.config'
        '';
        serviceConfig = nbLib.defaultHardening // {
          ExecStart = "${cfg.nbxplorer.package}/bin/nbxplorer --conf=${cfg.nbxplorer.dataDir}/settings.config";
          RuntimeDirectory = "nbxplorer";
          StateDirectory = "nbxplorer";
          User = cfg.nbxplorer.user;
          Group = cfg.nbxplorer.group;
          Restart = "on-failure";
          RestartSec = "10s";
          ReadWritePaths = [ cfg.nbxplorer.dataDir ];
        } // nbLib.allowedIPAddresses cfg.nbxplorer.tor.enforce;
      };

      services.bitcoind = {
        enable = true;
        txindex = true;
      };

      users.users.${cfg.nbxplorer.user} = {
        isSystemUser = true;
        group = cfg.nbxplorer.group;
      };
      users.groups.${cfg.nbxplorer.group} = {};
    })

    (mkIf cfg.btcpayserver.enable {
      services.nbxplorer.enable = true;

      services.bitcoind = {
        rpc.users.btcpayserver = {
          name = "btcpayserver";
          passwordHMACFromFile = true;
          rpcwhitelist = [
            "getblockchaininfo"
            "getblock"
            "getblockhash"
            "getblockheader"
            "getblockstats"
            "gettransaction"
            "getrawtransaction"
            "sendrawtransaction"
            "getblockcount"
            "getbestblockhash"
            "getnetworkinfo"
            "getpeerinfo"
            "estimatesmartfee"
            "getmempoolinfo"
            "getmempoolentry"
            "getrawmempool"
            "gettxout"
            "scantxoutset"
            "importmulti"
            "listunspent"
            "getwalletinfo"
            "listtransactions"
            "listreceivedbyaddress"
            "getnewaddress"
            "uptime"
            "getrpcinfo"
          ];
        };
      };

      systemd.services.btcpayserver = rec {
        wantedBy = [ "multi-user.target" ];
        requires = [ "nbxplorer.service" ];
        after = requires;
        preStart = ''
          {
            echo "postgres=User ID=${cfg.btcpayserver.user};Host=/run/postgresql;Database=btcpayserver"
            echo "explorer.postgres=User ID=${cfg.nbxplorer.user};Host=/run/postgresql;Database=nbxplorer"
          } >> '${cfg.btcpayserver.dataDir}/settings.config'
        '';
        serviceConfig = nbLib.defaultHardening // {
          ExecStart = "${cfg.btcpayserver.package}/bin/btcpayserver --conf=${cfg.btcpayserver.dataDir}/settings.config";
          RuntimeDirectory = "btcpayserver";
          StateDirectory = "btcpayserver";
          User = cfg.btcpayserver.user;
          Group = cfg.btcpayserver.group;
          Restart = "on-failure";
          RestartSec = "10s";
          ReadWritePaths = [ cfg.btcpayserver.dataDir ];
        } // nbLib.allowedIPAddresses cfg.btcpayserver.tor.enforce;
      };

      services.postgresql = {
        enable = true;
        ensureDatabases = [ "btcpayserver" "nbxplorer" ];
        ensureUsers = [
          { name = cfg.btcpayserver.user; ensureDBOwnership = true; }
          { name = cfg.nbxplorer.user; ensureDBOwnership = true; }
        ];
      };

      users.users.${cfg.btcpayserver.user} = {
        isSystemUser = true;
        group = cfg.btcpayserver.group;
        extraGroups = optional (cfg.btcpayserver.lightningBackend == "lnd") config.services.lnd.group;
      };
      users.groups.${cfg.btcpayserver.group} = {};

      nix-bitcoin.secrets = {
        bitcoin-rpcpassword-btcpayserver.user = cfg.btcpayserver.user;
        bitcoin-HMAC-btcpayserver.user = cfg.bitcoind.user;
      };
      nix-bitcoin.generateSecretsCmds.btcpayserver = ''
        makeBitcoinRPCPassword btcpayserver
      '';
    })

    (mkIf (cfg.btcpayserver.enable && cfg.btcpayserver.lightningBackend == "lnd") {
      services.lnd = {
        enable = true;
        macaroons.btcpayserver = {
          user = cfg.btcpayserver.user;
          permissions = ''
            {"entity":"address","action":"write"},{"entity":"info","action":"read"},{"entity":"invoices","action":"read"},{"entity":"invoices","action":"write"},{"entity":"offchain","action":"read"},{"entity":"offchain","action":"write"},{"entity":"onchain","action":"read"},{"entity":"onchain","action":"write"},{"entity":"peers","action":"read"},{"entity":"peers","action":"write"}
          '';
        };
      };

      users.users.${config.services.lnd.user}.extraGroups = [ cfg.btcpayserver.group ];
    })
  ];
}
