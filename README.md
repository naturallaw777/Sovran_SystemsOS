<p align="center">
  <img src="https://github.com/user-attachments/assets/sovran-systems-logo.png" alt="Sovran Systems" width="300"/>
</p>

<h1 align="center">Sovran_SystemsOS</h1>

<p align="center">
  <strong>A Fully Sovereign, Declarative NixOS Operating System</strong><br/>
  Take complete ownership of your digital infrastructure.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/OS-NixOS-5277C3?style=flat-square&logo=nixos&logoColor=white" alt="NixOS"/>
  <img src="https://img.shields.io/badge/Bitcoin-Ecosystem-F7931A?style=flat-square&logo=bitcoin&logoColor=white" alt="Bitcoin"/>
  <img src="https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square" alt="License"/>
  <img src="https://img.shields.io/badge/Reproducible-100%25-green?style=flat-square" alt="Reproducible"/>
</p>

---

## Overview

Sovran_SystemsOS is a purpose-built, fully declarative operating system constructed entirely on [NixOS](https://nixos.org). It delivers a complete sovereign computing platform — integrating a Bitcoin financial stack, encrypted communications, self-hosted cloud services, and a professional web presence — all managed through a single, reproducible configuration.

Every component of the system is defined in Nix. There are no imperative scripts, no hidden state, and no black boxes. What you declare is exactly what runs. The entire operating system can be rebuilt, replicated, or audited from source at any time.

<p align="center">
  <img src="[https://github.com/user-attachments/assets/sovran-hub-screenshot.png](https://github.com/user-attachments/assets/5e9babe8-ca59-465c-9dda-d2ee46d2d4c2)" alt="Sovran_SystemsOS Hub Dashboard" width="800"/>
</p>

---

## The Sovran_SystemsOS Hub

The **Sovran_SystemsOS Hub** is the central management dashboard for the entire operating system. Accessible through a local web interface, it provides a unified view of all running infrastructure, Bitcoin services, and application status in real time.

From the Hub, operators can:

- Monitor the health and status of every service at a glance
- Access system administration tools including password management, backups, and tech support
- Manage Bitcoin node infrastructure (Bitcoin Knots, Bitcoin Core, BIP-110)
- Oversee the full Bitcoin application stack (Electrs, LND, Ride The Lightning, BTCPayServer, Zeus Connect, Mempool)
- Update the system with a single action
- Perform manual backups to external storage
- Access remote desktop capabilities

The Hub eliminates the need to manage services individually through disparate interfaces. It is the operational command center for the entire Sovran_SystemsOS deployment.

---

## Three Deployment Roles

Sovran_SystemsOS is architected around three distinct deployment roles, each tailored to a specific use case. A role is selected during installation and can be changed at any time by editing a single configuration file (`custom.nix`).

### Server + Desktop

The complete deployment. This role activates every server service alongside a full GNOME desktop environment, delivering a workstation that simultaneously operates as a sovereign infrastructure node.

**Includes:** Matrix Synapse homeserver, Bitcoin ecosystem (bitcoind, Electrs, LND, RTL, BTCPayServer), Vaultwarden password manager, WordPress, Nextcloud file hosting, Caddy reverse proxy, Tor, and the full desktop environment.

### Desktop Only

A clean, sovereign desktop environment without server services. Ideal for daily computing, secure communications, and Bitcoin wallet management without running full node infrastructure.

**Includes:** GNOME desktop, Bitcoin desktop applications (Sparrow, Bisq, Bisq2, Bitcoin Core GUI), Tor, and all productivity tools.

### Node (Bitcoin Only)

A dedicated Bitcoin infrastructure node. This role strips away desktop and web services to focus entirely on running and serving the Bitcoin network.

**Includes:** Bitcoin Knots with BIP-110, Electrs, LND, Ride The Lightning, BTCPayServer, Mempool block explorer, and all supporting Bitcoin infrastructure.

---

## Key Benefits

### Complete Digital Sovereignty

Every service runs on hardware you own. Your Bitcoin keys, your communications, your files, your passwords, and your website all operate under your exclusive control. There is no reliance on third-party cloud providers, no data harvested, and no external points of failure.

### Pure Declarative Configuration

The entire operating system — from kernel parameters to application configurations — is defined declaratively in Nix. This guarantees:

- **Reproducibility:** Any deployment can be identically recreated from the configuration files alone.
- **Auditability:** The complete system state is transparent and version-controlled.
- **Rollback:** Every system generation is preserved; reverting to a previous state is a single command.
- **Atomic Upgrades:** System rebuilds either succeed completely or fail without side effects.

### Modular Service Architecture

Services and features are organized into independently toggleable modules. Operators enable or disable capabilities through simple boolean flags in `custom.nix`:

| Category | Service | Default |
|----------|---------|---------|
| **Services** | Matrix Synapse | ON |
| **Services** | Bitcoin Ecosystem | ON |
| **Services** | Vaultwarden | ON |
| **Services** | WordPress | ON |
| **Services** | Nextcloud | ON |
| **Features** | Haven (NOSTR Relay) | OFF |
| **Features** | BIP-110 | OFF |
| **Features** | Mempool Explorer | OFF |
| **Features** | Element Video Calling | OFF |
| **Features** | Remote Desktop (RDP) | OFF |
| **Features** | Bitcoin Core GUI | OFF |

---

## Security Architecture

Sovran_SystemsOS is engineered with security as a foundational principle, not an afterthought.

- **Declarative Firewall:** All network access is explicitly defined. Only ports required by enabled services are opened; everything else is denied by default.
- **Fail2Ban Integration:** Automated intrusion prevention monitors and blocks brute-force attacks across all exposed services.
- **SSH Hardened:** Password authentication and keyboard-interactive authentication are disabled. Access is restricted to public key authentication only.
- **Tor Built-In:** The Tor network is enabled system-wide, providing anonymized connectivity and the ability to operate hidden services for any exposed application.
- **Automated Backups:** rsnapshot performs hourly and daily snapshots of all critical data — including home directories, system state, and Bitcoin secrets — to external storage.
- **Vaultwarden (Self-Hosted Bitwarden):** All credentials are managed through a locally hosted, encrypted password vault with no external dependencies.
- **NixOS Immutability:** The declarative model ensures that the running system always matches the defined configuration. Unauthorized modifications do not persist across rebuilds.
- **Nix Flake Pinning:** All dependencies — including nixpkgs, nix-bitcoin, and third-party modules — are pinned to exact revisions via `flake.lock`, eliminating supply-chain ambiguity.
- **Credential Isolation:** Bitcoin secrets and service credentials are stored in dedicated, permission-restricted directories and automatically generated during provisioning.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Operating System** | NixOS (Unstable Channel) |
| **Desktop Environment** | GNOME (Wayland) |
| **Reverse Proxy** | Caddy |
| **Bitcoin Node** | Bitcoin Knots / Bitcoin Core |
| **Lightning Network** | LND |
| **Lightning Management** | Ride The Lightning |
| **Payment Processing** | BTCPayServer |
| **Block Explorer** | Mempool |
| **Electrum Server** | Electrs |
| **Communications** | Matrix Synapse + Element |
| **Video Calling** | LiveKit (Element Calling) |
| **File Hosting** | Nextcloud |
| **Website** | WordPress |
| **Password Management** | Vaultwarden |
| **NOSTR Relay** | Haven |
| **DNS Management** | Njalla Dynamic DNS |
| **Network Privacy** | Tor |
| **Intrusion Prevention** | Fail2Ban |
| **Backup** | rsnapshot |
| **Package Management** | Nix Flakes |

---

## Repository Structure

```
staging_alpha/
├── flake.nix                  # Flake entry point and dependency declarations
├── flake.lock                 # Pinned dependency revisions
├── configuration.nix          # Core system configuration
├── custom.template.nix        # User-facing customization template
├── onboarding.html            # First-run onboarding interface
├── modules/
│   ├── modules.nix            # Module import manifest
│   ├── core/
│   │   ├── roles.nix          # Role and option declarations
│   │   ├── role-logic.nix     # Role-conditional service activation
│   │   ├── caddy.nix          # Reverse proxy configuration
│   │   ├── sovran-hub.nix     # Hub dashboard
│   │   └── ...                # Additional core modules
│   ├── synapse.nix            # Matrix Synapse homeserver
│   ├── bitcoinecosystem.nix   # Bitcoin infrastructure module
│   ├── nextcloud.nix          # Nextcloud file hosting
│   ├── wordpress.nix          # WordPress configuration
│   ├── vaultwarden.nix        # Password manager
│   ├── haven.nix              # NOSTR relay and Blossom
│   ├── mempool.nix            # Mempool block explorer
│   ├── element-calling.nix    # LiveKit video calling
│   └── ...                    # Additional service modules
├── iso/
│   ├── installer.py           # Automated installation wizard
│   ├── desktop.nix            # Desktop ISO configuration
│   ├── server.nix             # Server ISO configuration
│   └── ...                    # ISO build assets
└── app/
    └── sovran_systemsos_web/  # Hub web application
```

---

## Getting Started

1. **Download** the Sovran_SystemsOS ISO image.
2. **Boot** from the installation media.
3. **Select your role** — Server + Desktop, Desktop Only, or Node — during the guided installation.
4. **Customize** your deployment by editing `/etc/nixos/custom.nix` to enable or disable services and features.
5. **Rebuild** with `nixos-rebuild switch` to apply changes.

---

## Acknowledgments

Sovran_SystemsOS is built on the work of exceptional open-source contributors and projects.

**[nix-bitcoin](https://github.com/fort-nix/nix-bitcoin)** — The Bitcoin infrastructure layer of Sovran_SystemsOS is made possible by the nix-bitcoin project. Their rigorous, security-focused NixOS modules for Bitcoin Core, LND, Electrs, BTCPayServer, and related services provide the foundation upon which the entire Bitcoin ecosystem in this operating system is constructed. The nix-bitcoin team's commitment to reproducible, auditable Bitcoin infrastructure is directly aligned with the mission of Sovran_SystemsOS, and their work is deeply appreciated.

**[Emmanuel Rosa](https://github.com/emmanuelrosa)** — The `btc-clients-nix` and `bitcoin-knots-bip-110-nix` packages, maintained by Emmanuel Rosa, bring essential Bitcoin desktop applications (Sparrow, Bisq, Bisq2) and the BIP-110 Bitcoin Knots implementation to NixOS. These ports fill a critical gap in the NixOS Bitcoin ecosystem and are integral to delivering a complete sovereign computing experience. His dedication to packaging and maintaining these tools for the Nix community is sincerely valued.

**[NixOS](https://nixos.org)** — The purely functional Linux distribution that makes all of this possible. Without the NixOS foundation of declarative, reproducible system management, a project of this scope and reliability would not be feasible.

---

## License

Sovran_SystemsOS is released under the [GNU Affero General Public License v3.0](LICENSE).

---

<p align="center">
  <strong>Sovran Systems</strong><br/>
  <em>Your keys. Your node. Your cloud. Your sovereignty.</em>
</p>
