# Sovran Hub — Manual Backup

The manual backup service copies critical system data from your Sovran Pro to an external USB drive, providing a third copy of your data (your Sovran Pro already maintains an automatic internal backup on its second drive).

Backups are written to:

```
<USB drive>/Sovran_SystemsOS_Backup/<timestamp>/
```

where `<timestamp>` is formatted as `YYYYMMDD_HHMMSS`.

---

## Backup Stages

The script always attempts all four stages, but skips stages that are irrelevant to the system's configured role (see [Per-Role Breakdown](#per-role-breakdown) below).

| Stage | Directory | Contents |
|-------|-----------|----------|
| **1/4 — NixOS config** | `/etc/nixos/` | Full NixOS system configuration: `role-state.nix`, `custom.nix`, flake files, and any other config managed by the Hub |
| **2/4 — Secrets** | `/etc/nix-bitcoin-secrets`, `/var/lib/domains`, `/var/lib/secrets` | Bitcoin/LND secrets, domain configurations for all web services, and Hub state files |
| **3/4 — Home directory** | `/home/` | All user home directories (`.cache/` and Trash are excluded) |
| **4/4 — LND wallet data** | `/var/lib/lnd/` | Lightning Network node wallet and channel data (log files excluded) |

---

## Per-Role Breakdown

The script detects the system role at runtime by reading `/var/lib/sovran-hub/config.json` (falling back to `/etc/nixos/role-state.nix`) and adjusts its behaviour accordingly.

### Server + Desktop (default)

All services are enabled: Bitcoin, Matrix Synapse, Vaultwarden, WordPress, Nextcloud.

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 1 — NixOS config | ✅ Backed up | Full server configuration |
| Stage 2 — Secrets | ✅ Backed up | Bitcoin secrets, domain configs, and Hub state |
| Stage 3 — Home directory | ✅ Backed up | Desktop user data |
| Stage 4 — LND wallet | ✅ Backed up | Lightning wallet and channel data |

This produces the largest backup. All four stages generate meaningful data.

### Desktop Only

All server services are disabled (`bitcoin = false`, `synapse = false`, `vaultwarden = false`, `wordpress = false`, `nextcloud = false`). Only GNOME desktop is active.

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 1 — NixOS config | ✅ Backed up | Simpler config (no server services) |
| Stage 2 — Secrets | ⚠️ Partial | `/etc/nix-bitcoin-secrets` is **skipped** (not applicable for Desktop Only role). `/var/lib/domains` and `/var/lib/secrets` (Hub state) are still backed up if present |
| Stage 3 — Home directory | ✅ Backed up | **The most important data for this role** |
| Stage 4 — LND wallet | ⏭️ Skipped | Explicitly skipped — not applicable for Desktop Only role |

This produces the smallest and fastest backup. Stages 1 and 3 are the primary sources of meaningful data.

### Node (Bitcoin-only)

Only the Bitcoin ecosystem is active: `bitcoind`, `electrs`, `lnd`, `rtl`, `btcpay`, `mempool`, and `bip110`. All other server services are disabled.

| Stage | Status | Notes |
|-------|--------|-------|
| Stage 1 — NixOS config | ✅ Backed up | Node-specific configuration |
| Stage 2 — Secrets | ✅ Backed up | Bitcoin secrets and Hub state. `/var/lib/domains` may be minimal (BTCPay runs but is not exposed via Caddy) |
| Stage 3 — Home directory | ✅ Backed up | User data |
| Stage 4 — LND wallet | ✅ Backed up | **Critical** — Lightning wallet and channel data |

All four stages run, matching Server + Desktop behaviour. The `/var/lib/domains` directory may be sparsely populated since non-Bitcoin web services are not configured.

---

## Backup Manifest

After all stages complete, the script writes a `BACKUP_MANIFEST.txt` file inside the timestamped backup directory. This file records the date, hostname, detected role, target drive, and a directory listing of everything that was backed up.

---

## Running the Backup

The backup is triggered from the Sovran Hub web UI. You can also run it directly:

```bash
# Auto-detect the first external USB drive
sudo bash /path/to/sovran-hub-backup.sh

# Specify a target drive explicitly
sudo BACKUP_TARGET=/run/media/<user>/<drive> bash /path/to/sovran-hub-backup.sh
```

The script requires at least **10 GB** of free space on the target drive and will refuse to write to internal system drives.

Logs are written to `/var/log/sovran-hub-backup.log` and the current status (`RUNNING`, `SUCCESS`, or `FAILED`) is tracked in `/var/log/sovran-hub-backup.status`.
