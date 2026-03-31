  monitoredServices =
    # ── Always-on infrastructure ───────────────────────────────
    [
      { name = "Caddy"; unit = "caddy.service"; type = "system"; icon = "caddy"; enabled = true; }
      { name = "Tor";   unit = "tor.service";   type = "system"; icon = "tor";   enabled = true; }
    ]
    # ── Bitcoin ecosystem ──────────────────────────────────────
    ++ [
      { name = "Bitcoind";           unit = "bitcoind.service";     type = "system"; icon = "bitcoind";      enabled = cfg.services.bitcoin; }
      { name = "Electrs";            unit = "electrs.service";      type = "system"; icon = "electrs";       enabled = cfg.services.bitcoin; }
      { name = "LND";                unit = "lnd.service";          type = "system"; icon = "lnd";           enabled = cfg.services.bitcoin; }
      { name = "Ride The Lightning"; unit = "rtl.service";          type = "system"; icon = "rtl";           enabled = cfg.services.bitcoin; }
      { name = "BTCPayserver";       unit = "btcpayserver.service"; type = "system"; icon = "btcpayserver";  enabled = cfg.services.bitcoin; }
    ]
    # ── Other services ─────────────────────────────────────────
    ++ [
      { name = "Matrix-Synapse"; unit = "matrix-synapse.service";   type = "system"; icon = "synapse";      enabled = cfg.services.synapse; }
      { name = "VaultWarden";    unit = "vaultwarden.service";      type = "system"; icon = "vaultwarden";  enabled = cfg.services.vaultwarden; }
      { name = "Nextcloud";      unit = "phpfpm-nextcloud.service"; type = "system"; icon = "nextcloud";    enabled = cfg.services.nextcloud; }
      { name = "WordPress";      unit = "phpfpm-wordpress.service"; type = "system"; icon = "wordpress";    enabled = cfg.services.wordpress; }
    ]
    # ── Optional features ──────────────────────────────────────
    ++ [
      { name = "Haven Relay";   unit = "haven-relay.service"; type = "system"; icon = "haven";   enabled = cfg.features.haven; }
      { name = "Mempool";       unit = "mempool.service";     type = "system"; icon = "mempool"; enabled = cfg.features.mempool; }
      { name = "Element-Call";  unit = "livekit.service";     type = "system"; icon = "livekit"; enabled = cfg.features.element-calling; }
    ];