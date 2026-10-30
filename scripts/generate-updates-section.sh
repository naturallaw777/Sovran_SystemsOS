#!/usr/bin/env bash
#
# generate-updates-section.sh
# Report what software actually changed between two revisions, by version.
#
# Reads flake.lock to see which inputs moved, then resolves the versions of the
# packages those inputs provide -- from the local git object store when the
# input is a repo this checkout can reach (sovran-bitcoin, btc-clients), or
# from GitHub raw for the nixpkgs inputs.
#
# Output is release-note prose, not revision hashes:
#
#   ### Changed
#   - **Sparrow Wallet** 2.5.5 → 2.5.6
#   - **Ride The Lightning** 0.15.13 → 0.15.16
#   - **Matrix Synapse** 1.163.0 → 1.163.2
#
# Usage
#   ./scripts/generate-updates-section.sh [--from REF] [--to REF] [--all] [--quiet]
#
#   --from REF   base revision   (default: latest release tag)
#   --to REF     revision        (default: HEAD)
#   --all        also list packages that did not change
#   --quiet      print only the section
#
set -uo pipefail

FROM=""; TO="HEAD"; SHOW_ALL=0; QUIET=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)  FROM="${2:-}"; shift 2 ;;
        --to)    TO="${2:-}";   shift 2 ;;
        --all)   SHOW_ALL=1; shift ;;
        --quiet) QUIET=1; shift ;;
        -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: not a git repo" >&2; exit 2; }

if [[ -z "$FROM" ]]; then
    FROM=$(git for-each-ref --sort=-version:refname --format='%(refname)' \
            'refs/tags/v*' 'refs/release-tags/github/v*' 2>/dev/null | head -1)
    [[ -n "$FROM" ]] || { echo "error: no release tag; pass --from" >&2; exit 2; }
fi
FROM_SHA=$(git rev-parse --verify -q "${FROM}^{commit}") || { echo "error: bad --from '$FROM'" >&2; exit 2; }
TO_SHA=$(git rev-parse --verify -q "${TO}^{commit}")     || { echo "error: bad --to '$TO'" >&2; exit 2; }

read_at() { git show "${1}:${2}" 2>/dev/null || true; }
LOCK_FROM=$(read_at "$FROM_SHA" flake.lock)
LOCK_TO=$(read_at "$TO_SHA" flake.lock)

input_node() { printf '%s' "$1" | jq -r --arg i "$2" '.nodes.root.inputs[$i] // empty' 2>/dev/null; }
node_rev()   { printf '%s' "$1" | jq -r --arg n "$2" '.nodes[$n].locked.rev // empty' 2>/dev/null; }

moved() {  # moved INPUT -> 0 if the input's locked rev differs
    local node; node=$(input_node "$LOCK_TO" "$1")
    [[ -n "$node" ]] || return 1
    [[ "$(node_rev "$LOCK_FROM" "$node")" != "$(node_rev "$LOCK_TO" "$node")" ]]
}

# ── version lookups ─────────────────────────────────────────────────────────
# Strip a nixpkgs-input version out of package.nix, at a given rev.
nix_ver() {  # nix_ver NIXPKGS_REV BY-NAME-PATH
    curl -sSL --max-time 20 \
        "https://raw.githubusercontent.com/NixOS/nixpkgs/$1/pkgs/by-name/$2/package.nix" \
        2>/dev/null | grep -oE '^[[:space:]]+version = "[^"]+"' | head -1 \
        | sed 's/.*= "//; s/"$//'
}

# Read a vendored package version out of the locked input's git history.
# Falls back to GitHub raw when the object is not in this clone.
dep_ver() {  # dep_ver LOCK_INPUT LOCKED_REV REPO PATH
    local input="$1" rev="$2" repo="$3" path="$4" v=""

    # 1. try the object store of an already-cloned sibling checkout
    local guess
    for guess in "../$input" "../$(basename "$repo" .git)"; do
        if [[ -d "$guess/.git" ]] && git -C "$guess" cat-file -e "${rev}:${path}" 2>/dev/null; then
            v=$(git -C "$guess" show "${rev}:${path}" 2>/dev/null \
                | grep -oE '^[[:space:]]+version = "[^"]+"' | head -1 | sed 's/.*= "//; s/"$//')
            [[ -n "$v" ]] && { printf '%s' "$v"; return; }
        fi
    done

    # 2. fall back to GitHub raw
    curl -sSL --max-time 20 "https://raw.githubusercontent.com/${repo}/${rev}/${path}" \
        2>/dev/null | grep -oE '^[[:space:]]+version = "[^"]+"' | head -1 \
        | sed 's/.*= "//; s/"$//'
}

nixpkgs_new=$(input_node "$LOCK_TO" nixpkgs)
nixpkgs_old=$(input_node "$LOCK_FROM" nixpkgs)
NP_OLD_REV=$(node_rev "$LOCK_FROM" "$nixpkgs_old")
NP_NEW_REV=$(node_rev "$LOCK_TO"   "$nixpkgs_new")

