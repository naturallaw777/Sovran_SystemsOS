# Changelog

All notable changes to Sovran_SystemsOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed
- Fix Bitcoin Knots → Bitcoin Core switch hanging in the Hub UI
  - Sessions are now persisted to `/var/lib/secrets/hub-sessions.json` so the
    browser login survives the Hub service restart that `nixos-rebuild switch`
    performs during activation. Previously the in-memory session store was
    wiped by that restart, the `/api/rebuild/status` poll started returning
    401, and the rebuild modal spun forever showing "Applying changes…" while
    the switch result was never displayed.
  - Rebuild and update modals now bail out and reload the page after sustained
    polling failures instead of hanging indefinitely.
  - Rebuild/update scripts stream `nixos-rebuild` output into the live log
    (it was buffered until completion, making long rebuilds look frozen).

---

## [1.1.0] - 2026-08-11

### Added
- Speed up Hub service status loading
- Update Documentation
- Njalla.nix: fail on ImportError; fix redundant except clause
- Correctly escape DDNS placeholder in Nix string
- Security hardening: fix all 8 blocking findings for PR #419
- Security hardening: fix DDNS injection, Nix injection, reboot auth, support key, sudo rules
- Harden btcpay and nbxplorer config handling
- Add provenance headers and fix flake checks for PR409
- Restore upstream nix-bitcoin fetchNodeModules for mempool and RTL packages
- Refactor Nix build configuration for mempool
- Update npm dependencies and patch handling in default.nix
- Update npmDepsHash for backend and frontend packages
- Mempool: use postPatch to copy lock file for npmDeps fetcher
- Mempool: use preBuild cd instead of postUnpack so npmDeps fetcher finds lock files
- Mempool: fix npmDeps fetcher — postUnpack instead of sourceRoot, postPatch instead of patches
- Mempool: switch backend and frontend to buildNpmPackage with placeholder npmDepsHash
- Update npmDepsHash with correct hash value
- RTL: switch to buildNpmPackage with placeholder npmDepsHash
- Add bitcoind.rpc.users.btcpayserver for NBXplorer
- Restore original flake.nix with nixosModules.Sovran_SystemsOS export
- Add vendored RTL package and fix rtl.nix to use it
- Vendor mempool packages and wire mempool module to vendored pkgs
- Refactor onion service configuration for LND
- Add missing bitcoind-rpc-public-whitelist.nix
- Remove joinmarket-ob-watcher from onion-services defaults
- Tailor: make bitcoin modules truly Sovran-only (lnd-only) and delete stubs.nix
- Vendor: replace nix-bitcoin flake input with minimal vendored modules (nixpkgs-only)
- Remove duplicate 1.0.6 release notes from CHANGELOG

### Changed
- Clean mempool module comment typo
- Move vendor/nix-bitcoin to modules/bitcoin, remove overlays
- Nix flake update - drop nix-bitcoin

### Fixed
- Correct RTL and Mempool Hub versions
- Fix DDNS URL validation: replace ${IP} temporarily for validator, keep placeholder for storage
- Fix all 8 security hardening blockers for PR #423
- Fix Nix interpolation in DDNS runner
- Fix IP validation in DDNS and document journalctl sudo rule
- Report configured BTCPay Server version
- Fix Matrix SIGPIPE and RTL v0.15.8 config schema regressions
- Add NBXplorer cookie auth and WorkingDirectory for BTCPay service
- Fix BTCPay startup regression: add home dirs to service users
- Address btcpay hardening review feedback
- Register bitcoin-HMAC-btcpayserver as managed secret owned by bitcoind user
- Fix RTL: use fetchNodeModules instead of npm ci in buildPhase
- Fix PostgreSQL ensureUsers: use ensureDBOwnership instead of ensureClauses
- Fix lnd macaroons: replace invalid 'enable' with 'user'
- Fix postgresql ensurePermissions -> ensureClauses for nixpkgs unstable
- Fix btcpayserver.nix to use pkgs.stable overlay
- Fix btcpayserver syntax error and pin to nixpkgs-stable (2.4.2)
- Fix mempool package: remove fetchNodeModules dependency
- Fix typo in onion-addresses service check
- Fix formatting of extraGroups in btcpayserver.nix
- Add missing semicolon after extraGroups in btcpayserver.nix
- Remove services.clightning.enable assignment that fails on f13ff45
- Remove clightning and clightning-rest from stubs to avoid duplicate on f13ff45
- Add stubs for nixpkgs-unstable 2026-08 where services.clightning removed
- Keep ISO artifacts out of the repo and auto-update README on release
[1.1.0]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.1.0


