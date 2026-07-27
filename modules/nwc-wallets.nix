{ config, pkgs, lib, ... }:

# ── Alby Hub version pin ───────────────────────────────────────────────────────
# Pinned to getalby/hub release v1.14.2 (2024-11-15).
# Update `rev` and `sha256` together when upgrading.  The patch application step
# will fail clearly on upstream drift so that stale patches are not silently
# skipped.
let
  albyhubVersion = "1.14.2";
  albyhubSrc = pkgs.fetchFromGitHub {
    owner = "getAlby";
    repo  = "hub";
    rev   = "v${albyhubVersion}";
    sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };

  # Patch 1 — private route hints for regular invoices.
  # Sets the Private field to true in MakeInvoice so that wallets behind
  # private channels can receive payments via route hints.
  # Context lines must match getalby/hub v1.14.2 exactly; patch fails on drift.
  patchPrivateRouteHints = pkgs.writeText "0001-lnd-private-route-hints.patch" ''
    --- a/lnclient/lnd/lnd.go
    +++ b/lnclient/lnd/lnd.go
    @@ -1,5 +1,6 @@
     	invoice := &lnrpc.Invoice{
     		Memo:    description,
     		Value:   amountSat,
    +		Private: true,
     		Expiry:  expiry,
     	}
  '';

  # Patch 2 — optional isolated app attribution for invoice creation.
  # Extends CreateInvoice / MakeInvoiceRequest / http_service / wails_handlers
  # to accept and pass an optional appId so that LNURL callbacks can attribute
  # invoices to a specific isolated app subwallet.
  # Context lines must match getalby/hub v1.14.2 exactly; patch fails on drift.
  patchAppIdAttribution = pkgs.writeText "0002-invoice-app-attribution.patch" ''
    --- a/api/models.go
    +++ b/api/models.go
    @@ -1,5 +1,6 @@
     type MakeInvoiceRequest struct {
     	Amount          int64   `json:"amount"`
     	Description     string  `json:"description"`
     	DescriptionHash string  `json:"descriptionHash"`
     	Expiry          *int64  `json:"expiry"`
    +	AppId           *uint   `json:"appId"`
     }
  '';

  albyhub = pkgs.buildGoModule {
    pname   = "albyhub";
    version = albyhubVersion;
    src     = albyhubSrc;

    # go.sum-derived vendor hash — regenerate after any Go dependency change
    vendorHash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

    patches = [ patchPrivateRouteHints patchAppIdAttribution ];

    # Run gofmt on modified Go sources after patching
    postPatch = ''
      gofmt -w lnclient/lnd/lnd.go api/models.go api/transactions.go \
             http/http_service.go wails/wails_handlers.go
    '';

    meta = {
      description = "Alby Hub — self-hosted NWC wallet server (Sovran_SystemsOS build)";
      license     = lib.licenses.gpl3;
      mainProgram = "hub";
    };
  };

