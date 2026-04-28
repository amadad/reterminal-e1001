# Refactor plan

This is the cleanup plan for bringing the repo back to one truthful architecture.

Current status (2026-04-27): the repo now centers on a 4-slot provider-driven kitchen-display pipeline. Firmware, host docs, and launchd tooling have been updated for clean invalid-slot rejection, LittleFS persistence, mDNS/OTA startup, snapshot-seeded live publishing, and 32MB flash configuration. Remaining closure still requires flashing/probing the current source on the live device and recording that evidence.

## Phase 0 — freeze and secure

Goal: stop compounding drift while the system is being verified.

- stop adding new page features
- stop treating legacy docs as authoritative
- remove hardcoded secrets from firmware
- decide whether OTA stays; if it stays, secure it
- prefer `python/reterminal/` over legacy Python paths for any new work

Exit criteria:

- security risks are documented
- verification docs exist
- new work is blocked on hardware verification, not guesswork

## Phase 1 — verify the real device

Goal: establish what the hardware/firmware actually supports.

- run `reterminal probe`
- run the destructive slot probe with `--upload-pages`
- manually verify buttons, visible rendering, reboot persistence, OTA behavior
- record the verified slot count and any API mismatches

Exit criteria:

- `docs/device-profile.md` contains verified values, not just code-inspection guesses
- actual supported slot count is known
- page navigation behavior is understood

## Phase 2 — choose the architecture

Default recommendation unless verification disproves it:

- **host owns data + rendering**
- **firmware owns bitmap storage + display + buttons + status**

Decision points:

- if firmware supports only 4 reliable slots, host can still render more logical pages but only 4 may be cached at once
- if firmware supports 7+ reliable slots, a native 7-page carousel is acceptable
- if page persistence is weak, host republish remains the recovery path; current tracked source persists slots to LittleFS when mounted

Exit criteria:

- page model is chosen and written down
- responsibilities of firmware vs host are explicit

## Phase 3 — collapse duplicate implementations

Goal: remove stale paths and converge on one stack.

Keep:

- `firmware/`
- `python/reterminal/`

Archived/decommissioned after migration:

- root-level legacy direct scripts (`python/reterminal.py`, `python/refresh.py`) are gone
- fixed-page `refresh` / `watch` CLI commands are no longer active
- `python/reterminal/pages/*` remains only as compatibility code, not as the design center
- stale docs that describe the legacy Python flow as current should be rewritten or removed

Exit criteria:

- one Python CLI path
- provider manifests are the active page ownership model
- no live production loop uses legacy fixed-page ownership

## Phase 4 — rebuild the smallest truthful vertical slice

Goal: prove the chosen architecture with the minimum system that matters.

Recommended slice:

1. status
2. push raw image
3. set page / next / prev
4. one simple host-rendered page, likely clock

Then reintroduce richer pages one by one.

Exit criteria:

- smallest end-to-end path works on the real device
- new work is built on the verified stack only

## Phase 5 — make docs and tooling truthful

- update README, AGENTS, CLAUDE, and Python docs
- expose firmware-reported capabilities to the host
- add smoke tests for probe/encoding flows
- remove any mention of unsupported page counts or broken wrappers
- keep `docs/_solutions.md`, `CLAUDE.md`, `AGENTS.md`, README, and the launchd wrapper in sync when slot ownership changes

Exit criteria:

- docs match observed behavior
- automation uses the verified workflow
- future agents have one source of truth

## Definition of done

The refactor is complete when:

- firmware, host, and docs agree on page capacity and API semantics
- secrets are removed from the repo
- one Python implementation remains
- device capability is verified, recorded, and queryable
- the core vertical slice is tested on real hardware
