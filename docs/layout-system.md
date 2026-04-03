# Layout system

This document formalizes how scene layout should work on the reTerminal display.

## Problem statement

The display renderer cannot rely on ad hoc `draw.text()` coordinates anymore. That approach creates:

- text-on-text collisions
- no overflow policy
- unstable spacing from one scene to the next
- poor image/text composition in monochrome

The fix is to treat layout as a small editorial system with measured regions and explicit fitting rules.

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
- title: max 3 lines
- subtitle/meta: max 1 line
- metric: optional, but if present it gets its own reserved panel
- body: max 3 bullets
- footer: max 1 line

#### `metrics`
- title: max 1 line
- subtitle/meta: max 1 line
- metrics: max 6 cards
- labels: max 1 line
- values: max 2 lines
- details: max 1 line

#### `bulletin`
- title: max 1 line
- subtitle: max 1 line
- feed items: max 5 rows
- each item: max 2 lines

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

Every scene must reserve a footer/folio strip. Page indicators, freshness stamps, and source labels belong there instead of floating near the bottom of the content area.

The current renderer now leaves the right side of that strip blank by default; scene metadata must opt in explicitly if any right-hand footer chrome should be shown.

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

## Current implementation

The current renderer now uses:

- `Rect`
- `fit_text_block()`
- `draw_text_block()`
- footer/folio chrome regions
- deterministic bitmap generators for poster scenes

These provide:

- explicit region boundaries
- font-size search within min/max limits
- line-budget reduction based on height
- ellipsis on the last visible line when needed

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
