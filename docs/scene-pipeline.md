# Scene pipeline architecture

This document describes the new host-rendered architecture for the reTerminal repo.

## Core idea

Treat the device as a **4-slot monochrome output target**, not as a fixed app with a hardcoded list of pages.

The host owns:

1. fetching signals from external systems
2. building logical scenes
3. choosing which scenes deserve the 4 physical slots
4. rendering the final bitmaps
5. publishing those bitmaps to the device

## Layers

### `reterminal/device`

Truthful SDK for the current firmware contract.

Responsibilities:

- derive the fixed display contract and live slot state from diagnostic `/status`
- validate slot operations against the reported slot count
- push PIL images safely during a diagnostic window
- keep firmware quirks away from the rest of the app

### `reterminal/providers`

Adapters that return logical scenes.

Responsibilities:

- fetch structured content from a source
- return `SceneSpec` objects
- avoid physical-slot logic

Most providers should also avoid rendering. The current kitchen markdown
providers are the exception: they use shared render helpers for bespoke 800x480
layouts and return `prerendered` scenes until those layouts graduate into
first-class renderer templates. Their parsing/dataclass layer lives outside
the providers package, in `reterminal.family.<name>`, so that any non-display
tool can read family state with `from reterminal.family import parse_calendar,
parse_missions, parse_events, parse_activities` without pulling in PIL.

Current providers:

- `FileSceneProvider` (legacy `{"scenes": [...]}` feed shape)
- `SystemSceneProvider`
- `PaperclipSceneProvider` (remote HTTP feed adapter)
- `CalendarProvider` — reads markdown or structured calendar JSON from the manifest path; parser in `reterminal.family.calendar`, date-relative views in `family/agenda.py`, compositions in `render/agenda.py`
- `MissionsProvider` — reads `~/reterminal-content/family/missions.md` by default; parser in `reterminal.family.missions`
- `EventsProvider` — reads `~/reterminal-content/family/events.md` by default; parser in `reterminal.family.events`
- `ActivitiesProvider` — reads `~/reterminal-content/family/activities.md` by default; parser in `reterminal.family.activities`. The renderer composites an inset movie/series poster on the right side of the layout when the top Queue item is tagged `[movie]` or `[series]`; posters are fetched from Wikipedia's open REST API on first use (no API key) by `reterminal.providers._poster_fetcher` and cached at `~/.cache/reterminal/posters/<slug>.jpg`. Falls back to text-only when the network is unreachable or no Wikipedia article matches.
- `ComingUpProvider` — the consolidated forward-looking board used by the tracked public example's slot 2. Merges `events.md` `## Upcoming` (dated, proximity-sorted) with `activities.md` `## Queue` (undated); the `## Recent` log is not shown. Multi-source: manifest config names `events` + `queue` rather than a single `path`, and `ProviderEntry.source_paths()` reports both so the watch loop tracks each.
- `CampsProvider` — summer schedule parsed from a markdown table (parser in `reterminal.family.camps`); reads e.g. the Madad Wiki `family-summer-2026-camps.md`. Renders the current week as a high-contrast hero plus four upcoming weeks; the table's Notes/cost column is parsed away and never rendered.
- `QuestProvider` — reads only an explicit `## Kitchen Display` block from an allowlisted wiki page and renders one weekly, kid-facing challenge. The large-type layout shows its sourced Spark idea and an explicit validity date.
- `TripProvider` — reads only an explicit `## Kitchen Display` block from an existing trip page and renders a countdown, safe route summary, operating rule, and next gate. Booking details outside that block cannot enter the scene model.
- `PhotoProvider` — watches a folder of images and renders one full-bleed (Floyd-Steinberg, optional `.txt` caption sidecar). Mode `newest` (default) picks newest-by-mtime; `daily` rotates deterministically by date. No markdown source — manifest `path` is the folder.

The kitchen-display providers register themselves into a manifest registry
(`providers/manifest.py`) so a `{"providers": [...]}` JSON config like
`python/examples/kitchen-display.json` can wire them up declaratively.
Provider factories receive their per-entry config dict (typically `path`)
and return a SceneProvider instance. The manifest may also include `slot` to
pin returned scenes to a physical slot; that pin is applied by the manifest
builder, not by provider code. Trip and Quest entries may also declare a nested
`fallback` provider; missing, invalid, or expired primary content yields the
same slot to that provider. Both source paths participate in file watching.

