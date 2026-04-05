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
  #       nixos-rebuild switch                #
  #                                                         #
  ###########################################################


  # ═══════════════════════════════════════════════════════════
  #  STEP 1: CHOOSE YOUR ROLE
  # ═══════════════════════════════════════════════════════════
  #
  #  Your initial role was selected during installation. 
  #  To CHANGE your role, uncomment exactly ONE of the lines below.
  #
  #  Server+Desktop: Full server + desktop environment
  #  Desktop Only: Desktop environment, no server services
  #  Node (Bitcoin Only): Bitcoin ecosystem
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.roles.server_plus_desktop = true;
  # sovran_systemsOS.roles.desktop = true;
  # sovran_systemsOS.roles.node = true;


  # ═══════════════════════════════════════════════════════════
  #  STEP 2: SERVICES (default: ON)
  # ═══════════════════════════════════════════════════════════
  #
  #  These are all ON by default in the Server+Desktop role.
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

  # sovran_systemsOS.services.wordpress = false;


  # ═══════════════════════════════════════════════════════════
  #  STEP 3: FEATURES (default: OFF)
  # ═══════════════════════════════════════════════════════════
  #
  #  These are OFF by default. Set to "true" to enable.
  #
  #  ┌─────────────────────┬────────────────────────────────┐
  #  │ Feature              │ What it does                   │
  #  ├─────────────────────┼────────────────────────────────┤
  #  │ haven                │ Haven NOSTR relay & Blossom    │
  #  │ bip110               │ BIP-110 Bitcoin Better Money   │
  #  │ mempool              │ Mempool.space block explorer   │
  #  │ element-calling      │ LiveKit server for Matrix      │
  #  │ rdp                  │ GNOME Remote Desktop (RDP)     │
  #  │ bitcoin-core         │ Bitcoin Core GUI desktop app   │
  #  │ sshd                 │ SSH remote access (for support) │
  #  └─────────────────────┴─────���──────────────────────────┘
  #
  #  Example — enable element video calling:
  #
  #    sovran_systemsOS.features.element-calling = true;
  #
  # ───────────────────────────────────────────────────────────

  # sovran_systemsOS.features.element-calling = true;


  # ═══════════════════════════════════════════════════════════
  #  STEP 4: WEB EXPOSURE (default: ON)
  # ═══════════════════════════════════════════════════════════
  #
  #  Controls whether Caddy serves this application to the web.
  #  (Does not stop the application itself from running).
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

}
