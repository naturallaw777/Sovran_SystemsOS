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
    local exclude="${1:-}"
    if [[ -n "$exclude" ]]; then
        git tag --list 'v*' --sort=-version:refname | grep -v -x -E "v?${exclude#v}|${exclude}" | head -1 || echo ""
    else
        git tag --list 'v*' --sort=-version:refname | head -1 || echo ""
    fi
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
git fetch --all --tags 2>/dev/null || true

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
    read -rp "Enter release headline (or press Enter for default): " input_msg
    if [[ -n "$input_msg" ]]; then
        RELEASE_MESSAGE="$input_msg"
    else
        RELEASE_MESSAGE="Sovran_SystemsOS ${TAG} — Stable Release"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Generate categorized release notes from commit history
# Groups commits since the last tag into Keep-a-Changelog sections based on
# conventional-commit prefixes (feat/fix/docs/security/etc.) and keywords.
# ─────────────────────────────────────────────────────────────────────────────
generate_release_notes() {
    local range="$1"

    local added="" changed="" fixed="" security="" docs=""

    while IFS= read -r subject; do
        # Skip noise commits
        case "$subject" in
            "Initial plan"|"initial plan") continue ;;
            "Merge pull request"*|"Merge branch"*) continue ;;
            "chore: bump VERSION"*|"docs: update CHANGELOG"*) continue ;;
            "Address code review"*|"Address review"*|"Address validation"*) continue ;;
        esac

        # Strip conventional-commit prefix for display
        local clean
        clean="$(echo "$subject" | sed -E 's/^(feat|fix|docs|chore|refactor|test|security|perf|style|ci|build)(\([^)]*\))?!?:[[:space:]]*//')"
        # Capitalize first letter
        clean="$(echo "${clean:0:1}" | tr '[:lower:]' '[:upper:]')${clean:1}"

        case "$subject" in
            security:*|security\(*)         security+="- ${clean}"$'\n' ;;
            feat:*|feat\(*)                 added+="- ${clean}"$'\n' ;;
            fix:*|fix\(*|Fix\ *|fixed\ *)   fixed+="- ${clean}"$'\n' ;;
            docs:*|docs\(*)                 docs+="- ${clean}"$'\n' ;;
            refactor:*|refactor\(*|chore:*|chore\(*|removed\ *|Updated\ *|updated\ *) changed+="- ${clean}"$'\n' ;;
            test:*|test\(*)                 continue ;;
            *)                              added+="- ${clean}"$'\n' ;;
        esac
    done < <(git log --no-merges --format='%s' "$range" 2>/dev/null | awk '!seen[$0]++')

    local notes=""
    if [[ -n "$added" ]];    then notes+=$'### Added\n'"$added"$'\n'; fi
    if [[ -n "$changed" ]];  then notes+=$'### Changed\n'"$changed"$'\n'; fi
    if [[ -n "$fixed" ]];    then notes+=$'### Fixed\n'"$fixed"$'\n'; fi
    if [[ -n "$security" ]]; then notes+=$'### Security\n'"$security"$'\n'; fi
    if [[ -n "$docs" ]];     then notes+=$'### Documentation\n'"$docs"$'\n'; fi

    if [[ -z "$notes" ]]; then
        notes=$'### Changed\n- Incremental stable updates\n'
    fi

    printf '%s' "$notes"
}

# Build the notes from commits since the previous tag (exclude the target tag if already present)
PREV_TAG=$(get_latest_tag "$TAG")
if [[ -n "$PREV_TAG" ]] && git rev-parse -q --verify "$PREV_TAG" >/dev/null; then
    COMMIT_RANGE="${PREV_TAG}..HEAD"
else
    COMMIT_RANGE="HEAD"
fi

echo
echo -e "${BLUE}Generating draft release notes from ${COMMIT_RANGE}...${NC}"
RELEASE_NOTES="$(generate_release_notes "$COMMIT_RANGE")"

