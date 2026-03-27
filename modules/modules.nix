{ config, pkgs, lib, ... }:

{
  imports = [
    # ── Core (always loaded) ──────────────────────────────────
    ./core/roles.nix
    ./core/role-logic.nix
    ./core/caddy.nix
    ./core/sovran-manage.nix

    # ── Always on (no flag) ───────────────────────────────────
    ./php.nix
    ./Sovran_SystemsOS_File_Fixes_And_New_Services.nix

    # ── Services (default ON — disable in custom.nix) ─────────
    ./synapse.nix
    ./wordpress.nix
    ./nextcloud.nix
    ./vaultwarden.nix
    ./bitcoinecosystem.nix

    # ── Features (default OFF — enable in custom.nix) ─────────
    ./haven.nix
    ./bip110.nix
    ./element-calling.nix
    ./mempool.nix
    ./bitcoin-core.nix
    ./rdp.nix
  ];
}
