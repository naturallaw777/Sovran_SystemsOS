# modules/core/tunnel.nix
#
# WireGuard client configuration for the Sovran VPS tunnel.
# When a VPS tunnel is configured, all public-facing traffic (ports 80, 443, 8448)
# routes through the VPS, keeping the home IP completely private.
#
# Tunnel state is stored in /var/lib/sovran-tunnel/ and managed by the Hub.

{ config, lib, pkgs, ... }:

let
  tunnelStateDir = "/var/lib/sovran-tunnel";
  tunnelConfigFile = "${tunnelStateDir}/tunnel.json";
  tunnelPrivkeyFile = "${tunnelStateDir}/wg-privatekey";
  wgInterface = "wg0";
in
{
  config = lib.mkIf (builtins.pathExists tunnelConfigFile) (
    let
      tunnelCfg = builtins.fromJSON (builtins.readFile tunnelConfigFile);
    in
    {
      # ── WireGuard network interface ──────────────────────────────
      networking.wireguard.interfaces."${wgInterface}" = {
        ips = [ "${tunnelCfg.home_wg_ip}/24" ];
        listenPort = 51821;  # Client uses a different port from server (51820)

        privateKeyFile = tunnelPrivkeyFile;

        peers = [
          {
            publicKey = tunnelCfg.vps_pubkey;
            endpoint = tunnelCfg.vps_endpoint;
            # Only route specific ports through the tunnel using policy routing,
            # not a blanket AllowedIPs = 0.0.0.0/0 which would break internet.
            # The VPS IP itself must be reachable through the default route.
            allowedIPs = [ "${tunnelCfg.vps_wg_ip}/32" ];
            persistentKeepalive = 25;
          }
        ];

        # Policy routing: redirect traffic on ports 80, 443, 8448 to use
        # the WireGuard tunnel rather than the default gateway.
        postSetup = ''
          # Ensure WireGuard tunnel is used for ports 80/443/8448 via DNAT reflection
          # The VPS already handles the inbound DNAT; outbound replies route via wg0
          # because source is VPS WG IP range.
          ip rule add fwmark 0x1 table 51820 2>/dev/null || true
          ip route add default dev ${wgInterface} table 51820 2>/dev/null || true
          ${pkgs.iptables}/bin/iptables -t mangle -A OUTPUT -p tcp -m multiport \
            --sports 80,443,8448 -j MARK --set-mark 0x1 || true
        '';
        postShutdown = ''
          ${pkgs.iptables}/bin/iptables -t mangle -D OUTPUT -p tcp -m multiport \
            --sports 80,443,8448 -j MARK --set-mark 0x1 2>/dev/null || true
          ip rule del fwmark 0x1 table 51820 2>/dev/null || true
          ip route del default dev ${wgInterface} table 51820 2>/dev/null || true
        '';
      };

      # Ensure the tunnel state directory exists with correct permissions
      systemd.tmpfiles.rules = [
        "d ${tunnelStateDir} 0700 root root -"
      ];
    }
  );
}