## [1.0.6] - 2026-08-07

### Added
- Iso: fix replaceStrings length mismatch in cleanVersion
- Promote virtual machine trial option in README
- Improve installer VM compatibility
- Trim redundant dev-vs-stable Gitea explanations in README
- Add Arean.Ai to AI tools used for development
- Prefix OS version badge with 'v' (v1.0.5)
- Match OS version badge styling to service modal version badges
- Place OS version badge inline right after the Hub title
- Center OS version badge under the Hub title
- Strengthen entropy section: add DYOR emphasis and hardware wallet verification note
- Add 'About Bitcoin wallet entropy' section to README
- README: balance intro between Bitcoin sovereignty and sovereign computing

### Changed
- Removed temp patch file

### Fixed
- Resolve tag range detection and improve release diagnostics
- Add token scope diagnostics and un-silence gh release errors
- Harden error handling and sanitize exception details across security endpoints (CWE-209)
- Sanitize exception handling in verify-integrity and security-reset (CWE-209)
- Sanitize api_security_reset errors to prevent exception information exposure (CWE-209)
- Use canonical prefix containment check for CodeQL path-injection
- Pass sanitized abs_path to os.chown to resolve CodeQL path injection at 4338
- Add CodeQL-recognized path sanitization for domain_name
- Remove domain substring check for CodeQL incomplete-url
- Use sentinel for njalla header check (CodeQL incomplete-url-substring)
- Prevent reflected XSS in lnurl-qr print endpoint
- Hash root password instead of storing in clear text (CWE-312)
- Separate web auth hash from system password file
- Fix Matrix Hub admin API credentials
- Fix CWE-78: replace subprocess call with Synapse Admin API in create-user endpoint

### Documentation
- Add SECURITY.md detailing security policy and best practices
- Versioned CDN downloads + add CDN upload script
- Correct active development workflow
- Make repo references mirror-neutral for Gitea readers
- Clarify GitHub is the dev mirror of the Gitea stable repo
[1.0.6]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.6

## [1.0.5] - 2026-08-04

### Added
- LND Update to v0.21.1-beta
- Nixpkgs Update
- Nixpkgs Update
- Update LND REST Zeus Connect instructions and design to match NWC exactly
- UI: Align LND REST and NWC Zeus connection instructions styling
- Make Zeus LND REST instructions coherent with NWC Zeus connect guide
- Clarify Zeus NWC wallet setup
- Make Manual Backup match the system role (Desktop Only scope)
- Reload Caddy immediately when a domain (or ACME email) is saved
- Unify Njal.la + router port-forwarding guidance across onboarding and feature enable modals
- Enhance Lightning Wallet Connect modal with professional benefits grid and refined messaging

### Fixed
- Resolve 'vdev' version badge and align it under the Hub title
- Align release script with Gitea staging-dev and stable branch workflow
- Auto-detect git remotes and clean up temp files in release-stable.sh

### Documentation
- Write real v1.0.4 changelog and auto-generate release notes in release script
[1.0.5]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/v1.0.5


## [Unreleased]

### Fixed
- Report the version of the configured BTCPay Server package in the Hub instead of the different package version from unstable nixpkgs.
- Installer VM compatibility: legacy BIOS VM boots now install with GRUB, UEFI VM installs avoid depending on NVRAM boot-entry writes, VM users get clearer disk/resource guidance, and the internet check falls back to HTTPS when ICMP is blocked.
- **Manual Backup now matches the system role**: on the Desktop Only role the Hub's
  "What gets backed up" list no longer shows Node / Server + Desktop items
  (nix-bitcoin secrets, `/var/lib` system service data, and the database/blockchain
  caveats), and the backup script skips those stages entirely — Desktop Only backups
  now mirror only the NixOS configuration (`/etc/nixos`) and home directory (`/home`).
  The free-space estimate, stage numbering, backup manifest, and completion message
  are all role-aware; Node and Server + Desktop backups are unchanged.

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
