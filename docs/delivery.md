# Delivery and freshness

The publisher and device report different evidence. A running service or a
successful bitmap HTTP response does not establish device storage or a visible
screen update.

## Operational check

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal doctor \
  --publisher-url http://127.0.0.1:8765 \
  --feed examples/kitchen-display.local.json --output json
```

Omit `--host` and unset `RETERMINAL_HOST` to inspect a sleeping device through its publisher. Add a freshly discovered `--host` during
diagnostic mode for live status and firmware checks.

`GET /health` reports the active manifest, source file modification times and
explicit calendar `checked_at`, last successful render, persistent configuration
errors, latest poll/download requests, desired hashes, and device receipts.
The source check timestamp determines calendar staleness; copying or rendering
an old export does not renew it. Doctor exits nonzero for source checks older
than two hours, failed/stale delivery, publisher errors, or unreachable health.
An optional expired quest can be absent while its calendar fallback is healthy.

Delivery statuses:

| Status | Meaning |
| --- | --- |
| `unconfirmed` | No valid device receipt has arrived. |
| `pending` | The latest receipt does not match the currently served edition. |
| `stored` | Assigned slot hashes match a recent successful device receipt. |
| `failed` | The device reported a failed or partial pull. |
| `stale` | The latest receipt is older than two wake intervals plus two minutes. |

`last_poll` and `last_download` include the requesting address; diagnostic client
requests can also populate these fields. They do not identify the device by
themselves. The unauthenticated LAN protocol is not an identity/security boundary.

## Device receipts

The new firmware sends `POST /receipt` after a boot, timer, or diagnostic pull.
The host supplies `received_at`, records whether the hashes matched at receipt
time, and atomically persists the latest 32 receipts alongside the manifest as
`*.delivery.json` (gitignored). Receipts survive a publisher restart; poll/download
request timestamps do not. Invalid receipts do not replace the previous evidence.

The firmware hashes actual stored files. `current_page` reports selection;
`displayed_hash` identifies the bitmap submitted in the last returned full-refresh
driver call. `refresh_returned` says that call returned in this wake. The display
driver can return after a busy timeout, so neither field proves optical or
controller success. Physical inspection remains the final display-quality check.

Source exports replace their file only after a complete validated fetch. The
publisher installs a complete rendered edition atomically, preserving its prior
cache on rendering failure. Firmware verifies each requested hash, downloads into
a separate buffer with a total deadline, and verifies staged storage before
replacing that slot. Device updates remain per-slot: a partial pull is reported
explicitly and retried at a later wake.

Explicit null hashes mean unassigned slots, whose stored bytes are preserved.
Retiring a card therefore needs a replacement scene, such as the manifest's
calendar fallback; removing its assignment alone does not erase the old device
bitmap.

## Rollout and physical verification

1. Activate the structured calendar exporter described in [calendar-source.md](calendar-source.md).
2. Restart the publisher to load changed Python modules. Manifest hot reload only
   changes configuration. Verify `/health` and all four
   `/content/slot-N?hash=<advertised-hash>` responses before flashing: old publisher
   code does not understand hash-bound URLs. New host code accepts old firmware.
3. Build/flash firmware through the existing PlatformIO path; rediscover and run
   doctor, capabilities, and a physical probe. Record binary SHA-256 and reported
   build time. Matching `HEAD-dirty` labels do not prove equal firmware.
4. Inspect stored snapshots, page selection, and returned refresh identity; then
   inspect the actual screen at normal kitchen viewing distance.
5. Record three successive changed editions confirmed by **timer** receipts,
   each with `matches_at_receipt: true`, without diagnostic holds or manual pushes.
   Confirm navigation does not reset the deadline. Preserve receipt JSON as local
   evidence; synthetic HTTP tests are not physical wake-cycle proof.
6. Verify publisher restart preserves receipts and upstream failure retains the
   last successful calendar export and its old timestamp.

The configured cadence remains a 20-minute source export, immediate watched
rendering with a five-minute sanity tick, and a 30-minute device poll. Allow up
to roughly 55 minutes from a calendar edit under healthy service/network conditions;
this is a configured budget, not a measured guarantee. Button navigation preserves
the next poll deadline in the new firmware. A long right-button hold requests a
fresh pull before opening diagnostics. No new scheduler or always-on device
server is introduced.
