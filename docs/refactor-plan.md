# Refactor plan

This is the cleanup plan for bringing the repo back to one truthful architecture.

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
- if page persistence is weak, cached pages are an optimization, not a contract

Exit criteria:

- page model is chosen and written down
- responsibilities of firmware vs host are explicit

## Phase 3 — collapse duplicate implementations

Goal: remove stale paths and converge on one stack.

Keep:

- `firmware/`
- `python/reterminal/`

Archive or delete after migration:

- `python/reterminal.py`
- `python/refresh.py`
- `python/pages/*`
- stale docs that describe the legacy Python flow as current

Exit criteria:

- one Python CLI path
- one page registry
- no parallel implementations of the same feature

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
