<br />
<br />

<p align="center">
  <img width="600" src="sovran_systems_grey.png">
</p>

<br />
<br />
<br />

# Sovran_SystemsOS

**A declarative, self-hosted operating system built on NixOS.**

---

## Overview

Sovran_SystemsOS is a fully integrated NixOS configuration that transforms a single machine into a personal cloud, communications hub, Bitcoin node, web server, and daily-use desktop — all managed declaratively.

Every service is pre-wired: reverse proxy routing, database initialization, firewall rules, and inter-service communication are handled out of the box. You activate what you need; the system does the rest.

---

## Architecture

Sovran_SystemsOS is structured as a set of NixOS modules exposed via a flake. A remote machine consumes the flake and selectively enables features through a simple configuration interface.

```
Remote Machine (flake.nix)
  └── Sovran_SystemsOS flake (nixosModules.Sovran_SystemsOS)
        ├── configuration.nix/       # Base system
        │   ├── Gnome Desktop        # Gnome Desktop Interface
        │   ├── caddy                # Reverse proxy + HTTPS
        │   ├── nextcloud            # Cloud storage
        │   ├── wordpress            # CMS / publishing
        │   ├── element              # Matrix Synapse via Element Messaging App
        ├── modules/
        │   ├── bitcoinecosystem.nix # Bitcoin Core / Knots / BTCPay Server / Bitcoin Lightning
        │   ├── bip110.nix           # Bip110 Node Consensus Policy
        │   ├── element-calling.nix  # Matrix Synapse via Element + Element Voice and Video Calling
        │   ├── haven.nix            # Nostr relay
        │   ├── mempool.nix          # Mempool explorer
        │   ├── rdp.nix              # Remote desktop (RDP)
        │   ├── vaultwarden.nix      # Password management
        │   └── ...
        ├── nix-bitcoin integration
        ├── agenix (secrets management)
        └── nixvim
```

## Features

### Feature Toggles

Every major service is gated behind a feature flag. Enable only what you need:

```nix
# custom.nix
{ lib, ... }:
{
  sovran_systemsOS.features = {
    bitcoin-core    = lib.mkForce true;
    bip110          = lib.mkForce true;
    element-calling = lib.mkForce true;
    haven           = lib.mkForce true;
    mempool         = lib.mkForce true;
    rdp             = lib.mkForce true;
  };
}
```

No unnecessary services run. No wasted resources.

---

### Service Stack

| Category | Service | Description |
|---|---|---|
| **Web** | Caddy | Automatic HTTPS, reverse proxy for all services |
| **Cloud** | Nextcloud | File storage, sync, and collaboration |
| **CMS** | WordPress | Self-hosted publishing and content management |
| **Passwords** | Vaultwarden | Bitwarden-compatible password vault |
| **Messaging** | Element/Matrix Synapse | Federated, decentralized messaging backend |
| **Video/Voice Calling** | Element Video and Voice Calling | Decentralized Voice Over IP for Matrix with optional TURN/STUN |
| **Bitcoin** | Bitcoin Core / Knots | Full node with optional BIP-110 consensus policy |
| **Bitcoin Lightning** | LND Full node connected over TOR |
| **Payments** | BTCPay Server | Self-hosted Bitcoin payment processor |
| **Explorer** | Mempool | Bitcoin mempool visualizer and block explorer |
| **Nostr** | Haven | Nostr relay server |
| **Remote Access** | GNOME Remote Desktop | RDP access with auto-generated TLS and credentials |

---

### Security

- **SSH hardened** — password authentication disabled by default
- **Fail2ban** — active on all exposed services
- **Agenix** — encrypted secrets management integrated into the flake
- **Tor** — optional integration available
- **Firewall** — ports managed per-module; only enabled services are exposed

### Reliability

- **Automated backups** via rsnapshot
- **Scheduled maintenance** via systemd timers
- **Database initialization** handled declaratively
- **Reproducible builds** — the entire system is defined in code and can be rebuilt or migrated to new hardware at any time

---

## Installation

### Full Guide

👉 [DIY Install Sovran_SystemsOS](https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/src/branch/main/DIY%20Install%20Sovran_SystemsOS.md)

---

## Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32+ GB |
| Storage | 512 GB SSD + 4 TB SSD | 2GB SSD + 4+ TB SSD (Bitcoin node requires significant disk) |
| Network | Stable broadband | Static IP or DDNS for public-facing services |

---

## Contributing

Contributions are welcome. If you want to add a module, fix a bug, or improve documentation:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request with a clear description of the change

Please keep modules self-contained and gated behind a feature flag.

---

## Community

| Channel | Link |
|---|---|
| General Chat | [#sovran-systems:anarchyislove.xyz](https://matrix.to/#/#sovran-systems:anarchyislove.xyz) |
| DIY Support | [#DIY_Sovran_SystemsOS:anarchyislove.xyz](https://matrix.to/#/#DIY_Sovran_SystemsOS:anarchyislove.xyz) |

---

## License

See [LICENSE](LICENSE) for details.

---

## Project Philosophy

Sovran_SystemsOS exists to provide a complete, self-hosted infrastructure stack that eliminates dependency on third-party platforms. It is opinionated by design — services are pre-integrated so you spend time using your system, not assembling it.

This is not a toolkit. It is a working system.

You retain full visibility into every module, every service definition, and every configuration choice. Nothing is hidden. Everything is reproducible.

---

**Own your stack. Run your world.**

