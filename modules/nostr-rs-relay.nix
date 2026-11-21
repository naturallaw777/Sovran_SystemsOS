{ config, pkgs, lib, ... }:

# ── nostr-rs-relay — personal NOSTR relay ────────────────────────────────────
# Self-hosted, single-process Nostr relay (Rust, SQLite). Replaces the old
# Haven relay: connects to the same Caddy / domain / Hub integration points
# but uses the upstream NixOS module (services.nostr-rs-relay) instead of
# Haven's bespoke settings.
#
# Access model: the relay is publicly readable. If sovran_systemsOS.nostr_pubkey
# is set to a 64-character hex Nostr public key, the relay only accepts writes
# from that key ([authorization] pubkey_whitelist) — the same "private outbox"
# semantics the Haven module offered. If it is empty the relay accepts writes
# from anyone (fully open); the Hub refuses to enable the feature without a
# pubkey, and the assertion below catches hand-written custom.nix mistakes.
#
# Note: nostr-rs-relay wants hex public keys (NOT npub1... bech32). The Haven
# npub setting does not carry over.

let
  rawPubkey = config.sovran_systemsOS.nostr_pubkey;
  pubkey = lib.strings.toLower rawPubkey;
  pubkeySet = pubkey != "";
  pubkeyOk = builtins.match "[0-9a-f]{64}" pubkey != null;
in

lib.mkIf config.sovran_systemsOS.features.nostr-rs-relay {

  assertions = [
    {
      assertion = !pubkeySet || pubkeyOk;
      message = ''
        sovran_systemsOS.nostr_pubkey must be a 64-character hex Nostr public key
        (e.g. the output of tools like `nostril --pubkey` or the hex form shown
        in your Nostr client) — npub1... bech32 strings are NOT accepted.
        Leave it empty for an open (publicly writable) relay, or set it via the
        Sovran Hub.
      '';
    }
  ];

  services.nostr-rs-relay = {
    enable = true;
    # Reuse the port the retired Haven relay listened on; Caddy proxies to it.
    port = 3355;
    # The generated config already points the SQLite database at this path
    # (/var/lib/nostr-rs-relay/nostr.db) and the systemd unit grants
    # read/write access to it via StateDirectory=.
    dataDir = "/var/lib/nostr-rs-relay";
    settings = {
      info = {
        name = "Sovran Systems Nostr Relay";
        description = "Personal NOSTR relay running on Sovran_SystemsOS";
        # info.pubkey is the operator's hex pubkey (NIP-11); advertised only
        # when one is configured.
      } // lib.optionalAttrs pubkeySet { pubkey = pubkey; };
      network = {
        # Bind to loopback only — Caddy is the sole entry point (it enforces
        # the public domain, TLS, and host-header routing). Nothing is served
        # to the LAN directly on port 3355.
        address = "127.0.0.1";
      };
      options = {
        reject_future_seconds = 3600;
      };
    } // lib.optionalAttrs pubkeySet {
      authorization = {
        # Only the operator may publish; anyone may read.
        pubkey_whitelist = [ pubkey ];
      };
    };
  };

  sovran_systemsOS.domainRequirements = [
    { name = "nostr-rs-relay"; label = "Nostr Relay"; example = "relay.yourdomain.com"; }
  ];
}
