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

# Always operate from the repository root, regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

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
# GitHub release tags are fetched into a private namespace instead of
# refs/tags/. GitHub and Gitea contain some same-named historical tags that
# point to different objects; sharing refs/tags/ would make either fetch fail
# with "would clobber existing tag".
GITHUB_TAG_NAMESPACE="refs/release-tags/github"

get_latest_tag() {
    local exclude="${1:-}"
    local tag

    while IFS= read -r tag; do
        if [[ -n "$exclude" && "$tag" == "v${exclude#v}" ]]; then
            continue
        fi
        printf '%s\n' "$tag"
        return 0
    done < <(git for-each-ref \
        --sort=-version:refname \
        --format='%(refname:strip=3)' \
        "${GITHUB_TAG_NAMESPACE}/v*")

    return 0
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
# Step 0: Preflight and fetch everything
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}Step 0: Running release preflight...${NC}"

# A release must start from an exact, committed, reproducible tree. This also
# prevents release metadata generated below from being mixed with local work.
if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${RED}Error: the working tree is not clean. Commit, stash, or remove local changes first.${NC}" >&2
    git status --short >&2
    exit 1
fi

for remote in "$GITHUB_REMOTE" "$GITEA_REMOTE"; do
    if ! git remote | grep -q -x "$remote"; then
        echo -e "${RED}Error: required remote '$remote' is not configured.${NC}" >&2
        exit 1
    fi
done

for command_name in gh curl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo -e "${RED}Error: required command '$command_name' is not installed.${NC}" >&2
        exit 1
    fi
done
if ! gh auth status >/dev/null 2>&1; then
    echo -e "${RED}Error: GitHub CLI is not authenticated. Run 'gh auth login' first.${NC}" >&2
    exit 1
fi
if [[ -z "${GITEA_TOKEN:-}" ]]; then
    echo
    read -rsp "Enter your Gitea API token (input hidden): " GITEA_TOKEN
    echo
fi
if [[ -z "${GITEA_TOKEN:-}" ]]; then
    echo -e "${RED}Error: a GITEA_TOKEN with write:repository scope is required.${NC}" >&2
    exit 1
fi

echo -e "  Fetching GitHub (${GITHUB_REMOTE}) and Gitea (${GITEA_REMOTE})..."
# Never fetch either host's tags into refs/tags/. Historical tags with the same
# name differ between the hosts, and Git correctly refuses to clobber them.
git fetch "$GITHUB_REMOTE" --prune --no-tags
git fetch "$GITEA_REMOTE" --prune --no-tags
git fetch "$GITHUB_REMOTE" --prune --no-tags \
    "+refs/tags/*:${GITHUB_TAG_NAMESPACE}/*"

GITHUB_MAIN_REF="refs/remotes/${GITHUB_REMOTE}/main"
GITEA_STAGING_REF="refs/remotes/${GITEA_REMOTE}/staging-dev"

if ! git rev-parse --verify "$GITHUB_MAIN_REF" >/dev/null 2>&1; then
    echo -e "${RED}Error: cannot resolve GitHub main at ${GITHUB_MAIN_REF}.${NC}" >&2
    exit 1
fi
if ! git rev-parse --verify "$GITEA_STAGING_REF" >/dev/null 2>&1; then
    echo -e "${RED}Error: cannot resolve Gitea staging-dev at ${GITEA_STAGING_REF}.${NC}" >&2
    exit 1
fi

HEAD_COMMIT=$(git rev-parse HEAD)
GITHUB_MAIN_COMMIT=$(git rev-parse "$GITHUB_MAIN_REF")
GITEA_STAGING_COMMIT=$(git rev-parse "$GITEA_STAGING_REF")

if [[ "$GITHUB_MAIN_COMMIT" != "$GITEA_STAGING_COMMIT" ]]; then
    echo -e "${RED}Error: GitHub main and Gitea staging-dev are not synchronized.${NC}" >&2
    echo "  GitHub main       : $GITHUB_MAIN_COMMIT" >&2
    echo "  Gitea staging-dev : $GITEA_STAGING_COMMIT" >&2
    exit 1
fi
if [[ "$HEAD_COMMIT" != "$GITHUB_MAIN_COMMIT" ]]; then
    echo -e "${RED}Error: local HEAD is not the synchronized release candidate.${NC}" >&2
    echo "  Local HEAD  : $HEAD_COMMIT" >&2
    echo "  Remote HEAD : $GITHUB_MAIN_COMMIT" >&2
    echo "Update/check out the synchronized commit, then run the script again." >&2
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Clean tree; GitHub main and Gitea staging-dev match local HEAD"

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

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Error: version must use MAJOR.MINOR.PATCH format (for example, 1.1.1).${NC}" >&2
    exit 1
fi
remote_has_tag() {
    local remote="$1"
    [[ -n "$(git ls-remote --tags "$remote" "refs/tags/${TAG}" "refs/tags/${TAG}^{}")" ]]
}

