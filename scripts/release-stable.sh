#!/usr/bin/env bash
#
# release-stable.sh
# Automated stable release script for Sovran_SystemsOS
#
# Features:
# - Detects latest tag and suggests next version
# - Pushes main → stable on Gitea
# - Creates annotated tag
# - Auto-updates CHANGELOG.md
# - Creates releases on both GitHub and Gitea via API
#
# Usage:
#   ./scripts/release-stable.sh [version] [--message "text"]
#
# Requirements:
#   - gh CLI (for GitHub releases)
#   - GITEA_TOKEN env var (for Gitea releases)
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
GITEA_REMOTE_DEFAULT="gitea"
GITHUB_REMOTE_DEFAULT="origin"
GITEA_API_URL="https://git.sovransystems.com/api/v1"
CHANGELOG_FILE="CHANGELOG.md"

# Auto-detect remotes
detect_remote() {
    local preferred="$1"
    local keyword="$2"
    if git remote | grep -q -x "$preferred"; then
        echo "$preferred"
        return
    fi
    local found
    found=$(git remote -v | grep -i "$keyword" | head -n 1 | awk '{print $1}')
    if [[ -n "$found" ]]; then
        echo "$found"
        return
    fi
    echo "$preferred"
}

GITEA_REMOTE=$(detect_remote "$GITEA_REMOTE_DEFAULT" "sovransystems\|gitea")
GITHUB_REMOTE=$(detect_remote "$GITHUB_REMOTE_DEFAULT" "github")

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Sovran_SystemsOS Automated Stable Release Script       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Get latest tag
# ─────────────────────────────────────────────────────────────────────────────
get_latest_tag() {
    git tag --list 'v*' --sort=-version:refname | head -1 || echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Suggest next version (patch bump)
# ─────────────────────────────────────────────────────────────────────────────
suggest_next_version() {
    local current="$1"
    if [[ -z "$current" ]]; then
        echo "1.0.0"
        return
    fi

    # Remove 'v' prefix
    local ver="${current#v}"
    IFS='.' read -r major minor patch <<< "$ver"

    # Default: bump patch
    echo "${major}.$((minor)).$((patch + 1))"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 0: Fetch everything
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}Step 0: Fetching latest from all remotes...${NC}"
git fetch --all --tags --prune --force || git fetch --all --tags --prune --force 2>/dev/null || true

LATEST_TAG=$(get_latest_tag)
NEXT_VERSION=$(suggest_next_version "$LATEST_TAG")

echo -e "  Latest tag   : ${CYAN}${LATEST_TAG:-none}${NC}"
echo -e "  Suggested    : ${GREEN}v${NEXT_VERSION}${NC}"
echo

# ─────────────────────────────────────────────────────────────────────────────
# Get version from user or argument
# ─────────────────────────────────────────────────────────────────────────────
if [ $# -ge 1 ] && [[ "$1" != --* ]]; then
    VERSION="$1"
    shift
else
    read -rp "Enter version to release (default: ${NEXT_VERSION}): " input_version
    VERSION="${input_version:-$NEXT_VERSION}"
fi

# Strip 'v' if user added it
VERSION="${VERSION#v}"
TAG="v${VERSION}"

# ─────────────────────────────────────────────────────────────────────────────
# Get release message
# ─────────────────────────────────────────────────────────────────────────────
RELEASE_MESSAGE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --message|-m)
            RELEASE_MESSAGE="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ -z "$RELEASE_MESSAGE" ]]; then
    echo
    read -rp "Enter release message (or press Enter for default): " input_msg
    if [[ -n "$input_msg" ]]; then
        RELEASE_MESSAGE="$input_msg"
    else
        RELEASE_MESSAGE="Sovran_SystemsOS ${TAG} — Stable Release"
    fi
fi

echo
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Preparing Release${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
echo "  Version       : ${TAG}"
echo "  Message       : ${RELEASE_MESSAGE}"
echo "  Gitea Remote  : ${GITEA_REMOTE}"
echo "  GitHub Remote : ${GITHUB_REMOTE}"
echo

read -rp "Proceed with this release? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Push tested code to Gitea (stable & staging-dev)
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 1: Pushing tested code to Gitea (stable & staging-dev)...${NC}"
if git remote | grep -q -x "${GITEA_REMOTE}"; then
    git push "${GITEA_REMOTE}" HEAD:stable --force-with-lease || echo -e "  ${YELLOW}⚠ Push to ${GITEA_REMOTE} (stable) failed.${NC}"
    git push "${GITEA_REMOTE}" HEAD:staging-dev --force-with-lease || echo -e "  ${YELLOW}⚠ Push to ${GITEA_REMOTE} (staging-dev) failed.${NC}"
else
    echo -e "  ${YELLOW}⚠ Remote '${GITEA_REMOTE}' not found in git — skipping Gitea push.${NC}"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Create annotated tag
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 2: Creating annotated tag ${TAG}...${NC}"
git tag -a "${TAG}" -m "${RELEASE_MESSAGE}

- Stable release of Sovran_SystemsOS
- See CHANGELOG.md for full details" || true

if git remote | grep -q -x "${GITEA_REMOTE}"; then
    git push "${GITEA_REMOTE}" "${TAG}" || echo -e "  ${YELLOW}⚠ Tag push to ${GITEA_REMOTE} failed.${NC}"
else
    echo -e "  ${YELLOW}⚠ Remote '${GITEA_REMOTE}' not found in git — skipping Gitea tag push.${NC}"
fi

if git remote | grep -q -x "${GITHUB_REMOTE}"; then
    git push "${GITHUB_REMOTE}" "${TAG}" || echo -e "  ${YELLOW}⚠ Tag push to ${GITHUB_REMOTE} failed.${NC}"
fi

# Update VERSION file for ISO builds
echo "${VERSION}" > VERSION
git add VERSION
git commit -m "chore: bump VERSION to ${TAG} for ISO naming" || true
echo -e "  ${GREEN}✓${NC} VERSION file updated to ${VERSION}"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Auto-update CHANGELOG.md
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 3: Updating ${CHANGELOG_FILE}...${NC}"

TODAY=$(date +%Y-%m-%d)

# Create new changelog entry
NEW_ENTRY="## [${VERSION}] - ${TODAY}

### Added
- (Add new features here)

### Changed
- (Add changes here)

### Fixed
- (Add bug fixes here)

[${VERSION}]: ${GITEA_API_URL%/*}/Sovran_Systems/Sovran_SystemsOS/releases/tag/${TAG}
"

# Prepend to changelog (after the header)
if [ -f "$CHANGELOG_FILE" ]; then
    # Backup
    cp "$CHANGELOG_FILE" "${CHANGELOG_FILE}.bak"

    # Insert new section after the first --- line
    awk -v new_entry="$NEW_ENTRY" '
        BEGIN { printed=0 }
        /^---$/ && !printed {
            print
            print ""
            print new_entry
            printed=1
            next
        }
        { print }
    ' "$CHANGELOG_FILE" > "${CHANGELOG_FILE}.tmp" && mv "${CHANGELOG_FILE}.tmp" "$CHANGELOG_FILE"
    rm -f "${CHANGELOG_FILE}.bak"

    echo -e "  ${GREEN}✓${NC} CHANGELOG.md updated with new section for ${TAG}"
else
    echo -e "  ${YELLOW}⚠${NC} CHANGELOG.md not found — skipping"
fi

# Commit the changelog update
git add "$CHANGELOG_FILE"
if git diff --cached --quiet; then
    echo "  (No changes to commit in changelog)"
else
    git commit -m "docs: update CHANGELOG.md for ${TAG}"
    echo -e "  ${GREEN}✓${NC} Committed changelog update"

    # Ask if user wants to push
    echo
    read -rp "Push the changelog commit to GitHub (main) and Gitea (staging-dev) now? (y/N): " push_confirm
    if [[ "$push_confirm" =~ ^[Yy]$ ]]; then
        if git remote | grep -q -x "${GITHUB_REMOTE}"; then
            echo -e "${BLUE}Pushing changelog commit to GitHub main...${NC}"
            if git push "${GITHUB_REMOTE}" HEAD:main; then
                echo -e "  ${GREEN}✓${NC} Changelog pushed to GitHub main (${GITHUB_REMOTE})"
            else
                echo -e "  ${YELLOW}⚠ Push to GitHub main failed — verify credentials or remote name.${NC}"
            fi
        fi
        if git remote | grep -q -x "${GITEA_REMOTE}"; then
            echo -e "${BLUE}Pushing changelog commit to Gitea staging-dev...${NC}"
            if git push "${GITEA_REMOTE}" HEAD:staging-dev; then
                echo -e "  ${GREEN}✓${NC} Changelog pushed to Gitea staging-dev (${GITEA_REMOTE})"
            else
                echo -e "  ${YELLOW}⚠ Push to Gitea staging-dev failed.${NC}"
            fi
        fi
    else
        echo "  (Changelog commit left local — remember to push later)"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Create GitHub Release via gh CLI
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 4: Creating GitHub Release...${NC}"

if command -v gh &>/dev/null; then
    if gh release create "${TAG}" \
        --repo naturallaw777/Sovran_SystemsOS \
        --title "${TAG}" \
        --notes "${RELEASE_MESSAGE}" \
        --target main 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} GitHub release created successfully"
    else
        echo -e "  ${YELLOW}⚠${NC} GitHub release may already exist or failed"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} gh CLI not found — skipping GitHub release"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create Gitea Release via API
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 5: Creating Gitea Release via API...${NC}"

# ── Gitea Token Handling ─────────────────────────────────────────────────────
if [[ -z "${GITEA_TOKEN:-}" ]]; then
    echo
    echo -e "${YELLOW}GITEA_TOKEN is not set.${NC}"
    read -rsp "Enter your Gitea API token (input will be hidden): " GITEA_TOKEN
    echo
    if [[ -z "$GITEA_TOKEN" ]]; then
        echo -e "  ${YELLOW}⚠${NC} No token provided — skipping Gitea release"
        GITEA_TOKEN=""
    fi
fi

if [[ -n "${GITEA_TOKEN:-}" ]]; then
    GITEA_REPO="Sovran_Systems/Sovran_SystemsOS"

    RESPONSE=$(curl -s -X POST \
        -H "Authorization: token ${GITEA_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{
            \"tag_name\": \"${TAG}\",
            \"name\": \"${TAG}\",
            \"body\": \"${RELEASE_MESSAGE}\",
            \"draft\": false,
            \"prerelease\": false
        }" \
        "${GITEA_API_URL}/repos/${GITEA_REPO}/releases" 2>/dev/null || echo "")

    if echo "$RESPONSE" | grep -q '"id"'; then
        echo -e "  ${GREEN}✓${NC} Gitea release created successfully"
    else
        echo -e "  ${YELLOW}⚠${NC} Gitea release creation failed or already exists"
        echo "     Response: $RESPONSE"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Final Summary
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ Release ${TAG} completed successfully!          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo
echo "Next manual steps (recommended):"
echo "  • Review and enhance the new section in CHANGELOG.md"
echo "  • Push changes: git push ${GITHUB_REMOTE} HEAD:main && git push ${GITEA_REMOTE} HEAD:staging-dev"
echo "  • Verify releases on both GitHub and Gitea"
echo
echo -e "${CYAN}Tag created: ${TAG}${NC}"
git show "${TAG}" --quiet
