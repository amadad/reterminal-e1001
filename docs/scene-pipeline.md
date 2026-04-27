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

- discover capabilities (prefer `/capabilities`, fall back to `/status` + `/page`)
- validate slot operations against the live slot count
- push PIL images safely
- keep firmware quirks away from the rest of the app

### `reterminal/providers`

Adapters that return logical scenes.

Responsibilities:

- fetch structured content from a source
- return `SceneSpec` objects
- avoid rendering or slot logic

Current providers:

- `FileSceneProvider` (legacy `{"scenes": [...]}` feed shape)
- `SystemSceneProvider`
- `PaperclipSceneProvider` (remote HTTP feed adapter)
- `CalendarProvider` — reads `~/madad/family/calendar.md`
- `MissionsProvider` — reads `~/madad/family/missions.md`
- `EventsProvider` — reads `~/madad/family/events.md`
- `ActivitiesProvider` — reads `~/madad/family/activities.md`

The kitchen-display providers register themselves into a manifest registry
(`providers/manifest.py`) so a `{"providers": [...]}` JSON config like
`python/examples/kitchen-display.json` can wire them up declaratively.
Provider factories receive their per-entry config dict (typically `path`)
and return a SceneProvider instance.

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

- honor preferred slots first
- resolve conflicts by priority
- fill remaining slots by descending priority

### `reterminal/render`

Turns logical scenes into actual monochrome compositions.

Current renderer stack:

- `MonoRenderer`
- `layout.py` for measured regions and text fitting
- `bitmap.py` for deterministic generated poster art

Supported scene kinds:

- `hero`
- `metrics`
- `bulletin`
- `agenda`
- `poster`
- `prerendered` — provider supplies its own 800x480 1-bit PIL image via
  `SceneSpec.prerendered`; MonoRenderer short-circuits and just blits it.
  Used by the kitchen-display providers (calendar/missions/events/activities)
  whose layouts do not fit the chrome+content kinds above.

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
  Watches the parent directories of every manifest provider's source file,
  re-renders on change, in-memory bitmap-compares to skip unchanged pushes,
  and ticks every 5 minutes as a sanity fallback. No persisted state.

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
