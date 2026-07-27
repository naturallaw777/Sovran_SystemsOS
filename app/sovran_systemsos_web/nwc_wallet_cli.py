from __future__ import annotations

import argparse
import json
import sys

from . import server


def _print(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nwc-wallet")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("alias")
    preset_group = create.add_mutually_exclusive_group()
    preset_group.add_argument("--receive-only", action="store_true")
    preset_group.add_argument("--limit-sats", type=int)

    sub.add_parser("list")

    drain = sub.add_parser("drain")
    drain.add_argument("wallet")

    delete = sub.add_parser("delete")
    delete.add_argument("wallet")

    addr = sub.add_parser("address")
    addr_sub = addr.add_subparsers(dest="address_cmd", required=True)
    addr_show = addr_sub.add_parser("show")
    addr_show.add_argument("alias")

    sub.add_parser("health")

    args = parser.parse_args(argv)
    state = server._nwc_load_state()
    domain = server._nwc_domain()

    if args.cmd == "list":
        _print({"wallets": [server._nwc_wallet_meta(w, domain) for w in state.get("wallets", [])]})
        return 0

    if args.cmd == "health":
        _print({"ok": True, "domain": domain, "wallet_count": len(state.get("wallets", []))})
        return 0

    if args.cmd == "address" and args.address_cmd == "show":
        test = server._nwc_test_address(args.alias.strip().lower())
        _print(test)
        return 0 if test.get("ok") else 1

    wallet = server._nwc_find_wallet(state, getattr(args, "wallet", ""))
    if args.cmd in {"drain", "delete"} and wallet is None:
        print("Error: wallet_not_found - The specified wallet connection does not exist.", file=sys.stderr)
        return 1

    if args.cmd == "drain":
        if int(wallet.get("pending_transactions", 0)) > 0:
            print("Error: pending_transactions - Wallet has pending transactions.", file=sys.stderr)
            return 1
        drained = int(wallet.get("balance_sats", 0))
        wallet["balance_sats"] = 0
        server._nwc_save_state(state)
        _print({"ok": True, "drained_sats": drained, "dust_msat": int(wallet.get("dust_msat", 0))})
        return 0

    if args.cmd == "delete":
        if int(wallet.get("pending_transactions", 0)) > 0:
            print("Error: pending_transactions - Wallet has pending transactions.", file=sys.stderr)
            return 1
        if int(wallet.get("balance_sats", 0)) > 0:
            print("Error: balance_drain_failed - Drain this wallet before deleting it.", file=sys.stderr)
            return 1
        wallet_id = wallet.get("id")
        state["wallets"] = [w for w in state.get("wallets", []) if w.get("id") != wallet_id]
        server._nwc_save_state(state)
        _print({"ok": True})
        return 0

    if args.cmd == "create":
        alias = args.alias.strip().lower()
        if not server._nwc_validate_alias(alias):
            print("Error: alias_invalid - Alias must be lowercase letters, digits, '_' or '-'.", file=sys.stderr)
            return 1
        if any(w.get("alias") == alias for w in state.get("wallets", [])):
            print("Error: alias_exists - This alias already exists.", file=sys.stderr)
            return 1
        if any(w.get("name", "").lower() == args.name.strip().lower() for w in state.get("wallets", [])):
            print("Error: wallet_name_exists - This wallet name already exists.", file=sys.stderr)
            return 1
        access_preset = "send_receive_limited" if args.limit_sats is not None else "receive_only"
        wallet = {
            "id": server.secrets.token_hex(8),
            "pubkey": server.secrets.token_hex(16),
            "name": args.name.strip(),
            "alias": alias,
            "access_preset": access_preset,
            "spending_limit_sats": args.limit_sats if access_preset == "send_receive_limited" else None,
            "remaining_budget_sats": args.limit_sats if access_preset == "send_receive_limited" else None,
            "balance_sats": 0,
            "dust_msat": 0,
            "pending_transactions": 0,
            "min_sendable_msat": server.NWC_MIN_SENDABLE_MSAT,
            "max_sendable_msat": server.NWC_MAX_SENDABLE_MSAT,
            "created_at": int(server.time.time()),
        }
        state.setdefault("wallets", []).append(wallet)
        server._nwc_save_state(state)
        _print(
            {
                "wallet": server._nwc_wallet_meta(wallet, domain),
                "pairing_uri_available": False,
                "message": "For security, pairing secrets are only returned from Hub create API responses.",
                "verification": server._nwc_test_address(alias),
            }
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
