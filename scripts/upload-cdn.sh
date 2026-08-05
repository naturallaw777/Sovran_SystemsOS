#!/usr/bin/env bash
#
# upload-cdn.sh
# Copies built ISO out of the nix store, generates versioned SHA-256 checksum,
# verifies it, and optionally uploads to CDN.
#
# Usage:
#   ./scripts/upload-cdn.sh [--upload]
#
# Environment variables (optional):
#   CDN_RSYNC_TARGET   - rsync destination (e.g. user@server:/var/www/downloads/)
#   CDN_RCLONE_REMOTE  - rclone remote target (e.g. s3:my-bucket/downloads/)
#   CDN_UPLOAD_CMD     - custom upload command
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Read version from VERSION file
if [ ! -f VERSION ]; then
    echo -e "${RED}Error: VERSION file not found.${NC}" >&2
    exit 1
fi
VERSION=$(cat VERSION | tr -d '\n\r ')
ISO_NAME="Sovran_SystemsOS-${VERSION}.iso"
SHA_NAME="${ISO_NAME}.sha256"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Sovran_SystemsOS CDN ISO Packaging & Upload Tool      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo -e "  Version : ${CYAN}${VERSION}${NC}"
echo -e "  ISO     : ${CYAN}${ISO_NAME}${NC}"
echo

# Locate or build ISO
SRC_ISO=""
if [ -f "result/iso/${ISO_NAME}" ]; then
    SRC_ISO="result/iso/${ISO_NAME}"
elif [ -f "result/iso/Sovran_SystemsOS.iso" ]; then
    SRC_ISO="result/iso/Sovran_SystemsOS.iso"
else
    FOUND=$(find result -name "*.iso" 2>/dev/null | head -n 1 || true)
    if [ -n "$FOUND" ]; then
        SRC_ISO="$FOUND"
    fi
fi

if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    echo -e "${YELLOW}Built ISO not found in result/. Building ISO via Nix...${NC}"
    nix build .#nixosConfigurations.sovran_systemsos-iso.config.system.build.isoImage
    
    if [ -f "result/iso/${ISO_NAME}" ]; then
        SRC_ISO="result/iso/${ISO_NAME}"
    else
        FOUND=$(find result -name "*.iso" 2>/dev/null | head -n 1 || true)
        if [ -n "$FOUND" ]; then
            SRC_ISO="$FOUND"
        else
            echo -e "${RED}Error: Failed to locate built ISO in result/.${NC}" >&2
            exit 1
        fi
    fi
fi

echo -e "${BLUE}Step 1: Copying built ISO out of Nix store...${NC}"
cp -v "$SRC_ISO" "./${ISO_NAME}"
echo -e "  ${GREEN}✓${NC} Copied to ./${ISO_NAME}"

echo
echo -e "${BLUE}Step 2: Generating versioned SHA-256 checksum...${NC}"
sha256sum "${ISO_NAME}" > "${SHA_NAME}"
echo -e "  ${GREEN}✓${NC} Generated ${SHA_NAME}"
cat "${SHA_NAME}"

echo
echo -e "${BLUE}Step 3: Verifying checksum...${NC}"
sha256sum --check "${SHA_NAME}"
echo -e "  ${GREEN}✓${NC} Checksum verified successfully"

# Parse arguments for upload
DO_UPLOAD=0
for arg in "$@"; do
    case $arg in
        --upload)
            DO_UPLOAD=1
            shift
            ;;
    esac
done

if [ "$DO_UPLOAD" -eq 1 ]; then
    echo
    echo -e "${BLUE}Step 4: Uploading to CDN...${NC}"
    
    UPLOADED=0
    if [ -n "${CDN_UPLOAD_CMD:-}" ]; then
        echo -e "  Running custom CDN_UPLOAD_CMD..."
        eval "$CDN_UPLOAD_CMD"
        UPLOADED=1
    fi

    if [ -n "${CDN_RSYNC_TARGET:-}" ]; then
        echo -e "  Uploading via rsync to ${CDN_RSYNC_TARGET}..."
        rsync -avP "${ISO_NAME}" "${SHA_NAME}" "${CDN_RSYNC_TARGET}"
        UPLOADED=1
    fi

    if [ -n "${CDN_RCLONE_REMOTE:-}" ]; then
        echo -e "  Uploading via rclone to ${CDN_RCLONE_REMOTE}..."
        rclone copy "${ISO_NAME}" "${SHA_NAME}" "${CDN_RCLONE_REMOTE}"
        UPLOADED=1
    fi

    if [ "$UPLOADED" -eq 0 ]; then
        echo -e "  ${YELLOW}⚠ Warning: --upload requested, but no upload method specified.${NC}"
        echo -e "     Set CDN_RSYNC_TARGET, CDN_RCLONE_REMOTE, or CDN_UPLOAD_CMD."
    else
        echo -e "  ${GREEN}✓${NC} Upload complete."
    fi
else
    echo
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           ✅ ISO packaging & verification complete!        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo -e "Ready files:"
    ls -lh "${ISO_NAME}" "${SHA_NAME}"
    echo
    echo "To upload to CDN, run:"
    echo "  ./scripts/upload-cdn.sh --upload"
    echo "(configure CDN_RSYNC_TARGET, CDN_RCLONE_REMOTE, or CDN_UPLOAD_CMD)"
fi