# Let the user review/edit the generated notes before publishing
NOTES_FILE="$(mktemp "/tmp/release-notes-${TAG}.XXXXXX.md")"
{
    echo "## Sovran_SystemsOS ${TAG}"
    echo
    echo "${RELEASE_MESSAGE}"
    echo
    echo "$RELEASE_NOTES"
    echo "**Full changelog:** [CHANGELOG.md](https://github.com/naturallaw777/Sovran_SystemsOS/blob/main/CHANGELOG.md)"
} > "$NOTES_FILE"

echo -e "  ${GREEN}✓${NC} Draft notes written to: ${CYAN}${NOTES_FILE}${NC}"
echo
echo "──────────────── Draft Release Notes ────────────────"
cat "$NOTES_FILE"
echo "──────────────────────────────────────────────────────"
echo
read -rp "Edit the notes before publishing? (y/N): " edit_confirm
if [[ "$edit_confirm" =~ ^[Yy]$ ]]; then
    "${EDITOR:-nano}" "$NOTES_FILE"
    RELEASE_NOTES="$(sed -n '/^###/,$p' "$NOTES_FILE" | sed '/^\*\*Full changelog/d')"
fi
RELEASE_BODY="$(cat "$NOTES_FILE")"

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
git tag -f -a "${TAG}" -m "${RELEASE_MESSAGE}

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

# Create new changelog entry from the generated notes (no placeholders)
NEW_ENTRY="## [${VERSION}] - ${TODAY}

${RELEASE_NOTES}
[${VERSION}]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/${TAG}
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
    title_suffix="${RELEASE_MESSAGE#Sovran_SystemsOS v* — }"
    title_suffix="${title_suffix#Sovran_SystemsOS * — }"
    if gh release create "${TAG}" \
        --repo naturallaw777/Sovran_SystemsOS \
        --title "${TAG} — ${title_suffix}" \
        --notes-file "${NOTES_FILE}"; then
        echo -e "  ${GREEN}✓${NC} GitHub release created successfully"
    else
        echo -e "  ${YELLOW}⚠${NC} GitHub release creation failed (check 'gh auth status' or create via web GUI)"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} gh CLI not found — skipping GitHub release (create via GitHub web GUI)"
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

    # Build JSON payload safely (release body may contain quotes/newlines)
    if command -v jq &>/dev/null; then
        PAYLOAD=$(jq -n \
            --arg tag "${TAG}" \
            --arg name "${TAG} — Stable Release" \
            --arg body "${RELEASE_BODY}" \
            '{tag_name: $tag, name: $name, body: $body, draft: false, prerelease: false}')
    else
        PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'tag_name': sys.argv[1], 'name': sys.argv[1] + ' — Stable Release', 'body': open(sys.argv[2]).read(), 'draft': False, 'prerelease': False}))" "${TAG}" "${NOTES_FILE}")
    fi

    RESPONSE=$(curl -s -X POST \
        -H "Authorization: token ${GITEA_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "${PAYLOAD}" \
        "${GITEA_API_URL}/repos/${GITEA_REPO}/releases" 2>/dev/null || echo "")

    if echo "$RESPONSE" | grep -q '"id"'; then
        echo -e "  ${GREEN}✓${NC} Gitea release created successfully"
    elif echo "$RESPONSE" | grep -q "write:repository"; then
        echo -e "  ${YELLOW}⚠${NC} Gitea token scope issue: your token requires the 'write:repository' scope (currently has write:package)."
        echo "     To fix: In Gitea, navigate to Settings → Applications → Manage Access Tokens and generate a token with 'write:repository'."
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
echo "  • Build the installer ISO:"
echo "    nix build .#nixosConfigurations.sovran_systemsos-iso.config.system.build.isoImage"
echo "  • Package, verify, and upload ISO to CDN:"
echo "    ./scripts/upload-cdn.sh --upload"
echo "  • Review and enhance the new section in CHANGELOG.md"
echo "  • Push changes: git push ${GITHUB_REMOTE} HEAD:main && git push ${GITEA_REMOTE} HEAD:staging-dev"
echo "  • Verify releases on both GitHub and Gitea"
echo
echo -e "${CYAN}Tag created: ${TAG}${NC}"
git show "${TAG}" --quiet

# Clean up temp notes file
rm -f "${NOTES_FILE}"
