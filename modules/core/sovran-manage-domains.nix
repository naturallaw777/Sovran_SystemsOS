{ config, pkgs, lib, ... }:

let
  domains = config.sovran_systemsOS.domainRequirements;

  # Build the domain prompts dynamically from registered modules
  domainPrompts = lib.concatMapStringsSep "\n" (d: ''
    echo ""
    echo -e "''${GREEN}── ${d.label} ──''${NC}"
    EXISTING=""
    if [ -f "/var/lib/domains/${d.name}" ]; then
      EXISTING=$(cat "/var/lib/domains/${d.name}")
      echo -e "  Current: ''${CYAN}$EXISTING''${NC}"
    fi
    read -p "  Subdomain (e.g. ${d.example}) or Enter to keep current: " DOMAIN_INPUT
    DOMAIN="''${DOMAIN_INPUT:-$EXISTING}"

    if [ -n "$DOMAIN" ]; then
      echo "$DOMAIN" > "/var/lib/domains/${d.name}"
      echo "  Saved: $DOMAIN"
      ${lib.optionalString d.needsDDNS ''
      read -p "  Njal.la DDNS URL for $DOMAIN (paste full URL, or Enter to skip): " DDNS_URL
      if [ -n "$DDNS_URL" ]; then
        NJALLA_ENTRIES="$NJALLA_ENTRIES
curl \"''${DDNS_URL%auto}''${DOLLAR}{IP}\""
      fi
      ''}
    else
      echo "  Skipped."
    fi
  '') domains;

  # Build the summary list
  domainSummary = lib.concatMapStringsSep "\n" (d: ''
    if [ -f "/var/lib/domains/${d.name}" ]; then
      echo "  ${d.label}: $(cat /var/lib/domains/${d.name})"
    fi
  '') domains;
in
{
  environment.systemPackages = [
    (pkgs.writeShellScriptBin "sovran-setup-domains" ''
      set -euo pipefail

      GREEN='\033[0;32m'
      YELLOW='\033[1;33m'
      CYAN='\033[0;36m'
      NC='\033[0m'
      DOLLAR='$'

      echo ""
      echo -e "''${CYAN}══════════════════════════════════════════════''${NC}"
      echo -e "''${CYAN}  Sovran_SystemsOS — Domain & DDNS Setup''${NC}"
      echo -e "''${CYAN}══════════════════════════════════════════════''${NC}"
      echo ""
      echo -e "''${YELLOW}Before running this, you need:''${NC}"
      echo ""
      echo "  1. Domains/subdomains purchased on https://njal.la"
      echo "  2. For each subdomain, add a Dynamic record in"
      echo "     your Njal.la dashboard."
      echo "  3. Njal.la will give you a DDNS URL like:"
      echo ""
      echo -e "     ''${CYAN}https://njal.la/update/?h=sub.domain.com&k=abc123&auto''${NC}"
      echo ""
      echo "  Have those URLs ready."
      echo ""
      read -p "Press Enter to continue..."

      # ── Create directories ────────────────────────────
      mkdir -p /var/lib/domains
      mkdir -p /var/lib/njalla

      NJALLA_ENTRIES=""

      # ── SSL Email ─────────────────────────────────────
      echo ""
      echo -e "''${GREEN}── SSL Certificate Email ──''${NC}"
      echo "Let's Encrypt needs an email for certificate notifications."
      EXISTING_EMAIL=""
      if [ -f "/var/lib/domains/sslemail" ]; then
        EXISTING_EMAIL=$(cat /var/lib/domains/sslemail)
        echo -e "  Current: ''${CYAN}$EXISTING_EMAIL''${NC}"
      fi
      read -p "  Email address (or Enter to keep current): " EMAIL_INPUT
      SSL_EMAIL="''${EMAIL_INPUT:-$EXISTING_EMAIL}"
      if [ -n "$SSL_EMAIL" ]; then
        echo "$SSL_EMAIL" > /var/lib/domains/sslemail
        echo "  Saved."
      fi

      # ── Module domains (auto-generated from enabled modules) ──
      ${domainPrompts}

      # ── Write njalla.sh ───────────────────────────────
      echo ""
      echo -e "''${GREEN}── Generating DDNS script ──''${NC}"

      cat > /var/lib/njalla/njalla.sh <<SCRIPT
#!/usr/bin/env bash
IP=\$(dig @resolver4.opendns.com myip.opendns.com +short -4)
$NJALLA_ENTRIES
SCRIPT

      chmod 700 /var/lib/njalla/njalla.sh
      echo "  Written to /var/lib/njalla/njalla.sh"

      # ── Run DDNS update now ───────────────────────────
      echo ""
      read -p "Update Njal.la DNS records now? (y/n): " RUN_NOW
      if [ "$RUN_NOW" = "y" ]; then
        bash /var/lib/njalla/njalla.sh
        echo "  DNS records updated."
      fi

      # ── Summary ───────────────────────────────────────
      echo ""
      echo -e "''${CYAN}══════════════════════════════════════════════''${NC}"
      echo -e "''${CYAN}  Setup Complete!''${NC}"
      echo -e "''${CYAN}══════════════════════════════════════════════''${NC}"
      echo ""
      echo "  Configured domains:"
      ${domainSummary}
      echo ""
      echo "  Domain files:   /var/lib/domains/"
      echo "  DDNS script:    /var/lib/njalla/njalla.sh"
      echo "  DDNS cron:      Every 15 minutes (already configured)"
      echo ""
      echo "  Next step:"
      echo "    sudo nixos-rebuild switch --flake /etc/nixos#nixos"
      echo ""
    '')
  ];
}