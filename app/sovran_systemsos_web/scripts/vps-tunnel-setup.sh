#!/usr/bin/env bash
# Sovran_SystemsOS — VPS WireGuard Tunnel Bootstrap Script
#
# This script is executed on the remote VPS via SSH by the Sovran Hub.
# It installs WireGuard, generates keypairs, configures iptables port
# forwarding (80, 443, 8448), and deploys a management SSH key so the
# Hub can later enable/disable port 22 forwarding for Tech Support.
#
# Outputs to stdout (captured by the Hub):
#   VPS_PUBKEY=<base64 wireguard public key>
#   VPS_ENDPOINT=<vps_ip:51820>
#   HUB_MGMT_PUBKEY=<base64 ssh public key for Hub management>
#
# Usage:
#   bash vps-tunnel-setup.sh <HOME_WG_PUBKEY> <HOME_WG_IP> [HUB_SSH_PUBKEY]
#
# HOME_WG_PUBKEY : WireGuard public key of the home server (client)
# HOME_WG_IP     : WireGuard tunnel IP to assign to the home server (e.g. 10.99.0.2)
# HUB_SSH_PUBKEY : (optional) SSH public key for Hub management user

set -euo pipefail

HOME_WG_PUBKEY="${1:-}"
HOME_WG_IP="${2:-10.99.0.2}"
HUB_SSH_PUBKEY="${3:-}"

WG_IFACE="wg0"
WG_DIR="/etc/wireguard"
WG_CONF="${WG_DIR}/${WG_IFACE}.conf"
VPS_WG_IP="10.99.0.1"
VPS_WG_PORT="51820"
MGMT_USER="sovran-mgmt"
MGMT_USER_HOME="/var/lib/${MGMT_USER}"
MGMT_SSH_DIR="${MGMT_USER_HOME}/.ssh"
MGMT_AUTH_KEYS="${MGMT_SSH_DIR}/authorized_keys"
HUB_SSH_KEY_FILE="/etc/sovran/hub-mgmt.pub"

log() { echo "[sovran-tunnel] $*" >&2; }

# ── Detect OS and install WireGuard ──────────────────────────────

install_wireguard() {
    if command -v wg &>/dev/null; then
        log "WireGuard already installed"
        return 0
    fi

    if command -v apt-get &>/dev/null; then
        log "Installing WireGuard via apt..."
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq wireguard wireguard-tools iptables
    elif command -v yum &>/dev/null; then
        log "Installing WireGuard via yum..."
        yum install -y epel-release
        yum install -y wireguard-tools iptables
    elif command -v dnf &>/dev/null; then
        log "Installing WireGuard via dnf..."
        dnf install -y wireguard-tools iptables
    elif command -v pacman &>/dev/null; then
        log "Installing WireGuard via pacman..."
        pacman -S --noconfirm wireguard-tools iptables
    else
        log "ERROR: No supported package manager found (apt/yum/dnf/pacman)"
        exit 1
    fi
}

# ── Enable IP forwarding ──────────────────────────────────────────

enable_ip_forwarding() {
    log "Enabling IP forwarding..."
    sysctl -w net.ipv4.ip_forward=1 > /dev/null
    if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    # Also handle sysctl.d
    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-sovran-tunnel.conf
}

# ── Generate or reuse WireGuard keypair ──────────────────────────

setup_wg_keys() {
    mkdir -p "${WG_DIR}"
    chmod 700 "${WG_DIR}"

    if [[ -f "${WG_DIR}/privatekey" && -f "${WG_DIR}/publickey" ]]; then
        log "Reusing existing WireGuard keypair"
    else
        log "Generating new WireGuard keypair..."
        wg genkey | tee "${WG_DIR}/privatekey" | wg pubkey > "${WG_DIR}/publickey"
        chmod 600 "${WG_DIR}/privatekey"
    fi
    VPS_PRIVKEY=$(cat "${WG_DIR}/privatekey")
    VPS_PUBKEY=$(cat "${WG_DIR}/publickey")
}

# ── Detect primary network interface ─────────────────────────────

detect_iface() {
    WAN_IFACE=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')
    if [[ -z "${WAN_IFACE}" ]]; then
        WAN_IFACE=$(ls /sys/class/net/ | grep -v lo | head -1)
    fi
    log "WAN interface: ${WAN_IFACE}"
}

# ── Write WireGuard config ────────────────────────────────────────

write_wg_config() {
    log "Writing WireGuard config to ${WG_CONF}..."
    cat > "${WG_CONF}" << EOF
[Interface]
Address = ${VPS_WG_IP}/24
ListenPort = ${VPS_WG_PORT}
PrivateKey = ${VPS_PRIVKEY}

# Automatically manage iptables rules via PostUp/PreDown
PostUp = /etc/sovran/tunnel-rules.sh up ${WAN_IFACE} ${HOME_WG_IP}
PreDown = /etc/sovran/tunnel-rules.sh down ${WAN_IFACE} ${HOME_WG_IP}

[Peer]
# Home Server
PublicKey = ${HOME_WG_PUBKEY:-PLACEHOLDER_REPLACE_WITH_HOME_PUBKEY}
AllowedIPs = ${HOME_WG_IP}/32
PersistentKeepalive = 25
EOF
    chmod 600 "${WG_CONF}"
}

