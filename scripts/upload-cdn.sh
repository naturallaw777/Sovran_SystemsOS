#!/usr/bin/env bash
#
# upload-cdn.sh
# Copies built ISO out of the nix store, generates versioned SHA-256 checksum,
# verifies it, and optionally uploads to CDN.
#
# Usage:
#   ./scripts/upload-cdn.sh [--upload] [--rebuild]
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
#   ISO_CONFIG         - flake attr holding the ISO (default:
#                        nixosConfigurations.sovran_systemsos-iso)
#   REPO_FLAKE_REF     - flake reference used to build. Defaults to "path:."
#                        so that gitignored files such as iso/secrets/enroll-token
#                        are actually visible to the build (a bare "." ref only
#                        sees git-tracked files and silently drops them).
#                        It is RELATIVE on purpose: a flake ref containing an
#                        absolute path with spaces cannot be parsed by Nix, and
#                        the script has already cd'd to the repo root.
#   CDN_RSYNC_TARGET   - rsync destination (e.g. user@server:/var/www/downloads/)
#   CDN_RCLONE_REMOTE  - rclone remote target (e.g. s3:my-bucket/downloads/)
#   CDN_UPLOAD_CMD     - custom upload command
#
# Notes on finding the ISO:
#   A Nix build result is a SYMLINK to an immutable /nix/store path, and the
#   ISO filename inside it is chosen by Nix (config.image.baseName), not by
#   this script.  We therefore ask Nix for the derivation's real output path
#   instead of guessing filenames, and we never rely on `find` walking through
#   the symlink (find does not follow symlinks unless given -L / -H).
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

# Flake attribute that produces the ISO image
ISO_ATTR="${ISO_CONFIG:-nixosConfigurations.sovran_systemsos-iso}"

# Flake reference used for the build. "path:" (not a bare ".") so gitignored
# files under iso/secrets/ are included -- a bare "." ref only sees files
# tracked by git, so the enroll token / provisioner URL vanish from the ISO.
# The path is relative because the script already cd'd to the repo root and
# Nix cannot parse a flake ref whose path contains spaces.
REPO_FLAKE_REF="${REPO_FLAKE_REF:-path:.}"
ISO_BUILD_ATTR="${REPO_FLAKE_REF}#${ISO_ATTR}.config.system.build.isoImage"

DO_REBUILD=0
for arg in "$@"; do
    case "$arg" in
        --rebuild) DO_REBUILD=1 ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Sovran_SystemsOS CDN ISO Packaging & Upload Tool      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo -e "  Version : ${CYAN}${VERSION}${NC}"
echo -e "  ISO     : ${CYAN}${ISO_NAME}${NC}"
echo -e "  Repo    : ${CYAN}${REPO_ROOT}${NC}   (left untouched)"
echo -e "  Output  : ${CYAN}${OUT_DIR}${NC}   (outside the repo)"
echo -e "  Attr    : ${CYAN}${ISO_ATTR}${NC}"
echo -e "  Flake   : ${CYAN}${REPO_FLAKE_REF}${NC}"
echo

# ---------------------------------------------------------------------------
# Helper: locate a *.iso file inside a nix build output directory.
# Follows symlinks explicitly (-L) and ignores compressed variants unless
# nothing else is present.
# ---------------------------------------------------------------------------
find_iso_in() {
    local dir="$1"
    [ -d "$dir" ] || return 0
    local hit
    # Prefer the exact versioned name Nix uses for this release.
    if [ -f "$dir/iso/${ISO_NAME}" ]; then
        printf '%s\n' "$dir/iso/${ISO_NAME}"
        return 0
    fi
    hit=$(find -L "$dir" -maxdepth 3 -type f -name '*.iso' 2>/dev/null | sort | head -n 1 || true)
    if [ -z "$hit" ]; then
        hit=$(find -L "$dir" -maxdepth 3 -type f -name '*.iso.*' 2>/dev/null | sort | head -n 1 || true)
    fi
    printf '%s\n' "$hit"
}

SRC_ISO=""

# 1) Reuse an existing build ONLY if it is exactly the version we are packaging.
#    A result symlink left over from a previous release must not be packaged
#    under the new version number, so a name mismatch falls through to Nix.
if [ "$DO_REBUILD" -eq 0 ] && [ -f "$RESULT_LINK/iso/${ISO_NAME}" ]; then
    SRC_ISO="$RESULT_LINK/iso/${ISO_NAME}"
elif [ "$DO_REBUILD" -eq 0 ] && [ -d "$RESULT_LINK" ]; then
    STALE=$(find_iso_in "$RESULT_LINK")
    if [ -n "$STALE" ]; then
        echo -e "${YELLOW}Ignoring stale build: $(basename "$STALE") != ${ISO_NAME}${NC}"
        echo -e "  (result link points at a different release; re-resolving via Nix)"
    fi
fi

# 2) Ask Nix for the authoritative output path. This builds only if needed.
if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    echo -e "${YELLOW}Building via Nix (result link goes outside the repo)...${NC}"
    rm -f "$RESULT_LINK"

    if ! OUT_PATH=$(nix build "$ISO_BUILD_ATTR" --out-link "$RESULT_LINK" --print-out-paths); then
        echo -e "${RED}Error: nix build failed for ${ISO_BUILD_ATTR}.${NC}" >&2
        echo -e "  The 'evaluation warning' lines about services.avahi are not fatal," >&2
        echo -e "  but the real error is printed above them. Re-run with --show-trace" >&2
        echo -e "  for details:" >&2
        echo -e "    nix build '${ISO_BUILD_ATTR}' --show-trace -L" >&2
        echo -e "  Flake ref: ${REPO_FLAKE_REF}  (override with REPO_FLAKE_REF=...)" >&2
        exit 1
    fi
    SRC_ISO=$(find_iso_in "$OUT_PATH")
fi

# 3) Last resort: a legacy in-repo result symlink.
if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    SRC_ISO=$(find_iso_in "$REPO_ROOT/result")
fi

if [ -z "$SRC_ISO" ] || [ ! -f "$SRC_ISO" ]; then
    echo -e "${RED}Error: Failed to locate built ISO.${NC}" >&2
    echo -e "  Looked in: ${RESULT_LINK} and ${REPO_ROOT}/result" >&2
    echo -e "  Expected a file named ${ISO_NAME} produced by ${ISO_ATTR}." >&2
    echo -e "  Inspect the build output with:" >&2
    echo -e "    ls -l ${RESULT_LINK}/iso/" >&2
    exit 1
fi

if [ "$(basename "$SRC_ISO")" != "$ISO_NAME" ]; then
    echo -e "${RED}Error: resolved ISO is $(basename "$SRC_ISO"), but VERSION requires ${ISO_NAME}.${NC}" >&2
    echo -e "  Refusing to package a mismatched artifact. This usually means the" >&2
    echo -e "  result link or an in-repo ./result points at an older release." >&2
    echo -e "  Fix by rebuilding from a clean state:" >&2
    echo -e "    rm -f ${RESULT_LINK} ${REPO_ROOT}/result" >&2
    echo -e "    ./scripts/upload-cdn.sh --rebuild" >&2
    exit 1
fi

echo -e "${GREEN}Using ISO:${NC} $SRC_ISO"
echo

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
    case "$arg" in
        --upload) DO_UPLOAD=1 ;;
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
