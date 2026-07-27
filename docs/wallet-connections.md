# Wallet Connections

Wallet Connections is a Hub-managed Sovran_SystemsOS feature that lets members create isolated Lightning app connections and reusable Lightning Addresses backed by a local LND node via Alby Hub.

## Enablement flow

Use the existing Hub service tile flow:

1. Open **Wallet Connections** in Bitcoin Apps.
2. Enable feature.
3. Complete existing port/domain/DDNS/rebuild flow (80/TCP and 443/TCP).
4. Reopen tile and manage connections.

## Service-detail modal UX

Wallet management runs inside the existing **Wallet Connections** service-detail modal with dedicated states:

1. **Empty state**: no wallets yet, with create action.
2. **Create form**: name, alias, access preset, optional spend limit.
3. **Created/secret state**: one-time pairing secret (URI + QR) shown with prominent warning:
   **Keep the NWC string and QR private. The NWC connection secret cannot be displayed again.**
4. **Wallet list state**: per-wallet actions for verify/test, drain, and delete.

Pairing URI and QR data are cleared when:
- "I Saved This Secret" is clicked
- the service modal X is closed
- the overlay closes the modal
- navigation otherwise leaves the secret view

Guardrails:
- Action buttons are disabled while API requests are in flight.
- Destructive actions (drain/delete) require user confirmation.
- API errors are surfaced inline in the modal state.

## Architecture

```
Authenticated Hub management API
  -> local Alby Hub (port 8080, loopback only)
  -> local LND

Public Lightning Address
  -> local Caddy on 80/443
  -> loopback nwc-lnurl service (port 8181)
  -> local Alby Hub invoice API with isolated appId
  -> local LND
```

Security invariants:

- Alby Hub management port (8080) is never opened to the public firewall.
- Dedicated LNURL service port (8181) is never opened to the public firewall.
- LNURL callback and discovery are exposed only through Caddy on 80/443.
- Management APIs are authenticated and remain under `/api/nwc/`.
- Pairing secrets are returned only on create responses and are never stored.
- Pairing secret QR data is generated only for create responses and is not rehydrated via wallet list APIs.
- Invoice attribution enforces wallet isolation via numeric appId on every LNURL callback.
- Wallet Connections state (Alby Hub database) is never exposed as a plain JSON file.

## Domain and runtime files

- Domain key: `lightning`
- Runtime domain file: `/var/lib/domains/lightning`
- Alby Hub state: `/var/lib/albyhub/` (restrictive permissions, secret-bearing)
- Alby Hub database: `/var/lib/albyhub/nwc.db`
- Alby Hub unlock password: `/var/lib/albyhub/unlock-password` (generated once, mode 0600)
- LND macaroon for Alby Hub: `/run/lnd/albyhub.macaroon` (restricted permissions)

## Alby Hub version pin and patches

Alby Hub is packaged in `modules/nwc-wallets.nix` with the following patches:

1. **Private route hints** (`0001-lnd-private-route-hints.patch`): sets `Private: true` in regular LND `MakeInvoice` requests so that wallets behind private channels can receive payments via route hints. Hold-invoice behavior is unchanged.
2. **Invoice app attribution** (`0002-invoice-app-attribution.patch`): extends `CreateInvoice`, `MakeInvoiceRequest`, `http_service`, and `wails_handlers` to accept and pass an optional numeric `appId` so that LNURL callbacks can attribute invoices to a specific isolated subwallet. Desktop/Wails calls pass `nil` and continue using the primary wallet.

The `vendorHash` and `sha256` fields in the derivation must be updated whenever the Alby Hub version changes.

## Services

| Service | User | Description |
|---|---|---|
| `albyhub.service` | `albyhub` | Headless Alby Hub NWC wallet server |
| `nwc-lnurl.service` | `nwc-lnurl` | Dedicated LNURL discovery and callback service |
| `albyhub-init.service` | `root` (oneshot) | Generates `unlock-password` once on first boot |

## API

Management (authenticated):

- `GET /api/nwc/wallets` — list all managed wallets (no secrets)
- `POST /api/nwc/wallets` — create a wallet; returns `pairing_uri` exactly once
- `DELETE /api/nwc/wallets/{id-or-pubkey}` — drain and delete
- `POST /api/nwc/wallets/{id-or-pubkey}/drain` — transfer funds to primary wallet
- `POST /api/nwc/addresses/{alias}/test` — verify public LNURL endpoint

Public LNURL (served by dedicated `nwc-lnurl` service via Caddy):

- `GET /.well-known/lnurlp/{alias}` — LNURL-pay discovery
- `GET /lnurlp/{alias}/callback?amount=<msat>` — invoice creation via Alby Hub

## Recovery CLI

`nwc-wallet` is included with the Hub package and calls the real Alby Hub manager:

- `nwc-wallet create <name> <alias> --receive-only`
- `nwc-wallet create <name> <alias> --limit-sats <amount>`
- `nwc-wallet list`
- `nwc-wallet drain <wallet>`
- `nwc-wallet delete <wallet>`
- `nwc-wallet address show <alias>`
- `nwc-wallet health`

A CLI `create` command prints the real NWC pairing secret once. Keep it private.

## Backup and restore

`/var/lib/albyhub` is the authoritative Alby Hub state directory. It contains:
- The SQLite database (`nwc.db`) with all wallet app records.
- The unlock password (`unlock-password`).

This directory **must be treated as secret-bearing wallet material**. Backups containing it must be encrypted and access-controlled.

To back up while the service is running, use SQLite online backup (`VACUUM INTO`) or a controlled brief service stop rather than a live `cp`. A brief stop of `albyhub.service` before copying `nwc.db` is the safest approach.

Disabling Wallet Connections stops `albyhub.service` and `nwc-lnurl.service` and removes the Caddy exposure, while preserving `/var/lib/albyhub`. Re-enabling and rebuilding restores all existing connections — no secrets need to be regenerated.

## Troubleshooting

**Alby Hub service not starting:**
- Check `journalctl -u albyhub.service` for errors.
- Verify `/var/lib/albyhub/unlock-password` exists and is readable by `albyhub`.
- Verify `/run/lnd/albyhub.macaroon` exists (LND must be running and the macaroon generated).

**LNURL discovery returning 503:**
- Check that `albyhub.service` is running.
- Check that `/var/lib/domains/lightning` contains the correct domain.
- Check `journalctl -u nwc-lnurl.service`.

**Invoice creation failing:**
- Verify LND has sufficient inbound liquidity on channels with route hints.
- Check `journalctl -u albyhub.service` for LND RPC errors.

**Wallet creation partial failure (funding not transferred):**
- The wallet was created and the NWC connection secret was shown. Save it.
- Do not create another wallet for the same alias.
- Fund the isolated wallet manually via Alby Hub's internal transfer API.
