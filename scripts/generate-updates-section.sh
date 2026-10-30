#!/usr/bin/env bash
#
# generate-updates-section.sh
# Derive a Keep-a-Changelog "### Changed" block from what flake.lock and
# versions.json actually say changed between two revisions.
#
# Why this exists
# ---------------
# Flake bumps are invisible to the release script. A commit called "updated
# nixpkgs" is one line in git log, but it can move Bitcoin Core, LND, electrs,
# Vaultwarden and a dozen other packages. And a commit called "updated flake
# inputs which includes Sparrow v2.5.6" reads like one package when it is
# usually three. Neither the commit scraper nor a hand-written [Unreleased]
# section reliably captures that, so the Bitcoin stack silently drops out of
# release notes.
#
# This script reads the lock files and the Hub's service version map directly,
# so the software list is derived rather than remembered.
#
# Usage
#   ./scripts/generate-updates-section.sh [--from REF] [--to REF] [--check] [--quiet]
#
#   --from REF   base revision      (default: latest release tag in refs/tags/ or
#                                    refs/release-tags/github/)
#   --to REF     revision to report (default: HEAD)
#   --check      exit 1 if any flake input or Hub service version moved; write
#                nothing. Use this in release preflight or CI.
#   --quiet      only print the generated section (no footer/notes)
#
# Everything is read from the git object store, so --from/--to need no checkout
# and the working tree is never touched.
#
set -uo pipefail

FROM=""
TO="HEAD"
CHECK=0
QUIET=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)  FROM="${2:-}"; shift 2 ;;
        --to)    TO="${2:-}";   shift 2 ;;
        --check) CHECK=1; shift ;;
        --quiet) QUIET=1; shift ;;
        -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

