# Security Policy

## Supported versions

| Release | Supported |
|---|:---:|
| Latest stable release | Yes |
| `main` / `staging-dev` | Development only |
| Older than `1.0.0` | No |

Install the newest stable point release to receive security fixes.

## Report a vulnerability

**Do not open a public issue or pull request.** Report privately through:

- [GitHub Private Vulnerability Reporting](https://github.com/naturallaw777/Sovran_SystemsOS/security/advisories/new)
- Email: [support@sovransystems.com](mailto:support@sovransystems.com)

Include the affected version, impact, reproduction steps, and a minimal proof of
concept. Never send wallet recovery words, private keys, or live credentials.

We aim to acknowledge reports within two business days. Please allow reasonable
time for a fix and coordinated disclosure.

## Security model

### Local-first operation

The Hub and core data run on operator-owned hardware. The Hub is intended for a
trusted local network and must not be port-forwarded to the internet. Public
services, DDNS, software updates, and optional third-party relays require
external networks and are outside a “fully offline” model.

The local Hub currently uses HTTP. Authentication does not encrypt local network
traffic, so use a trusted LAN and avoid public or guest Wi-Fi.

### Public services and your home IP address

Server + Desktop publishes services under your own domain. The Dynamic DNS
record at Njal.la then points at your home's public IP address, which anyone
can look up (domain privacy does not hide it), and ports 80 and 443 are open
to the whole internet. Public HTTPS certificates also list your service
hostnames in Certificate Transparency logs. Desktop publishes nothing. Node
publishes nothing unless *Put BTCPay Server Online* or *Lightning Wallet
Connections* is on. See
[Server + Desktop and your home IP address](README.md#server--desktop-and-your-home-ip-address)
for what this means and the alternatives.

Sovran_SystemsOS does not ask a STUN server, public DNS resolver, or “what is
my IP” service for your address. The DDNS update asks Njal.la to use the
address the request came from, and the address Njal.la reports back is the one
Element calling and the Hub use.

### Bitcoin stack

Bitcoin and Lightning modules are maintained in the standalone
[Sovran_Bitcoin](https://github.com/naturallaw777/Sovran_Bitcoin) repository
and consumed as a flake input. OS-specific customizations (Second_Drive paths,
operator user, Hub integration) are bridged by
`modules/sovran-bitcoin-integration.nix`. The `nix-bitcoin.*` option namespace
and `/etc/nix-bitcoin-secrets` path remain only for upgrade compatibility.

### Supply chain and integrity

`flake.lock` pins flake inputs, and fetched source archives use fixed hashes.
Builds still depend on pinned Nixpkgs, NixVim, btc-clients-nix, upstream source
archives, and any configured binary cache. Keeping the Bitcoin modules in this
repository reduces an external dependency; it does not remove supply-chain
risk.

The Hub integrity check verifies Nix store contents and compares the running
system with a build from local `/etc/nixos`. It does not authenticate the release
publisher or protect against an attacker who already controls root and can
change both the system and local configuration.

### Access and service isolation

- Firewall enabled by default
- Public SSH and remote desktop disabled by default
- Separate service users and systemd sandboxing where supported
- Administrative service ports bound to loopback where practical
- Tor enforced for supported Bitcoin traffic and onion services
- Public web services exposed only when enabled by the operator (this makes
  your home IP address public)

Tor reduces network exposure for configured Bitcoin services. It is not a
guarantee against every IP leak, application bug, or traffic-analysis attack.

### Restricted support access

Support uses a per-session SSH key on the non-root `sovran-support` account.
Sessions expire after 24 hours and have a small allowlist of `sudo` commands.
Wallet paths receive deny ACLs unless the operator explicitly removes them.
Disabling support removes the key and reapplies the ACLs.

Support events are written to `/var/log/sovran-support-audit.log`. This is a
local audit log, not a cryptographically tamper-evident record.

## Out of scope

Sovran_SystemsOS cannot protect against:

- Compromised root or administrator credentials
- Stolen recovery words, private keys, or backups
- Malicious or compromised hardware, firmware, or build infrastructure
- Services the operator deliberately exposes or weakens
- Physical access without appropriate disk and firmware protections

## Operator basics

- Verify downloads and stop if the checksum does not match.
- Apply stable security updates promptly.
- Use unique passwords and keep SSH/RDP off when not needed.
- Prefer a well-reviewed hardware signer for meaningful Bitcoin balances.
- Keep tested, offline backups in separate secure locations.
- Never share recovery words or private keys with support.
- Disable support access when the session ends and review the audit log.

No software can provide absolute security. Review your configuration and threat
model before storing important funds or data.
