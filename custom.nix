{ config, lib, ... }:

{
  ###########################################################
  #                                                         #
  #              Sovran_SystemsOS — custom.nix              #
  #                                                         #
  #  This is YOUR configuration file. Edit it to customize  #
  #  which services and features run on your machine.       #
  #                                                         #
  #  After making changes, rebuild with:                    #
  #                                                         #
  #       nixos-rebuild switch --impure                     #
  #                                                         #
  ###########################################################


  # ═══════════════════════════════════════════════════════════
  #  STEP 1: CHOOSE YOUR ROLE
  # ═══════════════════════════════════════════════════════════
  #
  #  Pick ONE role by uncommenting it. If none is chosen,
  #  you get the Server-Desktop role by default.
  #
  #  Server-Desktop (default):
  #    - Full server + desktop environment
  #    - All services ON by default
  #    - All features OFF by default
  #
  #  Desktop Only:
  #    - Desktop environment, no server services
  #    - All services OFF by default
  #
  #  Bitcoin Node Only:
  #    - Bitcoin ecosystem, mempool, bip110
  #    - BTCPay runs but is NOT exposed to the web
  #    - All other services OFF by default
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.roles.desktop = true;
  # sovran_systemsOS.roles.node = true;


  # ═══════════════════════════════════════════════════════════
  #  STEP 2: SERVICES (default: ON)
  # ═══════════════════════════════════════════════════════════
  #
  #  These are all ON by default in the Server-Desktop role.
  #  Set any to "false" to disable it.
  #
  #  ┌─────────────────────┬────────────────────────────────┐
  #  │ Service              │ What it does                   │
  #  ├─────────────────────┼────────────────────────────────┤
  #  │ synapse              │ Matrix Synapse homeserver      │
  #  │ bitcoin              │ Bitcoin ecosystem (bitcoind,   │
  #  │                      │   electrs, lnd, rtl, btcpay)  │
  #  │ vaultwarden          │ Vaultwarden password manager   │
  #  │ wordpress            │ WordPress website              │
  #  │ nextcloud            │ Nextcloud file hosting         │
  #  └─────────────────────┴────────────────────────────────┘
  #
  #  Example — disable WordPress and Nextcloud:
  #
  #    sovran_systemsOS.services.wordpress = false;
  #    sovran_systemsOS.services.nextcloud = false;
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.services.synapse = false;
  # sovran_systemsOS.services.bitcoin = false;
  # sovran_systemsOS.services.vaultwarden = false;
  # sovran_systemsOS.services.wordpress = false;
  # sovran_systemsOS.services.nextcloud = false;


  # ═══════════════════════════════════════════════════════════
  #  STEP 3: FEATURES (default: OFF)
  # ═══════════════════════════════════════════════════════════
  #
  #  These are all OFF by default. Set to "true" to enable.
  #
  #  ┌─────────────────────┬────────────────────────────────┐
  #  │ Feature              │ What it does                   │
  #  ├─────────────────────┼────────────────────────────────┤
  #  │ haven                │ Haven NOSTR relay              │
  #  │                      │  (requires nostr_npub below)   │
  #  │ element-calling      │ Element video/audio calls      │
  #  │                      │  (LiveKit + lk-jwt-service)    │
  #  │ mempool              │ Bitcoin Mempool Explorer        │
  #  │ bip110               │ BIP-110 Bitcoin Better Money   │
  #  │ bitcoin-core         │ Bitcoin Core (standalone)       │
  #  │ rdp                  │ GNOME Remote Desktop (RDP)     │
  #  └─────────────────────┴────────────────────────────────┘
  #
  #  Example — enable Haven and Element Calling:
  #
  #    sovran_systemsOS.features.haven = true;
  #    sovran_systemsOS.features.element-calling = true;
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.features.haven = true;
  # sovran_systemsOS.features.element-calling = true;
  # sovran_systemsOS.features.mempool = true;
  # sovran_systemsOS.features.bip110 = true;
  # sovran_systemsOS.features.bitcoin-core = true;
  # sovran_systemsOS.features.rdp = true;


  # ═══════════════════════════════════════════════════════════
  #  STEP 4: WEB EXPOSURE (controls Caddy reverse proxy)
  # ═══════════════════════════════════════════════════════════
  #
  #  These control whether a service gets a public Caddy
  #  vhost. The service itself still runs regardless.
  #
  #  ┌─────────────────────┬────────────────────────────────┐
  #  │ Option               │ Default                        │
  #  ├─────────────────────┼────────────────────────────────┤
  #  │ btcpayserver         │ true (false in Node role)      │
  #  └─────────────────────┴────────────────────────────────┘
  #
  #  Example — hide BTCPay from the web:
  #
  #    sovran_systemsOS.web.btcpayserver = false;
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.web.btcpayserver = false;


  # ═══════════════════════════════════════════════════════════
  #  STEP 5: NOSTR PUBLIC KEY (required for Haven)
  # ═══════════════════════════════════════════════════════════
  #
  #  If you enabled Haven above, paste your npub here.
  #  Haven will NOT start without a valid npub.
  #
  #  Example:
  #
  #    sovran_systemsOS.nostr_npub = "npub1abc123...";
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.nostr_npub = "";


  # ═══════════════════════════════════════════════════════════
  #  QUICK REFERENCE — COMMON SETUPS
  # ═══════════════════════════════════════════════════════════
  #
  #  ── Full Server (default, change nothing) ──────────────
  #
  #    All services ON, all features OFF.
  #    Just leave this file as-is.
  #
  #
  #  ── Server without WordPress ───────────────────────────
  #
  #    sovran_systemsOS.services.wordpress = false;
  #
  #
  #  ── Server with Haven + Element Calling ────────────────
  #
  #    sovran_systemsOS.features.haven = true;
  #    sovran_systemsOS.features.element-calling = true;
  #    sovran_systemsOS.nostr_npub = "npub1your_key_here";
  #
  #
  #  ── Bitcoin Node Only ──────────────────────────────────
  #
  #    sovran_systemsOS.roles.node = true;
  #
  #    (Gives you: bitcoind, electrs, lnd, rtl, btcpay,
  #     mempool, bip110 — no web services)
  #
  #
  #  ── Desktop Only (no server) ───────────────────────────
  #
  #    sovran_systemsOS.roles.desktop = true;
  #
  #
  #  ── Node with BTCPay web access ────────────────────────
  #
  #    sovran_systemsOS.roles.node = true;
  #    sovran_systemsOS.web.btcpayserver = true;
  #
  # ═══════════════════════════════════════════════════════════
}