command -v jq >/dev/null 2>&1 || { echo "error: jq is required" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: not a git repository" >&2; exit 2; }

# ── Resolve the base revision ────────────────────────────────────────────────
if [[ -z "$FROM" ]]; then
    FROM=$(git for-each-ref --sort=-version:refname --format='%(refname)' \
            'refs/tags/v*' 'refs/release-tags/github/v*' 2>/dev/null | head -1)
    [[ -n "$FROM" ]] || { echo "error: no release tag found; pass --from REF" >&2; exit 2; }
fi

FROM_SHA=$(git rev-parse --verify -q "${FROM}^{commit}" 2>/dev/null) \
    || { echo "error: cannot resolve --from '$FROM'" >&2; exit 2; }
TO_SHA=$(git rev-parse --verify -q "${TO}^{commit}" 2>/dev/null) \
    || { echo "error: cannot resolve --to '$TO'" >&2; exit 2; }

FROM_LABEL=$(git describe --tags --exact-match "$FROM_SHA" 2>/dev/null || echo "$FROM")

# ── Helpers ──────────────────────────────────────────────────────────────────
# Read a file at a revision; empty string when absent.
read_at() {
    git show "${1}:${2}" 2>/dev/null || true
}

# Direct flake inputs, mapped to the lock node that holds their locked rev.
# Following root.inputs rather than listing node names is deliberate: the same
# nixpkgs revision appears as nixpkgs, nixpkgs_2, nixpkgs_3 and nixpkgs_4, and
# only the node a direct input points at is relevant to this system.
direct_inputs() {
    local lock="$1"
    printf '%s' "$lock" \
        | jq -r '.nodes.root.inputs // {} | to_entries[] | select(.value | type == "string") | .key' \
              2>/dev/null | sort
}

input_node() {
    printf '%s' "$1" | jq -r --arg i "$2" '.nodes.root.inputs[$i] // empty' 2>/dev/null
}

node_rev() {
    printf '%s' "$1" | jq -r --arg n "$2" '.nodes[$n].locked.rev // empty' 2>/dev/null
}

node_ref() {
    printf '%s' "$1" | jq -r --arg n "$2" '.nodes[$n].locked.ref // .nodes[$n].original.ref // empty' 2>/dev/null
}

VERSIONS_JSON="app/sovran_systemsos_web/versions.json"

LOCK_FROM=$(read_at "$FROM_SHA" flake.lock)
LOCK_TO=$(read_at "$TO_SHA" flake.lock)
VER_FROM=$(read_at "$FROM_SHA" "$VERSIONS_JSON")
VER_TO=$(read_at "$TO_SHA" "$VERSIONS_JSON")

MOVED=0
BODY=""

# ── Flake inputs ─────────────────────────────────────────────────────────────
INPUT_LINES=""
while IFS= read -r input; do
    [[ -n "$input" ]] || continue
    node=$(input_node "$LOCK_TO" "$input")
    [[ -n "$node" ]] || continue
    rev_old=$(node_rev "$LOCK_FROM" "$node")
    rev_new=$(node_rev "$LOCK_TO" "$node")
    [[ "$rev_old" != "$rev_new" ]] || continue
    MOVED=1
    ref=$(node_ref "$LOCK_TO" "$node")
    if [[ -n "$ref" ]]; then
        INPUT_LINES+="- **${input}** (\`${ref}\`): \`${rev_old:0:10}\` → \`${rev_new:0:10}\`"$'\n'
    else
        INPUT_LINES+="- **${input}**: \`${rev_old:0:10}\` → \`${rev_new:0:10}\`"$'\n'
    fi
done < <(direct_inputs "$LOCK_TO")

# ── Hub service versions ────────────────────────────────────────────────────
SERVICE_LINES=""
if [[ -n "$VER_TO" ]] && printf '%s' "$VER_TO" | jq -e . >/dev/null 2>&1; then
    while IFS=$'\t' read -r svc old new; do
        [[ -n "$svc" ]] || continue
        [[ "$old" != "$new" ]] || continue
        MOVED=1
        SERVICE_LINES+="- **${svc%%.service}** \`${old:-—}\` → \`${new}\`"$'\n'
    done < <(jq -rn \
        --argjson old "$( [[ -n "$VER_FROM" ]] && printf '%s' "$VER_FROM" || echo '{}' )" \
        --argjson new "$VER_TO" \
        '($old + $new) | keys[] | . as $k
         | [$k, ($old[$k] // "—"), ($new[$k] // "—")] | @tsv')
fi

# ── Check mode ──────────────────────────────────────────────────────────────
if [[ "$CHECK" -eq 1 ]]; then
    if [[ "$MOVED" -eq 1 ]]; then
        echo "Pinned software moved between ${FROM_LABEL} and ${TO}:" >&2
        [[ -n "$INPUT_LINES" ]]   && printf '%s' "$INPUT_LINES" >&2
        [[ -n "$SERVICE_LINES" ]] && printf '%s' "$SERVICE_LINES" >&2
        exit 1
    fi
    exit 0
fi

# ── Output ──────────────────────────────────────────────────────────────────
if [[ -n "$INPUT_LINES" || -n "$SERVICE_LINES" ]]; then
    BODY=$'### Changed\n'
    [[ -n "$INPUT_LINES" ]]   && BODY+=$'\n#### Flake inputs\n'"$INPUT_LINES"
    [[ -n "$SERVICE_LINES" ]] && BODY+=$'\n#### Service versions\n'"$SERVICE_LINES"
fi

if [[ "$QUIET" -eq 1 ]]; then
    [[ -n "$BODY" ]] && printf '%s' "$BODY"
    exit 0
fi

if [[ -z "$BODY" ]]; then
    echo "No pinned software moved between ${FROM_LABEL} and ${TO}."
    exit 0
fi

printf '%s\n' "$BODY"
cat >&2 <<EOF

────────────────────────────────────────────────────────────────────────────
Paste the block above into "## [Unreleased]" in CHANGELOG.md, then replace
the revision hashes with real version numbers for anything user-facing.

Resolve them without a nix build:

  # Ride The Lightning / Mempool / sovran-nwc versions at the pinned rev
  git -C ../Sovran_Bitcoin show <rev>:packages/rtl/default.nix | grep version
  git -C ../Sovran_Bitcoin show <rev>:packages/mempool/default.nix | grep version

  # Or from inside the flake, which evaluates the real packages
  nix eval --raw .#nixosConfigurations.nixos.pkgs.sovran-bitcoin.rtl.version
  nix eval --raw .#nixosConfigurations.nixos.pkgs.sovran-bitcoin.mempool-backend.version
  nix eval --raw .#nixosConfigurations.nixos.pkgs.btc-clients.sparrow.version

The Hub's service map (${VERSIONS_JSON}) already carries definitive versions for
everything the Hub reports, so prefer it where an entry exists.
────────────────────────────────────────────────────────────────────────────
EOF
