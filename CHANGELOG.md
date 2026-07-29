# Changelog

All notable changes to Sovran_SystemsOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.4] - 2026-07-29

### Added
- **Lightning Wallet Connections (NWC)** — Hub-managed Nostr Wallet Connect powered by Alby Hub + LND:
  - Create, view, and delete wallet connections directly from the Sovran Hub with a tabbed modal UI
  - Downloadable/printable LNURL QR codes for connecting external wallets
  - Channel liquidity guide and onboarding guidance for new LND nodes
  - Unique-hostname enforcement with conflict validation and UI guidance
  - Official NWC branding and logo
- **Version visibility across the Hub**:
  - Sovran_SystemsOS version badge displayed under the Hub title
  - Version numbers shown on all Hub service tiles and next to service modal titles
  - Deployed PHP app versions surfaced in service titles
  - Build-time version reference file (`VERSION`) so version lookups are instantaneous and consistent
- **Automated stable release workflow** (`scripts/release-stable.sh`) with versioned ISO naming from the `VERSION` file
- `CONTRIBUTING.md` and expanded project documentation

### Changed
- **Manual Backup overhauled**: replaced tar+DB+LND archive approach with a reliable ext4 + rsync workflow, including
  mount checks, path safety, atomic completion markers, stale-marker cleanup, and behavioral test coverage
- **Port-forwarding UX simplified**: removed onboarding Step 4 and the misleading local "ready" status;
  Njal.la DDNS now runs automatically when the feature is enabled
- README restructured for clarity, links, and accuracy; added router/ISP port-forwarding requirements
  for Server + Desktop mode; acknowledged LiveKit and Alby Hub
- Updated nixpkgs and Bitcoin clients
- Repository cleanup: removed unused `.github`, `.tests`, `nix/`, and `docs/ai` directories

### Fixed
- NWC wallet certificate path wiring (now uses the nix-bitcoin LND cert path)
- Deterministic LND/Alby Hub port collision
- Alby Hub executable resolution and v1.23.0 patches regenerated against exact upstream source
- Manual Backup exit-code failures (bash/gawk in service PATH, tar tolerance, flock, browser-cache exclusions)
- rsync destination-directory failures in backups (auto `mkdir -p`, mount check, 19 behavioral tests)
- `sovran-hosts-update` converted to `writeShellApplication` with explicit runtime inputs
- Incorrect `lib.mkIf` usage in the NWC wallets module
- Duplicate systemd LND strings
- `git fetch` tag-clobber errors against Gitea (now uses `--force`)

### Security
- Hardened Lightning Wallet Connections (NWC): restricted `ReadOnlyPaths` for the unlock password,
  fixed an Authorization-header bug, eliminated stack-trace exposure flagged by CodeQL,
  and tightened credential access and amount validation

[1.0.4]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.4


## [1.0.3] - 2026-07-29

### Added
- Incremental stable updates

## [1.0.2] - 2026-07-29

### Added
- Incremental stable updates

## [1.0.1] - 2026-07-29

### Added
- Incremental stable updates

## [1.0.0] - 2026-07-29

### Added
- Initial stable release of Sovran_SystemsOS
- Full Bitcoin self-custody desktop environment
- Integrated Sparrow Wallet, Bisq, and Bisq 2
- Comprehensive Sovran Hub for service management
- NixOS-based operating system with privacy and sovereignty focus
- Support for Bitcoin Knots + BIP110, Electrs, LND, Ride The Lightning, BTCPay Server, and more
- Server + Desktop hybrid mode with Matrix, Nextcloud, VaultWarden, and other self-hosted services
- Automated installer with graphical GNOME desktop
- Tor integration and onion services for all major components
- Remote desktop (GNOME Remote Desktop) support
- Role-based system configuration (desktop, server, server+desktop)
- Detailed service credential management in the Sovran Hub

### Changed
- Moved from development/main branch to dedicated `stable` branch for production releases

### Security
- All services run with least-privilege principles where possible
- Secrets stored in `/var/lib/secrets/`
- Strong emphasis on user-controlled keys and self-sovereignty

---

## [Unreleased]

### Added
- (Nothing yet)

[1.0.3]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.3
[1.0.2]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.2
[1.0.1]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.1
[1.0.0]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.0
