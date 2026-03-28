{ config, pkgs, lib, ... }:

let
  domains = config.sovran_systemsOS.domainRequirements;

  domainNamesList = lib.concatMapStringsSep " " (d: d.name) domains;

  ddnsPrompt = ''
    read -p "  Njal.la DDNS curl command (paste full line, or Enter to skip): " DDNS_LINE
    if [ -n "$DDNS_LINE" ]; then
      # Strip any leading "curl " if they pasted the whole command
      DDNS_LINE="''${DDNS_LINE#curl }"
      # Strip surrounding quotes
      DDNS_LINE="''${DDNS_LINE%\"}"
      DDNS_LINE="''${DDNS_LINE#\"}"
      # Replace &auto with &a=''${IP} at the end
      DDNS_LINE="''${DDNS_LINE%auto}&a=''${DOLLAR}{IP}"
      # Remove any trailing double &a= if they already had &a=
      DDNS_LINE=$(echo "$DDNS_LINE" | sed 's/&a=&a=/\&a=/g')
  '';

  confirmDomain = name: ''
    while true; do
      echo ""
      printf "%b%s%b\n" "$YELLOW" "  You entered:" "$NC"
      printf "%b%s%b\n" "$CYAN" "    Domain:   $DOMAIN" "$NC"
      if [ -n "''${DDNS_DISPLAY:-}" ]; then
        printf "%b%s%b\n" "$CYAN" "    DDNS URL: $DDNS_DISPLAY" "$NC"
      fi
      echo ""
      read -p "  Is this correct? (y/n): " CONFIRM
      case "$CONFIRM" in
        [yY])
          echo "$DOMAIN" > "/var/lib/domains/${name}"
          printf "%b%s%b\n" "$GREEN" "  Saved." "$NC"
          break
          ;;
        [nN])
          echo "  Let's try again."
          REDO=true
          break
          ;;
        *)
          echo "  Please enter y or n."
          ;;
      esac
    done
  '';

  domainPrompts = lib.concatMapStringsSep "\n" (d: ''
    REDO=true
    while [ "$REDO" = true ]; do
      REDO=false
      DDNS_DISPLAY=""
      echo ""
      printf "%b%s%b\n" "$GREEN" "── ${d.label} ──" "$NC"
      EXISTING=""
      if [ -f "/var/lib/domains/${d.name}" ]; then
        EXISTING=$(cat "/var/lib/domains/${d.name}")
        printf "%b%s%b\n" "$CYAN" "  Current: $EXISTING" "$NC"
      fi
      read -p "  Subdomain (e.g. ${d.example}) or Enter to keep current: " DOMAIN_INPUT
      DOMAIN="''${DOMAIN_INPUT:-$EXISTING}"

      if [ -n "$DOMAIN" ]; then
        ${lib.optionalString d.needsDDNS ''
        ${ddnsPrompt}
          DDNS_DISPLAY="$DDNS_LINE"
          PENDING_NJALLA="curl \"$DDNS_LINE\""
        fi
        ''}

        ${confirmDomain d.name}

        if [ "$REDO" = false ] && [ -n "''${PENDING_NJALLA:-}" ]; then
          NJALLA_ENTRIES="$NJALLA_ENTRIES
$PENDING_NJALLA"
          PENDING_NJALLA=""
        fi
      else
        echo "  Skipped."
      fi
    done
  '') domains;

  missingDomainPrompts = lib.concatMapStringsSep "\n" (d: ''
    if [ ! -f "/var/lib/domains/${d.name}" ]; then
      MISSING=true
      REDO=true
      while [ "$REDO" = true ]; do
        REDO=false
        DDNS_DISPLAY=""
        echo ""
        printf "%b%s%b\n" "$GREEN" "── ${d.label} (NEW) ──" "$NC"
        read -p "  Subdomain (e.g. ${d.example}): " DOMAIN

        if [ -n "$DOMAIN" ]; then
          ${lib.optionalString d.needsDDNS ''
          ${ddnsPrompt}
            DDNS_DISPLAY="$DDNS_LINE"
            PENDING_NJALLA="curl \"$DDNS_LINE\""
          fi
          ''}

          ${confirmDomain d.name}

          if [ "$REDO" = false ] && [ -n "''${PENDING_NJALLA:-}" ]; then
            NEW_NJALLA_ENTRIES="$NEW_NJALLA_ENTRIES
$PENDING_NJALLA"
            PENDING_NJALLA=""
          fi
        else
          echo "  Skipped."
        fi
      done
    fi
  '') domains;

  domainSummary = lib.concatMapStringsSep "\n" (d: ''
    if [ -f "/var/lib/domains/${d.name}" ]; then
      printf "%b%s%b\n" "$NC" "  ${d.label}: $(cat /var/lib/domains/${d.name})" "$NC"
    fi
  '') domains;

  setupScript = pkgs.writeShellScriptBin "sovran-setup-domains" ''
    set -euo pipefail

    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    NC='\033[0m'
    DOLLAR='$'

    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  Sovran_SystemsOS — Domain & DDNS Setup" "$NC"
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    echo ""
    printf "%b%s%b\n" "$YELLOW" "Before running this, you need:" "$NC"
    echo ""
    echo "  1. Domains/subdomains purchased on https://njal.la"
    echo "  2. For each subdomain, add a Dynamic record in"
    echo "     your Njal.la dashboard."
    echo "  3. Njal.la will give you a curl command like:"
    echo ""
    printf "%b%s%b\n" "$CYAN" "     curl \"https://njal.la/update/?h=sub.domain.com&k=abc123&auto\"" "$NC"
    echo ""
    echo "  Have those curl commands ready."
    echo ""
    read -p "Press Enter to continue..."

    # ── Create directories ────────────────────────────
    mkdir -p /var/lib/domains

    NJALLA_ENTRIES=""
    PENDING_NJALLA=""

    # ── SSL Email ─────────────────────────────────────
    REDO=true
    while [ "$REDO" = true ]; do
      REDO=false
      echo ""
      printf "%b%s%b\n" "$GREEN" "── SSL Certificate Email ──" "$NC"
      echo "Let's Encrypt needs an email for certificate notifications."
      EXISTING_EMAIL=""
      if [ -f "/var/lib/domains/sslemail" ]; then
        EXISTING_EMAIL=$(cat /var/lib/domains/sslemail)
        printf "%b%s%b\n" "$CYAN" "  Current: $EXISTING_EMAIL" "$NC"
      fi
      read -p "  Email address (or Enter to keep current): " EMAIL_INPUT
      SSL_EMAIL="''${EMAIL_INPUT:-$EXISTING_EMAIL}"
      if [ -n "$SSL_EMAIL" ]; then
        while true; do
          echo ""
          printf "%b%s%b\n" "$YELLOW" "  You entered:" "$NC"
          printf "%b%s%b\n" "$CYAN" "    Email: $SSL_EMAIL" "$NC"
          echo ""
          read -p "  Is this correct? (y/n): " CONFIRM
          case "$CONFIRM" in
            [yY])
              echo "$SSL_EMAIL" > /var/lib/domains/sslemail
              printf "%b%s%b\n" "$GREEN" "  Saved." "$NC"
              break
              ;;
            [nN])
              echo "  Let's try again."
              REDO=true
              break
              ;;
            *)
              echo "  Please enter y or n."
              ;;
          esac
        done
      fi
    done

    # ── All module domains ────────────────────────────
    ${domainPrompts}

    # ── Final review ──────────────────────────────────
    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  Review All Entries" "$NC"
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    echo ""
    echo "  Configured domains:"
    ${domainSummary}
    echo ""
    echo "  DDNS entries:"
    if [ -n "$NJALLA_ENTRIES" ]; then
      echo "$NJALLA_ENTRIES"
    else
      echo "    (none)"
    fi
    echo ""
    read -p "  Does everything look correct? (y/n): " FINAL_CONFIRM
    if [ "$FINAL_CONFIRM" != "y" ] && [ "$FINAL_CONFIRM" != "Y" ]; then
      echo ""
      printf "%b%s%b\n" "$YELLOW" "  Setup cancelled. Run 'sudo sovran-setup-domains' to start over." "$NC"
      echo ""
      exit 1
    fi

    # ── Append curl entries to njalla.sh ──────────────
    if [ -n "$NJALLA_ENTRIES" ]; then
      echo ""
      printf "%b%s%b\n" "$GREEN" "── Updating DDNS script ──" "$NC"
      echo "$NJALLA_ENTRIES" >> /var/lib/njalla/njalla.sh
      echo "  Appended entries to /var/lib/njalla/njalla.sh"
    fi

    # ── Run DDNS update now ───────────────────────────
    echo ""
    read -p "Update Njal.la DNS records now? (y/n): " RUN_NOW
    if [ "$RUN_NOW" = "y" ]; then
      bash /var/lib/njalla/njalla.sh
      echo "  DNS records updated."
    fi

    # ── Mark setup complete ───────────────────────────
    touch /var/lib/domains/.setup-complete

    # ── Summary ───────────────────────────────────────
    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  Setup Complete!" "$NC"
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    echo ""
    echo "  Domain files:   /var/lib/domains/"
    echo "  DDNS script:    /var/lib/njalla/njalla.sh"
    echo "  DDNS cron:      Every 15 minutes (already configured)"
    echo ""
    printf "%b%s%b\n" "$YELLOW" "  Rebuilding to activate services with new domains..." "$NC"
    echo ""
    nixos-rebuild switch --flake /etc/nixos#nixos
  '';

  addDomainScript = pkgs.writeShellScriptBin "sovran-add-domains" ''
    set -euo pipefail

    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    NC='\033[0m'
    DOLLAR='$'

    MISSING=false
    NEW_NJALLA_ENTRIES=""
    PENDING_NJALLA=""

    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  Sovran_SystemsOS — New Feature Domains" "$NC"
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    echo ""
    echo "  Checking for newly enabled features that need domains..."

    mkdir -p /var/lib/domains

    ${missingDomainPrompts}

    if [ "$MISSING" = false ]; then
      echo ""
      printf "%b%s%b\n" "$GREEN" "  All domains are already configured. Nothing to do." "$NC"
      echo ""
      exit 0
    fi

    # ── Final review ──────────────────────────────────
    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  Review New Entries" "$NC"
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    echo ""
    echo "  All configured domains:"
    ${domainSummary}
    echo ""
    echo "  New DDNS entries:"
    if [ -n "$NEW_NJALLA_ENTRIES" ]; then
      echo "$NEW_NJALLA_ENTRIES"
    else
      echo "    (none)"
    fi
    echo ""
    read -p "  Does everything look correct? (y/n): " FINAL_CONFIRM
    if [ "$FINAL_CONFIRM" != "y" ] && [ "$FINAL_CONFIRM" != "Y" ]; then
      echo ""
      printf "%b%s%b\n" "$YELLOW" "  Setup cancelled. Run 'sudo sovran-add-domains' to start over." "$NC"
      echo ""
      exit 1
    fi

    # ── Append new entries to njalla.sh ───────────────
    if [ -n "$NEW_NJALLA_ENTRIES" ]; then
      echo ""
      printf "%b%s%b\n" "$GREEN" "── Updating DDNS script ──" "$NC"
      echo "$NEW_NJALLA_ENTRIES" >> /var/lib/njalla/njalla.sh
      echo "  Appended new entries to /var/lib/njalla/njalla.sh"

      echo ""
      read -p "Update Njal.la DNS records now? (y/n): " RUN_NOW
      if [ "$RUN_NOW" = "y" ]; then
        bash /var/lib/njalla/njalla.sh
        echo "  DNS records updated."
      fi
    fi

    # ── Summary ───────────────────────────────────────
    echo ""
    printf "%b%s%b\n" "$CYAN" "══════════════════════════════════════════════" "$NC"
    printf "%b%s%b\n" "$CYAN" "  New Domains Added!" "$NC"
    printf "%b%s%b\n" "$CYAN" "════════���═════════════════════════════════════" "$NC"
    echo ""
    echo "  All configured domains:"
    ${domainSummary}
    echo ""
    printf "%b%s%b\n" "$YELLOW" "  Rebuilding to activate services with new domains..." "$NC"
    echo ""
    nixos-rebuild switch --flake /etc/nixos#nixos
  '';

  needsSetup = pkgs.writeShellScriptBin "sovran-domains-need-setup" ''
    # First boot — no setup done at all
    if [ ! -f /var/lib/domains/.setup-complete ]; then
      exit 0
    fi

    # Existing machine — check for missing domain files
    for NAME in ${domainNamesList}; do
      if [ ! -f "/var/lib/domains/$NAME" ]; then
        exit 0
      fi
    done

    # Everything is configured
    exit 1
  '';

in
{
  environment.systemPackages = [
    setupScript
    addDomainScript
    needsSetup
  ];

  environment.etc."xdg/autostart/sovran-setup-domains.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Sovran_SystemsOS Domain Setup
    Comment=Configure domains for newly enabled features
    Exec=${pkgs.bash}/bin/bash -c 'if ${needsSetup}/bin/sovran-domains-need-setup; then if [ ! -f /var/lib/domains/.setup-complete ]; then ${pkgs.gnome-terminal}/bin/gnome-terminal -- sudo ${setupScript}/bin/sovran-setup-domains; else ${pkgs.gnome-terminal}/bin/gnome-terminal -- sudo ${addDomainScript}/bin/sovran-add-domains; fi; fi'
    Terminal=false
    X-GNOME-Autostart-enabled=true
  '';
}