if git show-ref --verify --quiet "refs/tags/${TAG}" || \
   git show-ref --verify --quiet "${GITHUB_TAG_NAMESPACE}/${TAG}" || \
   remote_has_tag "$GITHUB_REMOTE" || remote_has_tag "$GITEA_REMOTE"; then
    echo -e "${RED}Error: tag ${TAG} already exists locally or on a remote.${NC}" >&2
    echo "Refusing to move or overwrite an existing release tag." >&2
    exit 1
fi

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

# Build notes from the previous canonical GitHub tag. Use its private ref so a
# conflicting local or Gitea tag with the same name cannot select the wrong
# commit.
PREV_TAG=$(get_latest_tag "$TAG")
PREV_TAG_REF="${GITHUB_TAG_NAMESPACE}/${PREV_TAG}"
if [[ -n "$PREV_TAG" ]] && git rev-parse -q --verify "$PREV_TAG_REF" >/dev/null; then
    COMMIT_RANGE="${PREV_TAG_REF}..HEAD"
    COMMIT_RANGE_DISPLAY="${PREV_TAG}..HEAD"
else
    COMMIT_RANGE="HEAD"
    COMMIT_RANGE_DISPLAY="HEAD"
fi

echo
echo -e "${BLUE}Generating draft release notes from ${COMMIT_RANGE_DISPLAY}...${NC}"
RELEASE_NOTES="$(generate_release_notes "$COMMIT_RANGE")"

# Let the user review/edit the generated notes before publishing
NOTES_FILE="$(mktemp "/tmp/release-notes-${TAG}.XXXXXX.md")"
trap 'rm -f "$NOTES_FILE"' EXIT
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
# Step 1: Prepare and commit all release metadata
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 1: Preparing release metadata for ${TAG}...${NC}"

# VERSION drives ISO naming.
echo "${VERSION}" > VERSION

# Update every versioned ISO filename in README.md.
README_FILE="README.md"
if [[ ! -f "$README_FILE" ]]; then
    echo -e "${RED}Error: ${README_FILE} not found.${NC}" >&2
    exit 1
fi
OLD_ISO_VER=$(grep -oE 'Sovran_SystemsOS-[0-9]+\.[0-9]+\.[0-9]+\.iso' "$README_FILE" \
    | head -1 | sed 's/Sovran_SystemsOS-//; s/\.iso//')
if [[ -z "$OLD_ISO_VER" ]]; then
    echo -e "${RED}Error: no versioned ISO reference found in ${README_FILE}.${NC}" >&2
    exit 1
fi
if [[ "$OLD_ISO_VER" != "$VERSION" ]]; then
    sed "s/Sovran_SystemsOS-${OLD_ISO_VER}/Sovran_SystemsOS-${VERSION}/g" \
        "$README_FILE" > "$README_FILE.tmp"
    mv "$README_FILE.tmp" "$README_FILE"
fi

# Add the changelog entry before tagging so the tag and stable branch contain it.
TODAY=$(date +%Y-%m-%d)
NEW_ENTRY="## [${VERSION}] - ${TODAY}

${RELEASE_NOTES}
[${VERSION}]: https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/releases/tag/${TAG}
"

if [[ ! -f "$CHANGELOG_FILE" ]]; then
    echo -e "${RED}Error: ${CHANGELOG_FILE} not found.${NC}" >&2
    exit 1
fi
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
    END { if (!printed) exit 2 }
' "$CHANGELOG_FILE" > "${CHANGELOG_FILE}.tmp" || {
    rm -f "${CHANGELOG_FILE}.tmp"
    echo -e "${RED}Error: could not find the changelog insertion marker.${NC}" >&2
    exit 1
}
mv "${CHANGELOG_FILE}.tmp" "$CHANGELOG_FILE"

git add VERSION "$README_FILE" "$CHANGELOG_FILE"
if git diff --cached --quiet; then
    echo -e "${RED}Error: release preparation produced no changes.${NC}" >&2
    exit 1
fi
git commit -m "chore(release): prepare ${TAG}"
RELEASE_COMMIT=$(git rev-parse HEAD)

echo -e "  ${GREEN}✓${NC} VERSION, README, and CHANGELOG committed"
echo -e "  Release commit: ${CYAN}${RELEASE_COMMIT}${NC}"

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Publish the final release commit to every release branch
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 2: Publishing the final release commit...${NC}"

# GitHub main and Gitea staging-dev were verified equal during preflight, so
# these are normal fast-forward pushes. Stable is an intentional promotion and
# uses a lease to prevent overwriting a branch changed since the fetch.
git push "$GITHUB_REMOTE" HEAD:main
git push "$GITEA_REMOTE" HEAD:staging-dev
git push "$GITEA_REMOTE" HEAD:stable --force-with-lease

# Verify all three branch tips before creating an immutable release tag.
remote_branch_commit() {
    local remote="$1"
    local branch="$2"
    git ls-remote "$remote" "refs/heads/${branch}" | awk 'NR == 1 { print $1 }'
}

