# Hardware verification plan

Run this before making architecture decisions about page counts, caching, or firmware responsibilities.

## Important warning

The automated slot probe is **destructive**.

It uploads a test pattern into page slots and will overwrite whatever bitmaps are currently cached on the device.

## Preconditions

- Device is powered on and reachable on the network
- You know the correct device IP or have `RETERMINAL_HOST` set
- You can run commands from `python/`
- You are okay replacing cached display pages during the test

## 1. Non-destructive baseline

From the `python/` directory:

```bash
uv run reterminal probe
```

This checks:

- `GET /status`
- `GET /page`
- missing status fields versus the provisional contract

If this fails, stop and fix connectivity/basic API issues first.

## 2. Destructive slot probe

From the `python/` directory:

```bash
mkdir -p ../artifacts
uv run reterminal probe \
  --upload-pages \
  --slots 8 \
  --expected-pages 7 \
  --output ../artifacts/probe-report.json
```

What this does:

- uploads a known bitmap pattern to requested slots `0..7`
- checks whether the firmware confirms that each slot was actually stored
- calls `POST /page` for the same requested slot values
- infers the contiguous supported slot count starting at slot `0`
- restores the original current page if possible

## 3. Manual physical checks

The probe cannot verify what a human must observe on the device. Record these results manually.

| Check | Pass/Fail | Notes |
|---|---|---|
| Uploaded pattern visibly appears on each slot the probe marked as supported |  |  |
| Physical previous button matches API page navigation |  |  |
| Physical next button matches API page navigation |  |  |
| Physical refresh button behavior is understood and documented |  |  |
| Stored pages survive reboot |  |  |
| Stored pages survive OTA flash (if OTA remains in scope) |  |  |
| Full-screen refresh latency is acceptable |  |  |
| Ghosting / visual artifacts are acceptable |  |  |

## 4. Questions to answer from the run

After the automated and manual checks, write down these answers:

1. What is the **verified contiguous slot count**?
2. Does the firmware reject invalid page numbers or silently wrap them?
3. Does an invalid `?page=N` upload store, reject, or display immediately?
4. Do the physical buttons operate over the same slot range as the API?
5. Are cached pages persistent enough to be part of the product contract?
6. Is OTA reliable enough to keep in the default workflow?

## 5. How to interpret results

- If the probe confirms **4 slots**, the current firmware is a 4-slot cache and the host must adapt.
- If it confirms **7+ slots**, the 7-page carousel is viable on-device.
- If behavior is inconsistent between API and buttons, firmware needs cleanup before host refactor.
- If reboot clears cached pages, treat caching as ephemeral.

## 6. Required follow-up

Once you have results:

1. update `docs/device-contract.md` with verified values
2. update `docs/refactor-plan.md` with the chosen page model
3. remove or rewrite any docs that still claim unverified capability
