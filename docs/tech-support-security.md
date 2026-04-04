# Tech Support: Security Design, User Flow, and Incident Response

## Overview

The Sovran Hub includes a **Tech Support** feature that lets Sovran Systems
staff remotely diagnose and fix issues on a user's machine via SSH — without
ever having access to private keys or wallet funds.

Wallet protection is the default. The user must make an active, time-limited
choice to grant support staff access to wallet files, and can revoke that
access at any time.

---

## Implementation Details

### Restricted User Instead of Root

When a user enables support access the Hub:

1. Ensures the `sovran-support` system user exists (declared declaratively in
   `modules/core/tech-support.nix`; the Hub also provisions it on demand as a
   fallback on non-NixOS systems).
2. Writes the Sovran Systems public SSH key **only** to
   `/var/lib/sovran-support/.ssh/authorized_keys`, not to root's
   `authorized_keys`.
3. Applies POSIX ACLs (`setfacl -R -m u:sovran-support:---`) to every wallet
   directory that exists on disk, denying all access by the support user.
4. Records a timestamped `SUPPORT_ENABLED` event in the audit log at
   `/var/log/sovran-support-audit.log`.

When the session ends (or if the Hub cannot create the restricted user), the
key is removed and all ACLs are revoked immediately.

### Protected Wallet Paths

The following directories are locked by default when a support session starts:

| Path | Contents |
|------|----------|
| `/var/lib/lnd` | LND wallet and channel database |
| `/root/.lnd` | LND wallet (alternate location) |
| `/var/lib/sparrow` | Sparrow wallet data |
| `/root/.sparrow` | Sparrow wallet (alternate location) |
| `/root/.bisq` | Bisq wallet and keys |
| `/etc/nix-bitcoin-secrets` | nix-bitcoin generated secrets |
| `/var/lib/bitcoind` | Bitcoin Core chainstate and wallet |

Paths are only locked if they exist on disk at the time the session starts.

### POSIX ACL Mechanics

POSIX ACLs on Linux handle access checks in this order:

1. If the process UID matches the file owner UID → use owner permissions
2. **If there is a matching named-user ACL entry → use that entry's
   permissions** (clamped by the mask entry)
3. If any group matches → use group permissions
4. Otherwise → use "other" permissions

Setting `u:sovran-support:---` creates a named-user ACL entry with no
permissions. Because the named-user entry is checked before the group/other
entries, the support user cannot access those directories regardless of the
"other" permission bits.

`setfacl` and `getfacl` are provided by the `acl` package, which is added to
`environment.systemPackages` by `modules/core/tech-support.nix`.

### Fallback to Root (When Restricted User Cannot Be Created)

If the `sovran-support` user does not exist and cannot be created (e.g.,
`users.mutableUsers = false` and the declarative module has not been deployed
yet), the Hub falls back to adding the support key to root's
`authorized_keys`. The modal prominently warns the user when this has happened
so they can decide whether to end the session.

### Audit Log

Every session event is appended to `/var/log/sovran-support-audit.log`:

```
[2025-01-15 14:32:01 UTC] SUPPORT_ENABLED: restricted_user=True acl_applied=True protected_paths=4
[2025-01-15 14:45:00 UTC] WALLET_UNLOCKED: duration=3600s expires=2025-01-15 15:45:00 UTC
[2025-01-15 15:45:00 UTC] WALLET_RELOCKED: auto-expired
[2025-01-15 16:01:22 UTC] SUPPORT_DISABLED
```

The last 100 lines of this log are accessible from the Hub UI while a session
is active (or after it ends, until the page is refreshed).

---

## Security Tradeoffs

### What This Protects Against

- **Accidental wallet exposure** — support staff cannot read wallet files
  during a normal session; they must ask the user to explicitly grant access.
- **Credential theft** — private keys in the wallet directories are not
  visible to the `sovran-support` user by default.
- **Scope creep** — the restricted user account limits the blast radius of an
  SSH session compared to direct root access.

### Known Limitations

| Limitation | Mitigation |
|------------|------------|
| Support user still has system-wide bash access | Restrict with `ForceCommand` or AppArmor in the NixOS config if a narrower scope is required |
| ACLs apply only to directories that exist at session start | If new wallet directories are created during a session, they are not auto-protected. Re-lock and re-enable support to pick up new paths |
| Root fallback grants full access | The Hub UI warns the user prominently; users should end the session if they are uncomfortable |
| `setfacl` / ACL filesystem support required | The `acl` package is declared in `tech-support.nix`; most Linux filesystems (ext4, btrfs, xfs) support ACLs by default |
| Wallet access grant is time-limited but lazy-expired | Expiry is checked on the next `/api/support/status` poll (every 10 seconds in the UI); there is a small window after expiry |

### Defense-in-Depth Recommendations

For environments that require stronger isolation, consider layering one or
more additional controls:

- **`ForceCommand`** in `sshd_config` (or `~/.ssh/authorized_keys` command
  prefix) to restrict the support user to a specific diagnostic script.
