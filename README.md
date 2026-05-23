<div align="center">

<img src="iso/assets/sovran-hub-icon.svg" alt="Sovran Systems" width="160" />

# Sovran_SystemsOS

`Base Development` · NixOS Flake · AGPL-3.0

[Sovran Systems](https://sovransystems.com)

</div>

---

## Table of Contents

1. [What This Repo Is](#what-this-repo-is)
2. [Architecture](#architecture)
3. [Module Catalog](#module-catalog)
4. [The Three Modes (internal reference)](#the-three-modes-internal-reference)
5. [Build & Deploy Reference](#build--deploy-reference)
6. [Networking & Reverse Proxy](#networking--reverse-proxy)
7. [Security Posture](#security-posture)
8. [Backups & Recovery](#backups--recovery)
9. [License](#license)

---

## What This Repo Is

Sovran_SystemsOS is defined entirely as a **Nix flake** (`flake.nix`) and built from source. There is no pre-built binary — the System Installer is produced from this tree. Everything the system does is declared here.

The control center is the **Hub** — a built-in panel that lets the operator launch, monitor, and toggle services without touching a terminal. Under the hood, the Hub writes to `custom.nix`, which feeds back into the flake.

## Architecture

```
                        ┌─────────────────────────┐
                        │        flake.nix        │
                        │  inputs: nixpkgs,       │
                        │  nix-bitcoin, nixvim,   │
                        │  btc-clients, bip110    │
                        └───────────┬─────────────┘
                                    │ nixosModules.Sovran_SystemsOS
                                    ▼
   ┌──────────────────────────┐   imports   ┌──────────────────────────┐
   │      configuration.nix   │────────────▶│      modules/modules.nix │
   │ boot / fs / users /      │             │ core/* + services + opt  │
   │ desktop / nix settings   │             │ features                 │
   └──────────────────────────┘             └──────────┬───────────────┘
            ▲                                          │
            │ ./role-state.nix (mode/role)             ▼
            │ ./custom.nix      (user overrides) ┌────────────────────┐
            │                                    │ modules/*.nix      │
            └───────── sovran-hub writes ───────▶│ synapse / wordpress│
                                                 │ nextcloud / etc.   │
                                                 └────────────────────┘
```

- **`flake.nix`** declares two NixOS configurations:
  - `nixosConfigurations.nixos` — the running system.
  - `nixosConfigurations.sovran_systemsos-iso` — the System Installer.
- **`configuration.nix`** owns host concerns (boot, filesystems, users, desktop, locale, Nix settings, firewall, audio, backups).
- **`modules/modules.nix`** is the service router. Every other module is opt-in via flags read from `role-state.nix` and `custom.nix`.

## Module Catalog

Defaults follow the import order in `modules/modules.nix`. Toggles live in `custom.nix` (the Hub writes them) and `role-state.nix`.

| Module | Default | Purpose |
|---|---|---|
| `core/*` | **on** | Roles, Caddy, Njalla, Hub, desktop, perf, ssh-bootstrap |
| `php.nix`, `credentials.nix` | **on** | Required by web services & secrets |
| `synapse.nix` | **on** | Matrix homeserver |
| `wordpress.nix` | **on** | WordPress + PHP-FPM vhost |
| `nextcloud.nix` | **on** | Files / calendar / contacts |
| `vaultwarden.nix` | **on** | Bitwarden-compatible secrets vault |
| `bitcoinecosystem.nix` | **on** | bitcoind/electrs/LND/RTL/BTCPay (over Tor) |
| `wallet-autoconnect.nix` | **on** | Sparrow/Bisq ↔ node handshake |
| `haven.nix` | off | Nostr relay |
| `bip110.nix` | off | Bitcoin Knots BIP-110 |
| `element-calling.nix` | off | LiveKit + JWT for E2E calling |
| `mempool.nix` | off | Mempool.space dashboard |
| `bitcoin-core.nix` | off | Standalone bitcoind |
| `rdp.nix` | off | xrdp remote desktop |
| `sshd.nix` | off | Public-facing OpenSSH |

> Tor is wired directly into the Bitcoin stack. In `modules/bitcoinecosystem.nix`, `bitcoind`, `electrs`, and `lnd` all set `tor.enforce = true` and `tor.proxy = true`, and onion services are exposed for them.

## The Three Modes (internal reference)

Selected by `role-state.nix`, resolved by `modules/core/role-logic.nix`. All three configurations are produced from this same flake.

| Mode | What's enabled on top of the base NixOS + GNOME |
|---|---|
| **Desktop** | Private daily-driver. Sparrow + Bisq included. |
| **Node** | Desktop + full Bitcoin stack (bitcoind/electrs/LND/RTL/BTCPay over Tor). |
| **Server+Desktop** | Node + self-hosting services (Synapse, Nextcloud, WordPress, Vaultwarden, Element Calling, etc.). |

## Build & Deploy Reference

Internal commands. Run from the flake root.

| Action | Command |
|---|---|
| Build the System Installer | `nix build .#nixosConfigurations.sovran_systemsos-iso.config.system.build.isoImage` |
| Switch now | `sudo nixos-rebuild switch --flake .#nixos` |
| Test in current boot only | `sudo nixos-rebuild test --flake .#nixos` |
| Stage for next boot | `sudo nixos-rebuild boot --flake .#nixos` |
| Build only (no activation) | `nixos-rebuild build --flake .#nixos` |
| Update pinned inputs | `nix flake update` (then rebuild) |
| Rollback last switch | `sudo nixos-rebuild switch --rollback` |
| Garbage-collect (>7 days) | Automatic weekly; manual: `sudo nix-collect-garbage -d` |

## Networking & Reverse Proxy

- **Firewall on by default** (`networking.firewall.enable = true`). The only port opened at host level is **UDP 5353** for mDNS (Avahi). Every other port is opened by the module that needs it.
- **Caddy** (`modules/core/caddy.nix`) terminates TLS for all HTTP services. Operator vhosts go through `sovran_systemsOS.caddy.extraVirtualHosts`.
- **Njalla** dynamic DNS (`modules/core/njalla.nix`) keeps records in sync via a 15-minute cron job.
- **Avahi** publishes `sovransystemsos.local` on the LAN.
- **Tor** is enabled with `torsocks` available. The Bitcoin stack uses it directly — see [Security Posture](#security-posture).
- **SSH:** localhost-only by default (`core/sshd-localhost.nix`). Public OpenSSH is opt-in (`modules/sshd.nix`).

## Security Posture

Facts about the defaults, straight from `configuration.nix` and the modules:

- **Reproducible builds.** Every artifact derives from `flake.lock`. The same commit produces the same OS.
- **Bitcoin stack over Tor.** In `modules/bitcoinecosystem.nix`, `bitcoind`, `electrs`, and `lnd` all set `tor.enforce = true`, and onion services are exposed for `bitcoind`, `electrs`, `lnd`, and friends.
- **Firewall on, public sshd off, RDP off, auto-login off.**
- **EFI** is mounted with `umask=0077`.
- **Kernel surface trimmed.** `boot.blacklistedKernelModules = [ "rxrpc" ];`
- **Weekly garbage collection** with `--delete-older-than 7d`.

## Backups & Recovery

`services.rsnapshot` snapshots hourly and daily to `/run/media/Second_Drive/BTCEcoandBackup/NixOS_Snapshot_Backup`:

```
backup  /home/                       localhost/
backup  /var/lib/                    localhost/
backup  /etc/nixos/                  localhost/
backup  /etc/nix-bitcoin-secrets/    localhost/
retain  hourly  5
retain  daily   5
cron    hourly  0  *  *  *  *
cron    daily   50 21 *  *  *
```

The second drive is mounted by label (`BTCEcoandBackup`) with `nofail` so a missing drive doesn't block boot.

## License

Licensed under the **GNU Affero General Public License v3.0** — see [`LICENSE`](./LICENSE).
