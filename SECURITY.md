# Security Policy (SECURITY.md)

This document outlines the security policy, vulnerability disclosure process, threat model, and security best practices for **Sovran_SystemsOS**.

---

## 1. Supported Versions

We actively monitor and patch security vulnerabilities in Sovran_SystemsOS. Because the operating system is built on [NixOS](https://nixos.org), stable releases receive security updates backported from upstream Nixpkgs as well as our custom software updates.

| Version | Supported | Notes |
|:---|:---:|:---|
| **1.0.x** (Stable) |  Yes | Active stable release line. Patches are backported regularly. |
| **staging-dev** |  Yes | Development line; updated frequently but may contain untested code. |
| **Legacy (< 1.0.0)** |  No | Please upgrade to the latest stable release to ensure you have active security updates. |

---

## 2. Reporting a Vulnerability

We take the security of self-custody systems, private clouds, and communications servers extremely seriously. If you discover a vulnerability, **please do not open a public issue, forum thread, or submit a public pull request.** 

Instead, report vulnerabilities privately through one of the following secure channels:

1. **Email:** Send an encrypted or plain-text email to [support@sovransystems.com](mailto:support@sovransystems.com).
   - If sending sensitive information, please contact us first to establish a secure PGP-encrypted communication channel.
2. **GitHub Private Vulnerability Reporting:** If you are viewing this on GitHub, you can report vulnerabilities privately via the **Security** tab of this repository under **Vulnerability reporting**.

### What to Include in a Report:
To help us triage and resolve the issue quickly, please include:
- A clear description of the vulnerability and its potential impact.
- Step-by-step instructions to reproduce the issue (including any scripts or configuration snippets).
- The version of Sovran_SystemsOS you tested (found in the Hub header or `/etc/nixos/VERSION`).
- Any potential remediation steps or suggestions you may have.

### Our Response and Disclosure Process:
1. **Acknowledgment:** We will acknowledge receipt of your report within **24–48 hours** and provide a tracking reference.
2. **Triage:** We will investigate and verify the vulnerability privately. We may reach out to you for clarifying details.
3. **Remediation:** If verified, we will develop a patch on a private security branch.
4. **Release:** We will coordinate a release date with you and publish the patch to Gitea `stable` and GitHub `main`.
5. **Advisory:** A public security advisory will be published, giving full credit to you for the discovery (unless you request anonymity).

We ask that you practice **coordinated vulnerability disclosure**, giving us reasonable time to patch the vulnerability before disclosing it publicly to protect other operators' funds and data.

---

## 3. The Sovran_SystemsOS Security Architecture

Understanding our underlying threat model and architectural decisions will help you evaluate the system's security.

### A. Local-First Threat Model
- **No Cloud Dependency:** Your data, keys, and credentials live entirely on your physical hardware.
- **Local network Hub Access:** The Sovran Hub is served directly on your local network (`sovransystemsos.local`). It is protected by authentication and **never** automatically exposed to the public internet.
- **Localhost Auto-Login:** Auto-login to the Hub is restricted strictly to local connections from `127.0.0.1` or `::1` (e.g., when accessing it directly from the local GNOME desktop). LAN and WAN clients must authenticate via password.

### B. Declarative & Reproducible NixOS Foundation
- **No Supply Chain Drift:** Dependencies, packages, and system components are strictly pinned using Nix flakes (`flake.lock`).
- **Reproducible Integrity Checks:** Operators can verify system integrity at any time via the Hub (`/api/security/verify-integrity`), which runs `nix store verify --all` to check binary consistency and rebuilds the system state from local files to guarantee it matches the expected configuration.
- **Default-Hardened Base:** Firewalls are enabled by default (`networking.firewall.enable = true`), public SSH and remote desktop are disabled by default, and legacy kernel modules like `rxrpc` are blacklisted to reduce the kernel's attack surface.

### C. Restricted Tech Support ("Zero-Trust Support")
To prevent support staff or malicious actors from accessing your private wallets, the operating system employs a unique **"Zero-Trust Support"** architecture:
- **Restricted System Account:** Support sessions use a restricted, non-root account (`sovran-support`) with heavily scoped shell access and limited `sudo` privileges (restricted strictly to viewing logs, editing configuration, and rebuilding or restarting services).
- **POSIX ACL Wallet Lockout:** Enabling support immediately triggers POSIX ACLs (`setfacl -m u:sovran-support:---`) to block the support user from reading, writing, or traversing sensitive directories (such as `/etc/nix-bitcoin-secrets`, `/var/lib/bitcoind`, `/var/lib/lnd`, and `/home`).
- **User-Controlled Timed Unlock:** Support staff can *only* access wallet files if the operator explicitly grants a time-limited unlock from the Hub interface. This unlock automatically expires, re-locking the directories.
- **Tamper-Evident Auditing:** All support actions (enabling, disabling, wallet unlocking, or locking) are logged in a tamper-evident audit trail (`/var/log/sovran-support-audit.log`) readable directly by the operator.

### D. Native Cryptographic Isolation
- **Tor Network Integration:** Upstream Bitcoin services (Knots/Core, Electrs, LND) utilize native Tor integration, preventing your home IP address from leaking to the public network or third-party node providers.
- **Isolated Lightning Wallets:** Nostr Wallet Connect (NWC) uses isolated, sandboxed Lightning wallets with specific spending limits and access presets (e.g., receive-only), keeping your main node funds completely isolated from individual apps.

---

## 4. Security Best Practices for Operators (Users)

No software can provide absolute security. You are the ultimate sovereign of your machine. Follow these best practices to keep your system and assets secure:

### 🔑 1. Split Wallet Entropy
When setting up a Bitcoin wallet, **generate your two entropy sources on separate, unconnected hardware**:
- **Seed Phrase:** Generated by Sparrow Wallet on your Sovran_SystemsOS machine.
- **BIP-39 Passphrase (128-bit):** Generated on a separate device (e.g., a GrapheneOS phone using a trusted password generator or offline Diceware dice).
- *Why?* If either device is compromised, your wallet remains secure because an attacker needs **both** independent sources of randomness to recover it.

### 💾 2. Implement a Robust Backup Strategy
- **Off-Machine Backups:** Never store your only wallet backups, seed phrases, or descriptor backups on the same computer as your running wallet.
- **Descriptor & Channel Backups:** If using Lightning (LND), regularly back up your Static Channel Backups (SCB) and store them off-site. A node hardware failure can permanently lock up channel funds without a fresh SCB.
- **Ext4 Backups:** If using the Hub's Manual Backup utility, ensure you are backing up to a dedicated **ext4-formatted** external drive. This preserves Linux-native security metadata, permissions, and POSIX ACLs.

### 🛡️ 3. Maintain Network and Access Hygiene
- **Public SSH Off:** Keep SSH remote access disabled in the Hub unless you actively need it. If enabled, Fail2Ban is active, but you should still enforce a strong system password.
- **Strong Diceware Passwords:** Ensure the system `free` and `root` users have strong passphrases. Avoid re-using passwords across services.
- **Guest Networks:** Do not access the Sovran Hub over public or guest Wi-Fi networks. These networks often lack isolation, exposing local network traffic to other devices.
- **Disable RDP When Done:** Turn off Remote Desktop (RDP) once your administrative session is finished.

### 🧑‍💻 4. Hardening Support Sessions
If you require technical support from Sovran Systems:
- **Enable SSH and Support on-demand:** Only enable SSH Remote Access and Support sessions when actively working with a technician, and **disable** them immediately when the session is over.
- **Confirm Removal:** The Hub's support page includes a "Verify Removal" feature. Always use it to ensure public keys have been fully stripped from the system.
- **Restrict Wallet Access:** Only unlock your wallet directories if absolutely necessary for the support session, and choose the shortest possible duration. Re-lock manually as soon as the troubleshooting steps are complete.
- **Review Audit Logs:** Periodically inspect the support audit log via the Hub interface to review exactly when support sessions were toggled or unlocked.

---

Thank you for helping us maintain a highly secure, private, and sovereign computing operating system!
