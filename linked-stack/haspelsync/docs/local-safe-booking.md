# Local safe-booking changes

Local version: `1.3.4-local.1`, based on upstream commit
`253afa06a133246a52558ba42e0dae478a5f0f27` and the installed Ukrainian translation.

## Behaviour

- Every used sliced filament must resolve to exactly one known physical spool
  before any consumption request is sent. A missing or ambiguous assignment
  leaves the whole print uncharged, with the reason in its existing summary.
- Spoolman's `PUT /spool/{id}/use` is additive despite being a PUT. Automatic
  HTTP retries are disabled for this request.
- `printers/bookings.json` records an intent before the HTTP request, and its
  acknowledged result after success. The printer, saved print start and sliced
  item identify the attempt. Another physical run of the same file gets another
  identity. Changed mass, spool or Spoolman endpoint conflicts with a saved attempt.
- A successfully recorded replay returns its original result without a debit.
- Pending and uncertain attempts never retry automatically. The server may have
  committed the debit before losing the response. Check the actual Spoolman
  balance and existing printer logs before applying a manual correction.
- `GET /api/print/{printerId}/bookings` returns the latest 100 attempts behind the
  normal API authentication. The existing API explorer describes the route.
  No Spoolman URL, credentials or request hashes appear in this response.

## Storage and recovery limits

The journal is local to one running HaspelSync instance and uses atomic file
replacement. Do not run two writers against the same `printers` directory.
Back it up together with the other printer state. A malformed, unreadable or
unsupported journal blocks consumption instead of silently starting empty.
Do not delete it to retry a print: doing so loses the duplicate protection.

The initial limit is 10,000 attempts or 16 MiB. Reaching it blocks new writes;
no booking identities are silently evicted. A future reviewed archive/recovery
workflow can compact this history. No automated resolution endpoint is provided.

This is conservative local duplicate protection, not a transaction shared with
Spoolman. Different spools still use separate HTTP requests. An outage can leave
part of a multi-material print charged, and uncertain attempts require manual
review. Power-loss durability, distributed writers and a server-side
idempotency-key protocol are not claimed. An unknown terminal event first seen
after the print has ended still follows upstream's recovery rules.

The patch changes G-code mode only. Legacy RFID percentage updates are unchanged.
It does not convert calculated consumption into physically measured mass.

## Build and rollback

From the checkout, with the installed local base image present:

```powershell
docker build -f docker/Dockerfile.local-safe -t filament-manager/haspelsync:1.3.4-uk-safe1 .
```

Use the resulting image for the existing `haspelsync` Compose service when no
print is active. Keep its existing ports and data/log volumes. Spoolman and its
database require no migration for this patch. Take a backup of printer state
and the Spoolman database before replacing a running service.

Rollback selects the former image `filament-manager/haspelsync:1.3.4-uk`.
Preserve `bookings.json`: the former version ignores it, and returning to the
patched version must retain its saved attempts. Rollback also restores upstream
booking behaviour, so uncertain writes still require review.

## Validation

`node --test "test/*.test.js"` runs the suite. New regressions cover dropped
responses after remote debit, HTTP 503, same-file reprint, conflicting requests,
corrupt/unreadable storage, missing run identity, authenticated scoped history,
ambiguous allocation, whole-print allocation gating and process termination
after a fake Spoolman commits its debit. All network tests use throwaway local
servers and temporary state. No live inventory is used.

One existing language test now converts file URLs correctly on Windows. The
existing POSIX SIGTERM-delivery test is explicitly skipped on Windows, where
the operating system terminates the process instead of delivering that signal.
