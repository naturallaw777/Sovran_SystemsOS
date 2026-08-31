# Sovran Bitcoin integration layer — bridges Sovran_SystemsOS options to the
# Sovran_Bitcoin flake module.
#
# This is the ONLY place where OS-specific Bitcoin customizations live.
# All bitcoin service modules (bitcoind, electrs, lnd, rtl, btcpayserver,
# mempool, albyhub, lnurl) and vendored packages come from the Sovran_Bitcoin
# flake input.
#
# What this file does:
#   1. Maps sovran_systemsOS.services.bitcoin → sovran-bitcoin.enable
#   2. Maps sovran_systemsOS.features.* → sovran-bitcoin.features.*
#   3. Applies OS-specific overrides (Second_Drive paths, operator "free",
#      forced wallet enable, Hub firewall port, domain requirements)
#   4. Wires the Sovran Hub's NWC environment to the Alby Hub service
{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS;

  # ── NWC environment for the Sovran Hub web app ─────────────────
  # The Hub's web package provides nwc-wallet and nwc-lnurl binaries that
  # need to know where Alby Hub and LND are.  Sovran_Bitcoin's modules
  # handle the base Alby Hub service; this layers on the Hub-specific
  # tooling environment.
  lndRpcAddress = config.services.lnd.rpcAddress or "127.0.0.1";
  lndRpcPort = toString (config.services.lnd.rpcPort or 10009);
  lndCertPath = config.services.lnd.certPath or "/var/lib/lnd/tls.cert";

  hubNwcEnvironment = {
    NWC_ALBY_HUB_API_BASE = "http://127.0.0.1:18080";
    NWC_LND_ADDRESS = "${lndRpcAddress}:${lndRpcPort}";
    NWC_LND_CERT_FILE = lndCertPath;
    NWC_LND_MACAROON_FILE = "/run/lnd/albyhub.macaroon";
    NWC_RELAY =
      if cfg.features.haven
      then "wss://haven.${config.networking.domain}/nostr"
      else "wss://relay.getalby.com,wss://relay2.getalby.com";
  };
in {
  # ── 1. Map OS options → Sovran_Bitcoin options ─────────────────
  sovran-bitcoin = lib.mkIf cfg.services.bitcoin {
    enable = true;
    operatorName = "free";
    bitcoindTorGossip = cfg.features.bitcoin-tor-gossip;

    features = {
      electrs = true;
      lnd = true;
      rtl = true;
      btcpayserver = cfg.web.btcpayserver;
      mempool = cfg.features.mempool;
      nwc = cfg.features."nwc-wallets";
      lnurl = cfg.features."nwc-wallets";
    };
  };

  # ── 2. Second_Drive data paths (OS-specific) ──────────────────
  services.bitcoind = lib.mkIf cfg.services.bitcoin {
    dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node";
    # The OS always enables the bitcoind wallet — the Hub and BTCPay need it.
    disableWallet = lib.mkForce false;
  };

  services.electrs = lib.mkIf cfg.services.bitcoin {
    dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data";
  };

  # ── 3. Second_Drive mount dependencies ─────────────────────────
  systemd.services.bitcoind = lib.mkIf cfg.services.bitcoin {
    requires = [ "run-media-Second_Drive.mount" ];
    after    = [ "run-media-Second_Drive.mount" ];
    serviceConfig.PrivateUsers = lib.mkForce false;
  };

  systemd.services.electrs = lib.mkIf cfg.services.bitcoin {
    requires = lib.mkForce [ "run-media-Second_Drive.mount" ];
    after    = [ "run-media-Second_Drive.mount" "bitcoind.service" ];
    wants    = [ "bitcoind.service" ];
  };

  systemd.services.lnd = lib.mkIf cfg.services.bitcoin {
    wants    = [ "bitcoind.service" ];
    # nix-bitcoin sets `requires = [ "bitcoind.service" ]`; the OS removes it
    # so LND can start even if bitcoind is temporarily down.
    requires = lib.mkForce [ ];
  };

  # ── 4. Permission fixup for Second_Drive ───────────────────────
  systemd.services.sovran-btc-permissions = lib.mkIf cfg.services.bitcoin {
    description = "Fix Bitcoin/Electrs data directory ownership on second drive";
    wantedBy = [ "multi-user.target" ];
    after  = [ "run-media-Second_Drive.mount" ];
    before = [ "bitcoind.service" "electrs.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      if [ -d /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node ]; then
        chown -R bitcoin:bitcoin /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node
      fi
      if [ -d /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data ]; then
        chown -R electrs:electrs /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data
      fi
    '';
  };

  # ── 5. Firewall — Hub management port ──────────────────────────
  networking.firewall.allowedTCPPorts = lib.mkIf cfg.services.bitcoin [ 3051 ];
  networking.firewall.allowedUDPPorts = lib.mkIf cfg.services.bitcoin [ 3051 ];

  # ── 6. NWC / LNURL — Sovran Hub integration ───────────────────
  # Sovran_Bitcoin's albyhub.nix and lnurl.nix handle the base services.
  # This section wires the Hub's web app environment so the Hub can
  # display NWC status and the nwc-wallet CLI works from the Hub shell.
  systemd.services.sovran-hub-web.environment = lib.mkIf cfg.features."nwc-wallets"
    hubNwcEnvironment;

  # ── 7. Domain requirements ─────────────────────────────────────
  sovran_systemsOS.domainRequirements = lib.mkIf cfg.services.bitcoin (
    [
      { name = "btcpayserver"; label = "BTCPay Server"; example = "pay.yourdomain.com"; }
    ]
    ++ lib.optionals cfg.features."nwc-wallets" [
      { name = "lightning"; label = "Lightning Address Domain"; example = "pay.yourdomain.com"; needsDDNS = true; }
    ]
  );
}
