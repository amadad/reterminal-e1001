# Layout system

This document formalizes how scene layout should work on the reTerminal display.

## Problem statement

The display renderer cannot rely on ad hoc `draw.text()` coordinates anymore. That approach creates:

- text-on-text collisions
- no overflow policy
- unstable spacing from one scene to the next
- poor image/text composition in monochrome

The fix is to treat layout as a small editorial system with measured regions and explicit fitting rules. The current direction is deliberately narrower than a general dashboard toolkit: a small set of calm templates with only a few optical scales and regular spatial relationships.

## Rendering model

Each render goes through four conceptual layers:

1. **Scene data**
   - semantic content only
   - example: title, subtitle, metrics, bullets, image path

2. **Template spec**
   - named regions with size budgets
   - example: title band, metric card, body column, footer strip

3. **Measured layout**
   - text is wrapped, shrunk, clamped, or ellipsized to fit regions
   - this is where overflow decisions happen

4. **Bitmap output**
   - final monochrome image for the firmware

## Design rules

### 1. Scene kinds have content budgets

Each scene kind must constrain how much content it can successfully display.

#### `hero`
- default hero: title max 3 lines, optional metric panel, body max 4 bullets
- focus hero (`meta.hero_style = "focus"`): one large title block plus one large focus line
- focus heroes are allowed to hide both header chrome and footer chrome
- footer is optional, not mandatory

#### `metrics`
- title: max 1 line
- subtitle/meta: max 1 line
- metrics: max 6 cards
- labels: max 1 line
- values: max 2 lines
- details: max 1 line

#### `bulletin`
- title: max 1 quiet heading line
- subtitle: optional, max 1 line
- feed items: usually 3–4 rows on-device for the current kitchen-family layouts
- each item: 2 lines by default, with row budgets adjustable via scene metadata
- footer is optional, not mandatory

#### `agenda`
- supports schedule-oriented compositions where rows have ownership markers, time labels, and short titles
- current renderer supports two agenda modes:
  - **two-day**: `Today` / `Tomorrow` columns plus a dinner band
  - **grouped**: stacked future-day sections with short event rows
- current live kitchen feed uses the **two-day** agenda for slot 0; grouped agenda remains available as a renderer pattern but is no longer the default fourth page
- event rows should prefer monogram chips, simple 1-bit icons, and short titles over raw calendar strings
- sports rows may use variant icons so practice vs game survives even when the title is shortened

#### `poster`
- image region is dominant
- text never overlays directly on detailed art
- headline: max 2 lines
- subtitle: max 2 lines
- footer: max 1 line

### 2. Layout uses named regions

Templates define explicit rectangles for content, for example:

- `title_rect`
- `subtitle_rect`
- `metric_rect`
- `body_rect`
- `footer_rect`
- `folio_rect`
- `image_rect`
- `caption_rect`

Footer/folio strips are now optional. Text-heavy scenes may hide header and footer chrome entirely when the content benefits from a calmer poster-like composition. If footer chrome is shown, it should hold provenance or low-priority metadata instead of competing with the main content.

Content is fitted into regions; regions do not resize dynamically based on drawing side effects.

### 3. Overflow policy is explicit

Text fitting uses this order of operations:

1. wrap text to region width
2. shrink font size down to a floor
3. reduce allowed line count if region height is smaller than the nominal budget
4. ellipsize the last allowed line if content still overflows

This prevents accidental overlap and ensures failure is graceful.

### 4. Image scenes reserve text-safe areas

For `poster` scenes, text should live in a reserved caption band or knockout box. Body copy should not be placed directly on top of detailed imagery unless a future renderer adds explicit safe-region analysis.

### 5. Posters can use generated bitmaps

Poster scenes should support deterministic host-generated bitmap art in addition to source images. This is useful for:

- sparklines
- bar summaries
- grids / occupancy maps
- simple status diagrams

Generated bitmap art should use the same reserved caption and footer bands as image-based posters.

The shared vocabulary for quantitative visualizations now lives in `reterminal.render.viz` — `progress_bar`, `sparkline`, `heatmap`, `dots`, `ring`, `scale`, and category `shape`. See `docs/visualizations.md` for the rubric on when to use each primitive and when not. Reach for these before inventing a new visualization style inside a specific scene kind.

## Current implementation

The current renderer now uses:

- `Rect`
- `fit_text_block()`
- `draw_text_block()`
- opt-in header/footer chrome via `meta.hide_header` / `meta.hide_footer`
- `meta.hero_style = "focus"` for the older kitchen-board style hero
- bulletin row tuning via `item_max_lines`, `item_max_font_size`, `item_min_font_size`, and `item_gap`
- agenda metadata for schedule scenes (`agenda_style`, column/day labels, structured rows, dinner band)
- deterministic bitmap generators for poster scenes

These provide:

- explicit region boundaries
- font-size search within min/max limits
- calmer focus/list/agenda compositions for text-heavy scenes
- line-budget reduction based on height
- ellipsis on the last visible line only when fitting still fails
- hard-threshold text rendering for non-poster scenes, with dithering reserved for poster/image work

## Technical direction

The renderer should continue evolving toward reusable layout primitives.

Candidate primitives:

- `TextBlock`
- `MetricCard`
- `BulletRow`
- `CaptionBand`
- `FooterBar`
- `ImageFrame`

These should compose templates instead of hand-coded per-scene coordinate drawing.

## Regression strategy

Every layout change should be previewed against a stress corpus, including:

- very long titles
- dense bullet lists
- oversized metric values
- poster scenes with long subtitles
- empty or missing optional fields

Eventually this should become a preview regression suite so layout failures are visible before they hit the device.