- **`ChrootDirectory`** in the `sshd_config` `Match User sovran-support` block
  to confine the session to a prepared directory tree.
- **AppArmor or SELinux** profiles that deny the support process read access
  to wallet paths at the kernel level.
- **Namespace/bind-mount overlays** (e.g., via a wrapper systemd unit) to
  present a sanitized filesystem view.

---

## User Flow

```
User opens Hub  →  Clicks "Tech Support" in sidebar
        │
        ▼
Modal: "Need help from Sovran Systems?"
        • Explains what will happen
        • Shows Wallet Protection notice
        • User clicks "Enable Support Access"
        │
        ▼
Hub:    1. Creates / verifies sovran-support user
        2. Writes SSH key to that user's authorized_keys
        3. Applies POSIX ACL deny on all existing wallet paths
        4. Saves session metadata + writes SUPPORT_ENABLED to audit log
        │
        ▼
Modal: "Support Access is Active"
        • Live session duration timer
        • Wallet Files: Protected panel
            – Optional: "Grant Wallet Access" (time-limited, user-chosen)
        • "End Support Session" button
        • "View Audit Log" button
        │
  (User grants wallet access)
        │
        ▼
Hub:    • Removes ACL deny entries
        • Records WALLET_UNLOCKED event with expiry time
        • Starts countdown timer in UI
        │
  (Timer expires or user clicks "Re-lock Wallet Now")
        │
        ▼
Hub:    • Re-applies ACL deny entries
        • Removes WALLET_UNLOCK_FILE
        • Records WALLET_RELOCKED event
        │
  (User clicks "End Support Session")
        │
        ▼
Hub:    1. Removes SSH key from sovran-support authorized_keys
        2. Removes SSH key from root authorized_keys (legacy cleanup)
        3. Revokes any wallet unlock, re-applies ACL deny
        4. Verifies key is gone
        5. Records SUPPORT_DISABLED event
        │
        ▼
Modal: "Support Session Ended — SSH key removed"
        • Shows verified removal status
```

---

## Incident Response

### Scenario 1 — You accidentally granted wallet access and are unsure what was copied

**Immediate steps:**

1. Click **"Re-lock Wallet Now"** in the Hub modal, or click
   **"End Support Session"** to simultaneously revoke SSH access and wallet
   access.
2. Open the **Audit Log** from the Hub modal and note the timestamps of
   `WALLET_UNLOCKED` and `WALLET_RELOCKED` events.
3. Check `/var/log/auth.log` (or `journalctl -u sshd`) for SSH login events
   by `sovran-support` during the unlocked window.

**Assessment:**

- If no SSH login occurred during the wallet-unlocked window, your keys are
  safe.
- If an SSH login did occur, treat private keys as potentially compromised.

**Recovery if keys may be compromised:**

| Wallet | Recovery action |
|--------|----------------|
| LND | Move all funds out using `lncli sendcoins` to a freshly generated on-chain address; close channels; recreate wallet |
| Sparrow | Sweep funds to a new wallet generated on an air-gapped device |
| Bisq | Withdraw all BSQ and BTC to external wallets; delete the Bisq data directory and recreate |
| nix-bitcoin secrets | Rotate all secrets with `nix-bitcoin-secrets generate` and redeploy |

**Report the incident:**

Contact Sovran Systems immediately at support@sovransystems.com with:
- The audit log output (`/var/log/sovran-support-audit.log`)
- The SSH auth log for the affected time window
- A description of what you were troubleshooting

---

### Scenario 2 — Support session cannot be ended (button fails or server is unresponsive)

**Manual key removal (run as root on the device):**

```bash
# Remove from support user's authorized_keys
rm -f /var/lib/sovran-support/.ssh/authorized_keys

# Remove from root's authorized_keys (fallback / legacy)
sed -i '/sovransystemsos-support/d' /root/.ssh/authorized_keys

# Remove wallet unlock state
rm -f /var/lib/secrets/support-wallet-unlock

# Re-apply wallet ACL protections
setfacl -R -m u:sovran-support:--- /var/lib/lnd /root/.lnd \
  /var/lib/sparrow /root/.sparrow /root/.bisq \
  /etc/nix-bitcoin-secrets /var/lib/bitcoind 2>/dev/null || true

# Restart sshd to drop any active connections
systemctl restart sshd
```

---

### Scenario 3 — You see an unexpected SUPPORT_ENABLED in the audit log

This should never happen without physical or remote access to the Hub web
interface. If you see an unexpected entry:

1. Immediately run the manual key removal commands above.
2. Change the Sovran Hub web interface password.
3. Check `/var/log/nginx/access.log` (or Caddy access logs) for unexpected
   requests to `/api/support/enable`.
4. Consider rebooting the device to clear any in-memory state.
5. Report the incident to Sovran Systems.

---

*This document is part of the Sovran_SystemsOS repository. For the
authoritative and up-to-date version, see the repository.*