# ── Write iptables rules script ───────────────────────────────────

write_rules_script() {
    mkdir -p /etc/sovran
    log "Writing tunnel rules script..."
    cat > /etc/sovran/tunnel-rules.sh << 'RULES'
#!/usr/bin/env bash
# Manage iptables forwarding rules for the Sovran tunnel.
# Usage: tunnel-rules.sh up|down <WAN_IFACE> <HOME_WG_IP>
ACTION="$1"
WAN="${2:-eth0}"
HOME_IP="${3:-10.99.0.2}"

PORTS_TCP="80 443 8448"

case "$ACTION" in
  up)
    # Masquerade outgoing WireGuard traffic
    iptables -t nat -C POSTROUTING -o "${WAN}" -j MASQUERADE 2>/dev/null || \
      iptables -t nat -A POSTROUTING -o "${WAN}" -j MASQUERADE

    # Allow forwarding between WAN and WireGuard
    iptables -C FORWARD -i "${WAN}" -o wg0 -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -i "${WAN}" -o wg0 -j ACCEPT
    iptables -C FORWARD -i wg0 -o "${WAN}" -j ACCEPT 2>/dev/null || \
      iptables -A FORWARD -i wg0 -o "${WAN}" -j ACCEPT

    # DNAT: forward public ports 80, 443, 8448 to home server
    for PORT in $PORTS_TCP; do
      iptables -t nat -C PREROUTING -i "${WAN}" -p tcp --dport "${PORT}" -j DNAT \
        --to-destination "${HOME_IP}:${PORT}" 2>/dev/null || \
      iptables -t nat -A PREROUTING -i "${WAN}" -p tcp --dport "${PORT}" -j DNAT \
        --to-destination "${HOME_IP}:${PORT}"
    done
    ;;
  down)
    # Remove DNAT rules
    for PORT in $PORTS_TCP; do
      iptables -t nat -D PREROUTING -i "${WAN}" -p tcp --dport "${PORT}" -j DNAT \
        --to-destination "${HOME_IP}:${PORT}" 2>/dev/null || true
    done
    iptables -D FORWARD -i "${WAN}" -o wg0 -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i wg0 -o "${WAN}" -j ACCEPT 2>/dev/null || true
    iptables -t nat -D POSTROUTING -o "${WAN}" -j MASQUERADE 2>/dev/null || true
    ;;
esac
RULES
    chmod +x /etc/sovran/tunnel-rules.sh
}

# ── Write SSH port-22 forwarding toggle script ────────────────────

write_ssh_toggle_script() {
    log "Writing SSH forwarding toggle script..."
    cat > /etc/sovran/ssh-forward.sh << 'SSH_TOGGLE'
#!/usr/bin/env bash
# Toggle SSH port-22 forwarding through the tunnel.
# Usage: ssh-forward.sh enable|disable <WAN_IFACE> <HOME_WG_IP>
ACTION="$1"
WAN="${2:-eth0}"
HOME_IP="${3:-10.99.0.2}"

case "$ACTION" in
  enable)
    iptables -t nat -C PREROUTING -i "${WAN}" -p tcp --dport 22 -j DNAT \
      --to-destination "${HOME_IP}:22" 2>/dev/null || \
    iptables -t nat -A PREROUTING -i "${WAN}" -p tcp --dport 22 -j DNAT \
      --to-destination "${HOME_IP}:22"
    echo "SSH forwarding enabled"
    ;;
  disable)
    iptables -t nat -D PREROUTING -i "${WAN}" -p tcp --dport 22 -j DNAT \
      --to-destination "${HOME_IP}:22" 2>/dev/null || true
    echo "SSH forwarding disabled"
    ;;
  *)
    echo "Usage: $0 enable|disable <WAN_IFACE> <HOME_WG_IP>"
    exit 1
    ;;
esac
SSH_TOGGLE
    chmod +x /etc/sovran/ssh-forward.sh

    # Store WAN iface and HOME_WG_IP for later calls
    cat > /etc/sovran/tunnel-env << EOF
WAN_IFACE=${WAN_IFACE}
HOME_WG_IP=${HOME_WG_IP}
EOF
}

# ── Create management user with limited SSH access ────────────────

