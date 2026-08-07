#!/usr/bin/env bash
#
# upload-cdn.sh
# Copies built ISO out of the nix store, generates versioned SHA-256 checksum,
# verifies it, and optionally uploads to CDN.
#
# Usage:
#   ./scripts/upload-cdn.sh [--upload]
#
# EVERYTHING this script creates lives OUTSIDE the repository, even when you
# run it from inside the repo:
#   - the nix build output symlink  -> $ISO_OUT_DIR/result
#   - the ISO and .sha256 files     -> $ISO_OUT_DIR
# The repo working tree stays completely clean.
#
# Environment variables (optional):
#   ISO_OUT_DIR        - dir for the build symlink + ISO + checksum
#                        (default: ~/Sovran-builds)
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

# Always operate from the repo root, no matter where the script is invoked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Read version from VERSION file
if [ ! -f VERSION ]; then
    echo -e "${RED}Error: VERSION file not found in $REPO_ROOT.${NC}" >&2
    exit 1
fi
VERSION=$(cat VERSION | tr -d '\n\r ')
ISO_NAME="Sovran_SystemsOS-${VERSION}.iso"
SHA_NAME="${ISO_NAME}.sha256"

# Output directory OUTSIDE the repo (override with ISO_OUT_DIR)
OUT_DIR="${ISO_OUT_DIR:-$HOME/Sovran-builds}"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
ISO_PATH="$OUT_DIR/${ISO_NAME}"
SHA_PATH="$OUT_DIR/${SHA_NAME}"
RESULT_LINK="$OUT_DIR/result"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Sovran_SystemsOS CDN ISO Packaging & Upload Tool      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo -e "  Version : ${CYAN}${VERSION}${NC}"
echo -e "  ISO     : ${CYAN}${ISO_NAME}${NC}"
echo -e "  Repo    : ${CYAN}${REPO_ROOT}${NC}   (left untouched)"
echo -e "  Output  : ${CYAN}${OUT_DIR}${NC}   (outside the repo)"
echo

# Locate or build ISO
SRC_ISO=""
if [ -f "$RESULT_LINK/iso/${ISO_NAME}" ]; then
    SRC_ISO="$RESULT_LINK/iso/${ISO_NAME}"
elif [ -f "$RESULT_LINK/iso/Sovran_SystemsOS.iso" ]; then
    SRC_ISO="$RESULT_LINK/iso/Sovran_SystemsOS.iso"
elif [ -f "result/iso/${ISO_NAME}" ]; then
    SRC_ISO="result/iso/${ISO_NAME}"   # legacy: from an older in-repo build
elif [ -f "result/iso/Sovran_SystemsOS.iso" ]; then
    SRC_ISO="result/iso/Sovran_SystemsOS.iso"
else
    FOUND=$(find "$RESULT_LINK" result -name "*.iso" 2>/dev/null | head -n 1 || true)
    if [ -n "$FOUND" ]; then
        SRC_ISO="$FOUND"
    fi
fi

if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    echo -e "${YELLOW}Built ISO not found. Building via Nix (result link goes outside the repo)...${NC}"
    rm -f "$RESULT_LINK"
    nix build .#nixosConfigurations.sovran_systemsos-iso.config.system.build.isoImage \
        --out-link "$RESULT_LINK"

    if [ -f "$RESULT_LINK/iso/${ISO_NAME}" ]; then
        SRC_ISO="$RESULT_LINK/iso/${ISO_NAME}"
    else
        FOUND=$(find "$RESULT_LINK" -name "*.iso" 2>/dev/null | head -n 1 || true)
        if [ -n "$FOUND" ]; then
            SRC_ISO="$FOUND"
        fi
    fi
fi

if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    echo -e "${RED}Error: Failed to locate built ISO.${NC}" >&2
    exit 1
fi

echo -e "${BLUE}Step 1: Copying built ISO to output dir (outside repo)...${NC}"
cp -v "$SRC_ISO" "$ISO_PATH"
echo -e "  ${GREEN}✓${NC} Copied to $ISO_PATH"

echo
echo -e "${BLUE}Step 2: Generating versioned SHA-256 checksum...${NC}"
sha256sum "$ISO_PATH" > "$SHA_PATH"
echo -e "  ${GREEN}✓${NC} Generated $SHA_PATH"
cat "$SHA_PATH"

echo
echo -e "${BLUE}Step 3: Verifying checksum...${NC}"
sha256sum --check "$SHA_PATH"
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
        rsync -avP "$ISO_PATH" "$SHA_PATH" "${CDN_RSYNC_TARGET}"
        UPLOADED=1
    fi

    if [ -n "${CDN_RCLONE_REMOTE:-}" ]; then
        echo -e "  Uploading via rclone to ${CDN_RCLONE_REMOTE}..."
        rclone copy "$ISO_PATH" "$SHA_PATH" "${CDN_RCLONE_REMOTE}"
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
    echo -e "Ready files (in ${CYAN}${OUT_DIR}${NC}, outside the repo):"
    ls -lh "$ISO_PATH" "$SHA_PATH"
    echo
    echo "To upload to CDN, run:"
    echo "  ./scripts/upload-cdn.sh --upload"
    echo "(configure CDN_RSYNC_TARGET, CDN_RCLONE_REMOTE, or CDN_UPLOAD_CMD)"
fi
