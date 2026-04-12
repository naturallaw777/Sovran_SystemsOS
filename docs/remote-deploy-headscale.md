# Remote Deployment via Headscale (Self-Hosted Tailscale)

This guide covers the Sovran Systems remote deployment system built on [Headscale](https://headscale.net) — a self-hosted, open-source implementation of the Tailscale coordination server. Freshly booted ISOs automatically join a private WireGuard mesh VPN without any per-machine key pre-generation.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                        Internet                          │
└────────────┬─────────────────────┬──────────────────────┘
             │                     │
             ▼                     ▼
┌────────────────────┐   ┌─────────────────────────────────┐
│   Admin Workstation │   │         Sovran VPS              │
│                    │   │  ┌─────────────────────────────┐ │
│  tailscale up      │   │  │  Headscale (port 8080)      │ │
│  --login-server    │◄──┼─►│  Coordination server        │ │
│  hs.example.com   │   │  ├─────────────────────────────┤ │
│                    │   │  │  Provisioning API (9090)    │ │
└────────────────────┘   │  │  POST /register             │ │
                         │  │  GET  /machines             │ │
                         │  │  GET  /health               │ │
                         │  ├─────────────────────────────┤ │
                         │  │  Caddy (80/443)             │ │
                         │  │  hs.example.com → :8080     │ │
                         │  │  prov.example.com → :9090   │ │
                         │  └─────────────────────────────┘ │
                         └─────────────────────────────────┘
                                        ▲
                                        │  WireGuard mesh (Tailnet)
                                        ▼
                         ┌─────────────────────────────────┐
                         │     Deploy Target Machine       │
                         │                                 │
                         │  Boot live ISO →               │
                         │  sovran-auto-provision →       │
                         │  POST /register →              │
                         │  tailscale up --authkey=...    │
                         └─────────────────────────────────┘
```

**Components:**
- **`sovran-provisioner.nix`** — NixOS module deployed on a separate VPS; runs Headscale + provisioning API + Caddy.
- **Live ISO** (`iso/common.nix`) — Auto-registers with the provisioning server and joins the Tailnet on boot.
- **`remote-deploy.nix`** — Post-install NixOS module that uses Tailscale/Headscale for ongoing access.

---

## Part 1: VPS Setup — Deploy `sovran-provisioner.nix`

### Prerequisites

- A NixOS VPS (any provider) with a public IP
- Two DNS A records pointing to your VPS:
  - `hs.yourdomain.com` → VPS IP  (Headscale coordination server)
  - `prov.yourdomain.com` → VPS IP  (Provisioning API)
- Ports 80, 443 (TCP) and 3478 (UDP, STUN/DERP) open in your VPS firewall

### DNS Records

| Type | Name                  | Value      |
|------|-----------------------|------------|
| A    | `hs.yourdomain.com`   | `<VPS IP>` |
| A    | `prov.yourdomain.com` | `<VPS IP>` |

### NixOS Configuration

Add the following to your VPS's `/etc/nixos/configuration.nix`:

```nix
{ config, lib, pkgs, ... }:

{
  imports = [
    ./hardware-configuration.nix
    /path/to/sovran-provisioner.nix   # or fetch from the repo
  ];

  sovranProvisioner = {
    enable = true;
    domain        = "prov.yourdomain.com";
    headscaleDomain = "hs.yourdomain.com";

    # Optional: customise defaults
    headscaleUser = "sovran-deploy";   # namespace for deploy machines
    adminUser     = "admin";           # namespace for your workstation
    keyExpiry     = "1h";              # pre-auth keys expire after 1 hour
    rateLimitMax  = 10;                # max registrations per window
    rateLimitWindow = 60;              # window in seconds
  };

  # Required for Caddy ACME (Let's Encrypt)
  networking.hostName = "sovran-vps";
  system.stateVersion = "24.11";
}
```

### Deploy

```bash
nixos-rebuild switch
```

Caddy will automatically obtain TLS certificates via Let's Encrypt.

### Retrieve the Enrollment Token

```bash
cat /var/lib/sovran-provisioner/enroll-token
```

Keep this token secret — it is used to authenticate ISO registrations. The token is auto-generated on first boot and stored at this path. You never need to set it manually. Just `cat` it from the VPS and copy it to `iso/secrets/enroll-token` before building the ISO.

---

## Part 2: Admin Workstation Setup

Join your Tailnet as an admin so you can reach deployed machines:

### Install Tailscale

Follow the [Tailscale installation guide](https://tailscale.com/download) for your OS, or on NixOS:

```nix
services.tailscale.enable = true;
```

### Join the Tailnet

```bash
sudo tailscale up --login-server https://hs.yourdomain.com --accept-dns=false
```

> **Note:** The `--accept-dns=false` flag prevents Tailscale from taking over your system DNS resolver. This is important if you are behind a VPN (see [Troubleshooting](#troubleshooting) below).

Tailscale prints a URL. Open it and copy the node key (starts with `mkey:`).

### Approve the Node in Headscale

On the VPS, first find the numeric user ID for the `admin` user, then register the node:

```bash
# Look up the numeric ID for the admin user (Headscale 0.28.0 requires -u <id>)
headscale users list -o json

# Register the node using the numeric user ID
headscale nodes register -u <admin-user-id> --key mkey:xxxxxxxxxxxxxxxx
```

Your workstation is now on the Tailnet. You can list nodes:

```bash
headscale nodes list
```

---

## Part 3: Building the Deploy ISO

### Add Secrets (gitignored)

The secrets directory `iso/secrets/` is gitignored. Populate it before building:

```bash
# Copy the enrollment token from the VPS
ssh root@<VPS> cat /var/lib/sovran-provisioner/enroll-token > iso/secrets/enroll-token

# Set the provisioner URL
echo "https://prov.yourdomain.com" > iso/secrets/provisioner-url
```

These files are baked into the ISO at build time. If the files are absent the ISO still builds — the auto-provision service exits cleanly with "No enroll token found, skipping auto-provision", leaving DIY users unaffected.

### Build the ISO

```bash
nix build .#nixosConfigurations.sovran_systemsos-iso.config.system.build.isoImage
```

The resulting ISO is in `./result/iso/`.

---

## Part 4: Deployment Workflow

### Step-by-Step

1. **Hand the ISO to the remote person** — they burn it to a USB drive and boot.

2. **ISO boots and auto-registers** — `sovran-auto-provision.service` runs automatically:
   - Reads `enroll-token` and `provisioner-url` from `/etc/sovran/`
   - `POST https://prov.yourdomain.com/register` with hostname + MAC
   - Receives a Headscale pre-auth key
   - Runs `tailscale up --login-server=... --authkey=...`
   - The machine appears in `headscale nodes list` within ~30 seconds

3. **Approve the node (if not using auto-approve)** — on the VPS:
   ```bash
   headscale nodes list
   # Note the node key for the new machine
   ```

4. **SSH from your workstation** — once the machine is on the Tailnet:
   ```bash
   # Get the machine's Tailscale IP
   headscale nodes list | grep sovran-deploy-

   # SSH in
   ssh root@100.64.x.x    # password: sovran-remote (live ISO default)
   ```

5. **Run the headless installer**:

   The `--deploy-key` is your SSH public key that gets injected into `root`'s `authorized_keys` on the deployed machine. This grants full root access for initial setup. Generate it once on your workstation if you haven't already:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/sovran-deploy -C "sovran-deploy"
   ```
   After deployment is complete and you disable deploy mode, this key is removed.

   ```bash
   sudo sovran-install-headless.sh \
     --disk /dev/sda \
     --role server \
     --deploy-key "$(cat ~/.ssh/sovran-deploy.pub)" \
     --headscale-server "https://hs.yourdomain.com" \
     --headscale-key "$(headscale preauthkeys create -u $(headscale users list -o json | jq -r '.[] | select(.name=="sovran-deploy") | .id') -e 2h -o json | jq -r '.key')"
   ```

6. **Machine reboots into Sovran_SystemsOS** — `deploy-tailscale-connect.service` runs:
   - Reads `/var/lib/secrets/headscale-authkey`
   - Joins the Tailnet with a deterministic hostname (`sovran-<hostname>`)

7. **Post-install SSH and RDP**:
   ```bash
   # SSH over Tailnet
   ssh root@<tailscale-ip>

   # RDP over Tailnet (desktop role) — Sovran_SystemsOS uses GNOME Remote Desktop (native Wayland RDP)
   # Retrieve the auto-generated RDP password:
   ssh root@<tailscale-ip> cat /var/lib/gnome-remote-desktop/rdp-password
   # Then connect with any RDP client (Remmina, GNOME Connections, Microsoft Remote Desktop):
   #   Host: <tailscale-ip>:3389   User: sovran   Password: <from above>
   ```

8. **Disable deploy mode** — edit `/etc/nixos/custom.nix` on the target, set `enable = false`, then:
   ```bash
   sudo nixos-rebuild switch
   ```

---

## Part 5: Post-Install Access

### SSH

```bash
# Over Tailnet
ssh root@100.64.x.x
```

### RDP (desktop/server roles)

Sovran_SystemsOS uses **GNOME Remote Desktop** (native Wayland RDP — not xfreerdp). The RDP service auto-generates credentials on first boot.

**Username:** `sovran`
**Password:** auto-generated — retrieve it via SSH:
```bash
ssh root@<tailscale-ip> cat /var/lib/gnome-remote-desktop/rdp-password
```

Connect using any RDP client (Remmina, GNOME Connections, Microsoft Remote Desktop) to `<tailscale-ip>:3389`.

---

## Security Model

| Concern | Mitigation |
|---------|-----------|
| Enrollment token theft | Token only triggers key generation; it does not grant access to the machine itself |
| Rogue device joins Tailnet | Visible in `headscale nodes list`; removable instantly with `headscale nodes delete` |
| Pre-auth key reuse | Keys are ephemeral and expire in 1 hour (configurable via `keyExpiry`) |
| Rate limiting | Provisioning API limits to 10 registrations/minute by default (configurable) |
| SSH access | Requires ed25519 key injected at install time; password authentication disabled |
| Credential storage | Auth key written to `/var/lib/secrets/headscale-authkey` (mode 600) on the installed OS |

### Token Rotation

To rotate the enrollment token:

1. On the VPS:
   ```bash
   openssl rand -hex 32 > /var/lib/sovran-provisioner/enroll-token
   chmod 600 /var/lib/sovran-provisioner/enroll-token
   ```

2. Update `iso/secrets/enroll-token` and rebuild the ISO.

Old ISOs with the previous token will fail to register (receive 401).

---

## Monitoring

### List Active Tailnet Nodes

```bash
# On the VPS
headscale nodes list
```

### List Registered Machines (Provisioning API)

```bash
curl -s -H "Authorization: Bearer $(cat /var/lib/sovran-provisioner/enroll-token)" \
  https://prov.yourdomain.com/machines | jq .
```

### Health Check

```bash
curl https://prov.yourdomain.com/health
# {"status": "ok"}
```

### Provisioner Logs

```bash
journalctl -u sovran-provisioner -f
```

### Headscale Logs

```bash
journalctl -u headscale -f
```

---

## Cleanup

### Remove a Machine from the Tailnet

```bash
headscale nodes list
headscale nodes delete --identifier <id>
```

### Disable Deploy Mode on an Installed Machine

Edit `/etc/nixos/custom.nix`:

```nix
sovran_systemsOS.deploy.enable = false;
```

Then rebuild:

```bash
nixos-rebuild switch
```

This stops the Tailscale connect service.

### Revoke All Active Pre-Auth Keys

```bash
# List pre-auth keys (Headscale 0.28.0: no --user flag on list)
headscale preauthkeys list

# Expire a specific key — use numeric user ID (-u <id>)
# First find the user ID:
headscale users list -o json
# Then expire the key:
headscale preauthkeys expire -u <user-id> --key <key>
```

---

## Troubleshooting

### VPN Conflicts (Mullvad, WireGuard, etc.)

**Symptom:** `tailscale up` hangs or fails with `connection refused` on port 443, even though `curl https://hs.yourdomain.com/health` works fine.

**Cause:** VPNs like Mullvad route all traffic — including Tailscale's control-plane connections — through the VPN tunnel. Additionally, Tailscale's DNS handler (`--accept-dns=true` by default) hijacks DNS resolution and may prevent correct resolution of your Headscale server even when logged out.

**Solution:**
1. Disconnect your VPN temporarily and retry `tailscale up`.
2. If you need the VPN active, use split tunneling to exclude `tailscaled`:
   ```bash
   # Mullvad CLI
   mullvad split-tunnel add $(pidof tailscaled)
   ```
   Or in the Mullvad GUI: **Settings → Split tunneling → Add tailscaled**.
3. Always pass `--accept-dns=false` when enrolling to avoid DNS hijacking:
   ```bash
   sudo tailscale up --login-server https://hs.yourdomain.com --authkey <key> --accept-dns=false
   ```

---

### "RATELIMIT" in tailscaled Logs

**Symptom:** `journalctl -u tailscaled` shows lines like:
```
[RATELIMIT] format("Received error: %v")
```

**Cause:** This is **NOT** a server-side rate limit from Headscale. It is tailscaled's internal log suppressor de-duplicating repeated connection-refused error messages. The real underlying error is `connection refused`.

**What to check:**
1. Is Headscale actually running? `curl https://hs.yourdomain.com/health`
2. Is your VPN blocking the connection? (see VPN Conflicts above)
3. Is there a firewall blocking port 443?

---

### "connection refused" on Port 443

If `tailscale up` fails but `curl` works, the issue is usually DNS or VPN:

```bash
# Does curl reach Headscale successfully?
curl -v https://hs.yourdomain.com/health

# Force IPv4 vs IPv6 to identify if it's an address-family issue
curl -4 https://hs.yourdomain.com/health
curl -6 https://hs.yourdomain.com/health

# Check what IP headscale resolves to
dig +short hs.yourdomain.com

# What resolver is the system using?
cat /etc/resolv.conf
```

If curl works but tailscale doesn't, tailscaled may be using a different DNS resolver (e.g. its own `100.100.100.100` stub resolver). Fix: pass `--accept-dns=false`.

---

### Headscale User ID Lookup (0.28.0)

Headscale 0.28.0 removed `--user <name>` in favour of `-u <numeric-id>`. To find the numeric ID for a user:

```bash
headscale users list -o json
# Output: [{"id": "1", "name": "sovran-deploy", ...}, ...]

# One-liner to get the ID for a specific user
headscale users list -o json | jq -r '.[] | select(.name=="sovran-deploy") | .id'
```

Then use the numeric ID in subsequent commands:
```bash
headscale preauthkeys create -u 1 -e 1h -o json
headscale nodes register -u 1 --key mkey:xxxx
```

---

## Reference

| Component | Port | Protocol | Description |
|-----------|------|----------|-------------|
| Caddy     | 80   | TCP      | HTTP → HTTPS redirect |
| Caddy     | 443  | TCP      | HTTPS (Let's Encrypt) |
| Headscale | 8080 | TCP      | Coordination server (proxied by Caddy) |
| Provisioner | 9090 | TCP  | Registration API (proxied by Caddy) |
| DERP/STUN | 3478 | UDP     | WireGuard relay fallback |
| Tailscale | N/A  | WireGuard | Mesh VPN between nodes |
