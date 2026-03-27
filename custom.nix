{
  # ── Disable services you don't want ─────────────
  sovran_systemsOS.services.wordpress = false;
  sovran_systemsOS.services.nextcloud = false;

  # ── Enable features you do want ─────────────────
  sovran_systemsOS.features.haven = true;
  sovran_systemsOS.features.element-calling = true;
  sovran_systemsOS.nostr_npub = "npub1abc123...";
}
