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
  -> local Alby Hub (port 18080, loopback only)
  -> local LND

Public Lightning Address
  -> local Caddy on 80/443
  -> loopback nwc-lnurl service (port 8181)
  -> local Alby Hub invoice API with isolated appId
  -> local LND
```

Security invariants:

- Alby Hub management port (18080) is never opened to the public firewall.
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

## Alby Hub package and patches

Wallet Connections uses `pkgs.albyhub` from the repository's pinned `nixpkgs` input and applies three conventional patches via `overrideAttrs`:

1. **Private route hints** (`packages/albyhub/0001-private-route-hints.patch`): changes regular LND invoice creation from `Private: !hasPublicChannels` to `Private: true` and leaves hold-invoice logic unchanged.
2. **Invoice app attribution** (`packages/albyhub/0002-isolated-invoice-app-id.patch`): updates `api/models.go`, `api/transactions.go`, `http/http_service.go`, and `wails/wails_handlers.go` so invoice creation accepts and forwards optional `appId`.
3. **Loopback bind host** (`packages/albyhub/0003-loopback-bind-host.patch`): adds `HOST` to config and binds Echo to `HOST:PORT` instead of `:PORT`.

No placeholder source/vendor hashes are used in the Wallet Connections module.

## Services

| Service | User | Description |
|---|---|---|
| `albyhub.service` | `albyhub` | Headless Alby Hub NWC wallet server |
| `nwc-lnurl.service` | `albyhub` | Dedicated LNURL discovery and callback service |
| `albyhub-init.service` | `root` (oneshot) | Generates `unlock-password` once on first boot |

`nwc-lnurl.service` runs as `albyhub` so it can traverse `/var/lib/albyhub` (0700) and read `/var/lib/albyhub/unlock-password` (0600) without weakening permissions.

## Wallet Connections icon asset

- Hub service icon identifier: `nwc` (feature name remains **Wallet Connections**)
- Asset path in this repository: `app/icons/nwc.svg`
- Official source: `https://raw.githubusercontent.com/getAlby/nostr-wallet-connect/5fb6831739c7e6b089cd7205e11910ef542432ad/public/images/nwc-logo.svg`
- Upstream repository: `https://github.com/getAlby/nostr-wallet-connect`
- Upstream license: Apache-2.0 (`https://github.com/getAlby/nostr-wallet-connect/blob/5fb6831739c7e6b089cd7205e11910ef542432ad/LICENSE`)
- Attribution/redistribution note: Apache-2.0 permits redistribution; preserve upstream license notices in distributions.

## API

Management (authenticated):

- `GET /api/nwc/wallets` — list all managed wallets (no secrets)
- `POST /api/nwc/wallets` — create a wallet; returns `pairing_uri` exactly once
- `DELETE /api/nwc/wallets/{id-or-pubkey}` — drain and delete
- `POST /api/nwc/wallets/{id-or-pubkey}/drain` — transfer funds to primary wallet
- `POST /api/nwc/addresses/{alias}/test` — verify public LNURL endpoint

Exact Hub setup/auth flow used by the manager:

- `GET /api/info`
- If `setupCompleted == false`: `POST /api/setup` with `backendType`, `unlockPassword`, `lndAddress`, `lndCertFile`, `lndMacaroonFile`
- `GET /api/info` again
- If `running == false`: `POST /api/start` with `unlockPassword`
- If `running == true`: `POST /api/unlock` with `unlockPassword` and `permission: "full"`
- Poll authenticated `GET /api/node/status` until `isReady == true`
- Cached bearer token is refreshed once on 401/403

Exact app/transaction usage:

- `GET /api/apps?limit=<N>&offset=<N>&order_by=created_at` (full pagination using `totalCount`)
- `GET /api/v2/apps/{id}` for app-by-id fetches
- `GET /api/transactions?appId={id}&limit=<N>&offset=<N>` (full pagination using `totalCount`)
- Wallet metadata uses `appPubkey` and `balanceMsat` (`balance_sats = balanceMsat / 1000`, `dust_msat = balanceMsat % 1000`)
- Limited-wallet initial funding uses `POST /api/transfers` with `toAppId`, `amountSat`, `description`
- Drain uses `PATCH /api/apps/{appPubkey}`, transfer with `fromAppId` + `amountMsat`, and enforces final dust equality
- Delete uses `DELETE /api/apps/{appPubkey}` after pending/drain checks

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