setup_mgmt_user() {
    log "Setting up management user '${MGMT_USER}'..."

    if ! id -u "${MGMT_USER}" &>/dev/null; then
        useradd --system --home-dir "${MGMT_USER_HOME}" \
            --create-home --shell /bin/bash "${MGMT_USER}"
    fi

    mkdir -p "${MGMT_SSH_DIR}"
    chmod 700 "${MGMT_SSH_DIR}"
    chown "${MGMT_USER}:${MGMT_USER}" "${MGMT_SSH_DIR}"

    # Write Hub SSH public key if provided, else generate one
    if [[ -n "${HUB_SSH_PUBKEY}" ]]; then
        echo "${HUB_SSH_PUBKEY}" > "${MGMT_AUTH_KEYS}"
        chmod 600 "${MGMT_AUTH_KEYS}"
        chown "${MGMT_USER}:${MGMT_USER}" "${MGMT_AUTH_KEYS}"
        mkdir -p /etc/sovran
        echo "${HUB_SSH_PUBKEY}" > "${HUB_SSH_KEY_FILE}"
        log "Deployed Hub SSH public key"
    fi

    # Allow the management user to run only the tunnel scripts as root
    local sudoers_line="${MGMT_USER} ALL=(root) NOPASSWD: /etc/sovran/ssh-forward.sh"
    if ! grep -qF "${MGMT_USER}" /etc/sudoers.d/sovran-mgmt 2>/dev/null; then
        echo "${sudoers_line}" > /etc/sudoers.d/sovran-mgmt
        chmod 440 /etc/sudoers.d/sovran-mgmt
    fi
}

# ── Generate Hub SSH keypair on VPS if not provided ───────────────

maybe_generate_hub_keypair() {
    # If a Hub SSH key was not provided, generate a key for the management
    # user and output the public key so the Hub can store it.
    if [[ -z "${HUB_SSH_PUBKEY}" ]]; then
        local hub_key_priv="${MGMT_USER_HOME}/.ssh/id_ed25519"
        if [[ ! -f "${hub_key_priv}" ]]; then
            log "Generating Hub management SSH keypair..."
            ssh-keygen -t ed25519 -N "" -f "${hub_key_priv}" -C "sovran-hub-mgmt" >/dev/null
            chown "${MGMT_USER}:${MGMT_USER}" "${hub_key_priv}" "${hub_key_priv}.pub"
        fi
        # Deploy the public key so the management user can log in with the private key
        cat "${hub_key_priv}.pub" > "${MGMT_AUTH_KEYS}"
        chmod 600 "${MGMT_AUTH_KEYS}"
        chown "${MGMT_USER}:${MGMT_USER}" "${MGMT_AUTH_KEYS}"
        HUB_MGMT_PRIVKEY=$(cat "${hub_key_priv}")
        HUB_MGMT_PUBKEY=$(cat "${hub_key_priv}.pub")
    fi
}

# ── Enable and start WireGuard service ───────────────────────────

start_wireguard() {
    log "Enabling and starting WireGuard service..."
    if command -v systemctl &>/dev/null; then
        systemctl enable "wg-quick@${WG_IFACE}" 2>/dev/null || true
        if systemctl is-active "wg-quick@${WG_IFACE}" &>/dev/null; then
            systemctl restart "wg-quick@${WG_IFACE}"
        else
            systemctl start "wg-quick@${WG_IFACE}"
        fi
    else
        wg-quick down "${WG_IFACE}" 2>/dev/null || true
        wg-quick up "${WG_IFACE}"
    fi
}

# ── Detect VPS public IP ──────────────────────────────────────────

detect_vps_ip() {
    VPS_IP=$(curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
             curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
             curl -s --max-time 5 https://icanhazip.com 2>/dev/null || \
             ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}' || \
             echo "unknown")
    log "VPS public IP: ${VPS_IP}"
}

# ── Main ─────────────────────────────────────────────────────────

main() {
    log "Starting Sovran VPS tunnel bootstrap..."

    install_wireguard
    enable_ip_forwarding
    setup_wg_keys
    detect_iface
    detect_vps_ip
    write_wg_config
    write_rules_script
    write_ssh_toggle_script
    setup_mgmt_user
    maybe_generate_hub_keypair
    start_wireguard

    log "Bootstrap complete."

    # Output machine-readable result for the Hub to capture
    echo "---SOVRAN-TUNNEL-OUTPUT-BEGIN---"
    echo "VPS_PUBKEY=${VPS_PUBKEY}"
    echo "VPS_ENDPOINT=${VPS_IP}:${VPS_WG_PORT}"
    echo "VPS_IP=${VPS_IP}"
    echo "VPS_WG_IP=${VPS_WG_IP}"
    echo "HOME_WG_IP=${HOME_WG_IP}"
    echo "WAN_IFACE=${WAN_IFACE}"
    echo "MGMT_USER=${MGMT_USER}"
    if [[ -n "${HUB_MGMT_PRIVKEY:-}" ]]; then
        # Base64-encode the private key to avoid newline issues in captured output
        echo "HUB_MGMT_PRIVKEY_B64=$(echo "${HUB_MGMT_PRIVKEY}" | base64 -w 0)"
        echo "HUB_MGMT_PUBKEY=${HUB_MGMT_PUBKEY}"
    fi
    echo "---SOVRAN-TUNNEL-OUTPUT-END---"
}

main "$@"
