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
- **`remote-deploy.nix`** — Post-install NixOS module that uses Tailscale/Headscale for ongoing access (plus the existing reverse SSH tunnel as a fallback).

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

    # Optional: set a static token instead of auto-generating one
    # enrollToken = "your-secret-token-here";

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

Keep this token secret — it is used to authenticate ISO registrations. If you set `enrollToken` statically in `configuration.nix`, that value is used directly (but avoid committing secrets to version control).

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
sudo tailscale up --login-server https://hs.yourdomain.com
```

Tailscale prints a URL. Open it and copy the node key (starts with `mkey:`).

### Approve the Node in Headscale

On the VPS:

```bash
headscale nodes register --user admin --key mkey:xxxxxxxxxxxxxxxx
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
   ```bash
   # Basic install (relay tunnel)
   sudo sovran-install-headless.sh \
     --disk /dev/sda \
     --role server \
     --deploy-key "ssh-ed25519 AAAA..." \
     --relay-host relay.yourdomain.com

   # With Tailscale for post-install access
   sudo sovran-install-headless.sh \
     --disk /dev/sda \
     --role server \
     --deploy-key "ssh-ed25519 AAAA..." \
     --headscale-server "https://hs.yourdomain.com" \
     --headscale-key "$(headscale preauthkeys create --user sovran-deploy --expiration 2h --output json | jq -r '.key')"
   ```

6. **Machine reboots into Sovran_SystemsOS** — `deploy-tailscale-connect.service` runs:
   - Reads `/var/lib/secrets/headscale-authkey`
   - Joins the Tailnet with a deterministic hostname (`sovran-<hostname>`)
   - The reverse SSH tunnel also activates if `relayHost` was set

7. **Post-install SSH and RDP**:
   ```bash
   # SSH over Tailnet
   ssh root@<tailscale-ip>

   # RDP over Tailnet (if desktop role)
   xfreerdp /v:<tailscale-ip> /u:free /p:free
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

# Over reverse tunnel (if configured)
ssh -p 2222 root@relay.yourdomain.com
```

### RDP (desktop/server roles)

```bash
# Over Tailnet
xfreerdp /v:100.64.x.x /u:free /p:free /dynamic-resolution
```

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

This stops the reverse tunnel and Tailscale connect services.

### Revoke All Active Pre-Auth Keys

```bash
headscale preauthkeys list --user sovran-deploy
headscale preauthkeys expire --user sovran-deploy --key <key>
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