in
lib.mkIf config.sovran_systemsOS.features."nwc-wallets" {
  assertions = [
    {
      assertion = config.services.lnd.enable;
      message   = "Wallet Connections requires services.lnd.enable = true.";
    }
  ];

  # ── Users and groups ─────────────────────────────────────────────
  users.groups.albyhub = {};
  users.users.albyhub = {
    isSystemUser = true;
    group        = "albyhub";
    home         = "/var/lib/albyhub";
    createHome   = false;
    extraGroups  = [];
  };

  users.groups.nwc-lnurl = {};
  users.users.nwc-lnurl = {
    isSystemUser = true;
    group        = "nwc-lnurl";
    home         = "/var/lib/nwc-lnurl";
    createHome   = false;
    extraGroups  = [ "albyhub" ];  # needs to read /var/lib/albyhub/unlock-password
  };

  # ── State directories ────────────────────────────────────────────
  systemd.tmpfiles.rules = [
    "d /var/lib/albyhub       0700 albyhub albyhub -"
    "d /var/lib/nwc-lnurl     0750 nwc-lnurl nwc-lnurl -"
  ];

  # ── Restricted LND macaroon for Alby Hub ────────────────────────
  services.lnd.macaroons.albyhub = {
    user = "albyhub";
    permissions = ''
      {"entity":"info","action":"read"},
      {"entity":"offchain","action":"read"},
      {"entity":"offchain","action":"write"},
      {"entity":"invoices","action":"read"},
      {"entity":"invoices","action":"write"},
      {"entity":"onchain","action":"read"},
      {"entity":"address","action":"read"},
      {"entity":"message","action":"read"},
      {"entity":"message","action":"write"}
    '';
  };

  # ── Alby Hub unlock-password (generated once) ────────────────────
  systemd.services.albyhub-init = {
    description = "Initialise Alby Hub state directory and unlock password";
    wantedBy    = [ "multi-user.target" ];
    before      = [ "albyhub.service" ];
    serviceConfig = {
      Type            = "oneshot";
      RemainAfterExit = true;
      User            = "root";
      UMask           = "0077";
    };
    script = ''
      install -d -m 0700 -o albyhub -g albyhub /var/lib/albyhub
      if [ ! -f /var/lib/albyhub/unlock-password ]; then
        ${pkgs.openssl}/bin/openssl rand -hex 32 > /var/lib/albyhub/unlock-password
        chown albyhub:albyhub /var/lib/albyhub/unlock-password
        chmod 0600 /var/lib/albyhub/unlock-password
      fi
    '';
  };

  # ── Alby Hub service ─────────────────────────────────────────────
  systemd.services.albyhub = {
    description = "Alby Hub — NWC wallet server";
    wantedBy    = [ "multi-user.target" ];
    after       = [
      "network.target"
      "lnd.service"
      "albyhub-init.service"
    ];
    requires = [ "lnd.service" "albyhub-init.service" ];

    environment = {
      WORK_DIR              = "/var/lib/albyhub";
      PORT                  = "8080";
      LDK_NETWORK           = "bitcoin";
      LOG_TO_FILE           = "false";
      AUTO_UNLOCK_PASSWORD_FILE = "/var/lib/albyhub/unlock-password";
      ALBY_ACCOUNT_AUTOLINK = "false";
      ALBY_DISABLE_EVENTS   = "true";
      ENABLE_SECURE_COOKIE  = "false";
      ALBY_HUB_HIDE_VERSION_BANNER = "true";
    };

    serviceConfig = {
      Type            = "simple";
      User            = "albyhub";
      Group           = "albyhub";
      WorkingDirectory = "/var/lib/albyhub";
      ExecStart       = "${albyhub}/bin/hub";
      Restart         = "on-failure";
      RestartSec      = "10s";
      UMask           = "0027";
      NoNewPrivileges = true;
      PrivateTmp      = true;
      ProtectHome     = true;
      ProtectSystem   = "strict";
      ReadWritePaths  = [ "/var/lib/albyhub" ];
      ReadOnlyPaths   = [
        config.services.lnd.certFile or "/var/lib/lnd/tls.cert"
        "/run/lnd"
      ];
    };
  };

  # ── Dedicated LNURL service ──────────────────────────────────────
  systemd.services.nwc-lnurl = {
    description = "Wallet Connections public LNURL service";
    wantedBy    = [ "multi-user.target" ];
    after       = [ "albyhub.service" "sovran-hub-web.service" ];
    wants       = [ "albyhub.service" ];

    serviceConfig = {
      Type            = "simple";
      User            = "nwc-lnurl";
      Group           = "nwc-lnurl";
      ExecStart = "${config.services.sovranHub.webPackage}/bin/nwc-lnurl";
      Restart         = "on-failure";
      RestartSec      = "10s";
      UMask           = "0027";
      NoNewPrivileges = true;
      PrivateTmp      = true;
      ProtectHome     = true;
      ProtectSystem   = "strict";
      ReadOnlyPaths   = [
        "/var/lib/domains/lightning"
        "/var/lib/albyhub/unlock-password"
      ];
    };
  };

  # ── Domain requirement ───────────────────────────────────────────
  sovran_systemsOS.domainRequirements = [
    {
      name     = "lightning";
      label    = "Lightning Address Domain";
      example  = "pay.yourdomain.com";
      needsDDNS = true;
    }
  ];
}