PUBLISHED_GITHUB=$(remote_branch_commit "$GITHUB_REMOTE" main)
PUBLISHED_STAGING=$(remote_branch_commit "$GITEA_REMOTE" staging-dev)
PUBLISHED_STABLE=$(remote_branch_commit "$GITEA_REMOTE" stable)
if [[ "$PUBLISHED_GITHUB" != "$RELEASE_COMMIT" || \
      "$PUBLISHED_STAGING" != "$RELEASE_COMMIT" || \
      "$PUBLISHED_STABLE" != "$RELEASE_COMMIT" ]]; then
    echo -e "${RED}Error: post-push verification failed; no release tag was created.${NC}" >&2
    echo "  Expected          : $RELEASE_COMMIT" >&2
    echo "  GitHub main       : ${PUBLISHED_GITHUB:-missing}" >&2
    echo "  Gitea staging-dev : ${PUBLISHED_STAGING:-missing}" >&2
    echo "  Gitea stable      : ${PUBLISHED_STABLE:-missing}" >&2
    exit 1
fi
echo -e "  ${GREEN}✓${NC} GitHub main, Gitea staging-dev, and Gitea stable all match"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Tag the final release commit and publish the tag
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 3: Creating annotated tag ${TAG} on ${RELEASE_COMMIT}...${NC}"
git tag -a "$TAG" -m "${RELEASE_MESSAGE}

- Stable release of Sovran_SystemsOS
- See CHANGELOG.md for full details" "$RELEASE_COMMIT"

git push "$GITHUB_REMOTE" "$TAG"
git push "$GITEA_REMOTE" "$TAG"

# For an annotated tag, ^{} resolves the commit referenced by the tag object.
remote_tag_commit() {
    local remote="$1"
    git ls-remote "$remote" "refs/tags/${TAG}^{}" | awk 'NR == 1 { print $1 }'
}
GITHUB_TAG_COMMIT=$(remote_tag_commit "$GITHUB_REMOTE")
GITEA_TAG_COMMIT=$(remote_tag_commit "$GITEA_REMOTE")
if [[ "$GITHUB_TAG_COMMIT" != "$RELEASE_COMMIT" || "$GITEA_TAG_COMMIT" != "$RELEASE_COMMIT" ]]; then
    echo -e "${RED}Error: published tag verification failed.${NC}" >&2
    exit 1
fi
echo -e "  ${GREEN}✓${NC} ${TAG} points to the final release commit on GitHub and Gitea"

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Create GitHub release via gh CLI
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 4: Creating GitHub release...${NC}"

title_suffix="${RELEASE_MESSAGE#Sovran_SystemsOS v* — }"
title_suffix="${title_suffix#Sovran_SystemsOS * — }"
gh release create "$TAG" \
    --repo naturallaw777/Sovran_SystemsOS \
    --title "${TAG} — ${title_suffix}" \
    --notes-file "$NOTES_FILE"
echo -e "  ${GREEN}✓${NC} GitHub release created successfully"

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create Gitea release via API
# ─────────────────────────────────────────────────────────────────────────────
echo
echo -e "${BLUE}Step 5: Creating Gitea release via API...${NC}"

GITEA_REPO="Sovran_Systems/Sovran_SystemsOS"

# Build JSON safely because release notes may contain quotes and newlines.
if command -v jq >/dev/null 2>&1; then
    PAYLOAD=$(jq -n \
        --arg tag "$TAG" \
        --arg name "$TAG — Stable Release" \
        --arg body "$RELEASE_BODY" \
        '{tag_name: $tag, name: $name, body: $body, draft: false, prerelease: false}')
else
    PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'tag_name': sys.argv[1], 'name': sys.argv[1] + ' — Stable Release', 'body': open(sys.argv[2]).read(), 'draft': False, 'prerelease': False}))" "$TAG" "$NOTES_FILE")
fi

RESPONSE_FILE=$(mktemp "/tmp/gitea-release-${TAG}.XXXXXX.json")
HTTP_STATUS=$(curl -sS -o "$RESPONSE_FILE" -w '%{http_code}' -X POST \
    -H "Authorization: token ${GITEA_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "${GITEA_API_URL}/repos/${GITEA_REPO}/releases")

if [[ "$HTTP_STATUS" != "201" ]]; then
    echo -e "${RED}Error: Gitea release creation failed (HTTP ${HTTP_STATUS}).${NC}" >&2
    cat "$RESPONSE_FILE" >&2
    rm -f "$RESPONSE_FILE"
    exit 1
fi
rm -f "$RESPONSE_FILE"
echo -e "  ${GREEN}✓${NC} Gitea release created successfully"

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
echo "  • Verify the ISO download and checksum from the public CDN"
echo "  • Verify releases on both GitHub and Gitea"
echo
echo -e "${CYAN}Tag created: ${TAG}${NC}"
git show "${TAG}" --quiet

# Clean up temp notes file
rm -f "${NOTES_FILE}"
