# Wallet Connections

Wallet Connections is a Hub-managed Sovran_SystemsOS feature that lets members create isolated Lightning app connections and reusable Lightning Addresses.

## Enablement flow

Use the existing Hub service tile flow:

1. Open **Wallet Connections** in Bitcoin Apps.
2. Enable feature.
3. Complete existing port/domain/DDNS/rebuild flow (80/TCP and 443/TCP).
4. Reopen tile and manage connections.

## Service-detail modal UX (implemented)

Wallet management now runs inside the existing **Wallet Connections** service-detail modal with dedicated states:

1. **Empty state**: no wallets yet, with create action.
2. **Create form**: name, alias, access preset, optional spend limit.
3. **Created/secret state**: one-time pairing secret (URI + QR when available) shown with explicit "save now" warning.
4. **Wallet list state**: per-wallet actions for verify/test, drain, and delete.

Guardrails in modal flow:

- Action buttons are disabled while API requests are in flight.
- Destructive actions (drain/delete) require user confirmation.
- API errors are surfaced inline in the modal state.

Node role behavior is unchanged: Node onboarding still skips global domain/port setup, and the `lightning` domain is configured on demand through feature enablement.

## Architecture

Public path:

`Internet -> DNS/DDNS -> router 80/443 -> Caddy -> LNURL endpoints -> Hub NWC backend -> local LND stack`

Security invariants:

- Alby/NWC management remains local to the host.
- LNURL callback/discovery are exposed only through Caddy on 80/443.
- Management APIs are authenticated and remain under `/api/nwc/`.
- Pairing secrets are returned only on create responses.
- Pairing secret QR data is generated only for create responses and is not rehydrated via wallet list APIs.
- Invoice attribution enforces wallet isolation with app-id checks.

## Domain and runtime files

- Domain key: `lightning`
- Runtime domain file: `/var/lib/domains/lightning`
- Wallet state: `/var/lib/nwc-wallets/state.json`

## API

- `GET /api/nwc/wallets`
- `POST /api/nwc/wallets`
- `DELETE /api/nwc/wallets/{id-or-pubkey}`
- `POST /api/nwc/wallets/{id-or-pubkey}/drain`
- `POST /api/nwc/addresses/{alias}/test`

Public LNURL:

- `GET /.well-known/lnurlp/{alias}`
- `GET /lnurlp/{alias}/callback?amount=<msat>`

## Recovery CLI

`nwc-wallet` is included with Hub package:

- `nwc-wallet create <name> <alias> --receive-only`
- `nwc-wallet create <name> <alias> --limit-sats <amount>`
- `nwc-wallet list`
- `nwc-wallet drain <wallet>`
- `nwc-wallet delete <wallet>`
- `nwc-wallet address show <alias>`
- `nwc-wallet health`

## Backup and restore

Wallet Connections state is stored in `/var/lib/nwc-wallets` and is included with `/var/lib` backups. Backups contain sensitive wallet-connection material and must be protected.