SB_NEW_REV=$(node_rev "$LOCK_TO" "$(input_node "$LOCK_TO" sovran-bitcoin)")
SB_OLD_REV=$(node_rev "$LOCK_FROM" "$(input_node "$LOCK_FROM" sovran-bitcoin)")
BC_NEW_REV=$(node_rev "$LOCK_TO" "$(input_node "$LOCK_TO" btc-clients)")
BC_OLD_REV=$(node_rev "$LOCK_FROM" "$(input_node "$LOCK_FROM" btc-clients)")

MOVED_LINES=""; SAME_LINES=""

add() {  # add LABEL OLD NEW
    local label="$1" old="$2" new="$3"
    [[ -n "$old" && -n "$new" ]] || return 0
    if [[ "$old" != "$new" ]]; then
        MOVED_LINES+="- **${label}** \`${old}\` → \`${new}\`"$'\n'
    elif [[ "$SHOW_ALL" -eq 1 ]]; then
        SAME_LINES+="- **${label}** \`${new}\` (unchanged)"$'\n'
    fi
}

# ── nixpkgs packages ────────────────────────────────────────────────────────
if moved nixpkgs; then
    for spec in \
        "Bitcoin Core:bi/bitcoin" \
        "LND:ln/lnd" \
        "electrs:el/electrs" \
        "BTCPay Server:bt/btcpayserver" \
        "Matrix Synapse:ma/matrix-synapse-unwrapped" \
        "Vaultwarden:va/vaultwarden" \
        "Caddy:ca/caddy" \
        "Tor:to/tor" \
        "LiveKit:li/livekit"
    do
        label="${spec%%:*}"; p="${spec##*:}"
        add "$label" "$(nix_ver "$NP_OLD_REV" "$p")" "$(nix_ver "$NP_NEW_REV" "$p")"
    done
fi

# ── Sovran_Bitcoin vendored packages ────────────────────────────────────────
if moved sovran-bitcoin; then
    add "Ride The Lightning" \
        "$(dep_ver sovran-bitcoin "$SB_OLD_REV" naturallaw777/Sovran_Bitcoin packages/rtl/default.nix)" \
        "$(dep_ver sovran-bitcoin "$SB_NEW_REV" naturallaw777/Sovran_Bitcoin packages/rtl/default.nix)"
    add "Mempool" \
        "$(dep_ver sovran-bitcoin "$SB_OLD_REV" naturallaw777/Sovran_Bitcoin packages/mempool/default.nix)" \
        "$(dep_ver sovran-bitcoin "$SB_NEW_REV" naturallaw777/Sovran_Bitcoin packages/mempool/default.nix)"
    add "Sovran NWC" \
        "$(dep_ver sovran-bitcoin "$SB_OLD_REV" naturallaw777/Sovran_Bitcoin packages/sovran-nwc/default.nix)" \
        "$(dep_ver sovran-bitcoin "$SB_NEW_REV" naturallaw777/Sovran_Bitcoin packages/sovran-nwc/default.nix)"
fi

# ── btc-clients desktop apps ────────────────────────────────────────────────
if moved btc-clients; then
    add "Sparrow Wallet" \
        "$(dep_ver btc-clients "$BC_OLD_REV" emmanuelrosa/btc-clients-nix pkgs/sparrow/default.nix)" \
        "$(dep_ver btc-clients "$BC_NEW_REV" emmanuelrosa/btc-clients-nix pkgs/sparrow/default.nix)"
    add "Bisq" \
        "$(dep_ver btc-clients "$BC_OLD_REV" emmanuelrosa/btc-clients-nix pkgs/bisq/default.nix)" \
        "$(dep_ver btc-clients "$BC_NEW_REV" emmanuelrosa/btc-clients-nix pkgs/bisq/default.nix)"
    add "Bisq 2" \
        "$(dep_ver btc-clients "$BC_OLD_REV" emmanuelrosa/btc-clients-nix pkgs/bisq2/default.nix)" \
        "$(dep_ver btc-clients "$BC_NEW_REV" emmanuelrosa/btc-clients-nix pkgs/bisq2/default.nix)"
fi

# ── output ──────────────────────────────────────────────────────────────────
if [[ -z "$MOVED_LINES" && -z "$SAME_LINES" ]]; then
    [[ "$QUIET" -eq 1 ]] || echo "No software changed between ${FROM} and ${TO}."
    exit 0
fi

BODY="### Changed"$'\n\n'
[[ -n "$MOVED_LINES" ]] && BODY+="$MOVED_LINES"
[[ -n "$SAME_LINES"  ]] && BODY+=$'\n'"#### Unchanged"$'\n'"$SAME_LINES"

printf '%s' "$BODY"