Additional providers worth adding:

- generated media provider
- local queue/status provider

### `reterminal/scenes`

Structured scene schema.

Current core types:

- `SceneSpec`
- `Metric`

The scene layer is intentionally close to a content model, not a render tree.

### `reterminal/scheduler`

Maps logical scenes into physical slots.

Current strategy:

- `PriorityScheduler`

Behavior:

- honor manifest/scene preferred slots first
- resolve conflicts by priority
- fill remaining slots by descending priority

### `reterminal/render`

Turns logical scenes into actual monochrome compositions.

Current renderer stack:

- `MonoRenderer`
- `layout.py` for measured regions and text fitting
- `bitmap.py` for deterministic generated poster art
- `kitchen.py` for shared drawing helpers used by the markdown-backed kitchen layouts

Supported scene kinds:

- `hero`
- `metrics`
- `bulletin`
- `agenda`
- `poster`
- `prerendered` — provider supplies its own 800x480 1-bit PIL image via
  `SceneSpec.prerendered`; MonoRenderer short-circuits and just blits it.
  Used by the bespoke kitchen-display providers (calendar, missions, events,
  activities, coming-up, camps, trip, and quest) whose layouts do not fit the
  chrome+content kinds above.

Current renderer behavior worth knowing:

- `hero` scenes can opt into a chrome-free focus composition via `meta.hero_style = "focus"`
- text-heavy scenes can suppress header/footer chrome with `meta.hide_header` / `meta.hide_footer`
- bulletin rows can tune line count, font-size bounds, row gaps, and whether title/row rules are shown
- `agenda` scenes support structured row payloads (chip, icon, time, title) for schedule pages, plus grouped future-day sections and a dinner band for the main Today/Tomorrow board
- agenda rows can encode small semantic icon variants (for example baseball practice vs game) so short titles still keep the important distinction
- poster/image scenes still use Floyd-Steinberg dithering, but text-heavy scenes now render with a hard threshold for cleaner typography

This is the right place to evolve typography, image treatment, layout systems, and generated bitmap art.

Shared quantitative visualization primitives (progress bars, sparklines, heatmaps, dots, rings, scales, category shapes) live in `reterminal.render.viz`. See `docs/visualizations.md` for the rubric — use these primitives across scene kinds rather than reinventing visual encodings per kind, so readers learn one visual vocabulary.

### `reterminal/app`

High-level orchestration.

Current entrypoints:

- `DisplayPublisher` — single-shot publish (collect → schedule → render → push)
- `run_live` (in `app/live.py`) — FSEvents-driven loop for `publish --watch`.
  Watches every manifest source plus the manifest itself, renders into an atomic
  in-memory edition cache, serves `/content-hash`, hash-bound `/content/slot-N`,
  `/health`, and `/receipt`, and ticks
  every 5 minutes as a sanity fallback. It never discovers or pushes to the
  device; the sleeping firmware is the HTTP client. `DeliveryState` in
  `app/delivery.py` persists bounded device receipts beside the manifest. See
  [delivery.md](delivery.md) for what each stage proves.
- `calendar-export` — explicitly calls the installed gws CLI through
  `family/calendar_export.py`, writing complete-day JSON only after a successful
  validated fetch. The existing calendar launchd job owns this acquisition;
  calendar providers remain local readers.

Pipeline:

- collect scenes from providers
- dedupe by scene id / priority
- schedule scenes into slots
- render images
- preview and/or push

## Why this model

It matches the verified device profile:

- there are only 4 physical slots today
- semantic page names are unstable between host docs and firmware
- external integrations should not be baked into firmware

It also matches the product direction:

- dynamic Paperclip/agent feed
- strong typography and layouts
- image/poster pipeline
- future adapters and scheduler strategies

## Extension points

This repo borrows the spirit of pi's adapter architecture, but keeps the runtime simpler.

Good extension points:

- providers
- renderers / templates
- scheduler strategies
- image post-processors

Bad extension points for now:

- arbitrary plugin runtime inside firmware
- slot semantics in userland code
- scene meaning hardcoded to fixed slot numbers

## Recommended next additions

1. scheduler policy for pinned vs rotating scenes
2. preview regression corpus for layout stress cases
3. richer poster/image composition templates
4. provider composition / multi-feed merge policy
5. device capability caching/versioning
