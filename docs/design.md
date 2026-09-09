# Kitchen-display design system

The governing document for how the four slots *look*. The goal is **unity, not
uniformity**: every slot shares one visual language so the wall reads as one
considered object, while each slot's body is free to be composed for its own
content. Legibility at a kitchen glance on a 1-bit ePaper panel beats density,
always.

## Governing mechanism

Three layers, each enforcing the next. A prose doc alone drifts; code alone has
no rationale; neither catches regressions. So:

| Layer | Where | Role |
|-------|-------|------|
| **Intent** | this file (`docs/design.md`) | the *why*, the tokens, the legibility floor |
| **Tokens** | `python/reterminal/render/kitchen.py` | the type ladder + `draw_kicker` / `draw_rule` / `shape_for` as code; renderers compose from these |
| **Guardrail** | `tests/test_renderer_snapshots.py` goldens | any unintended pixel change fails the test suite; intentional ones move the pin in the same commit |

Rule: **change a token → update this doc in the same edit → re-pin the goldens.**
`CLAUDE.md` remains the source of truth for the rendering *constraints* (rules
6–9: bundled font, `fontmode="1"`, threshold-vs-dither, full refresh); this doc is
the *design intent* above the code, and `docs/visualizations.md` is the
data-encoding vocabulary it draws on.

## Principles

1. **Glance, not read.** A slot answers one question from across the kitchen.
   Fewer items, larger type, more whitespace. Now shows at most three items per
   day as space permits; Week shows the first event on up to four scheduled days
   within the next week, with explicit extra counts; the optional family quest shows one current idea, falling back to tomorrow’s
   first event and its source-provided location; Weekend groups plans into two day
   columns. When in doubt, cut a row and disclose the remaining count.
2. **One frame, many bodies.** Every slot opens with the same chrome (kicker →
   optional rule → body → authoritative metadata when available). The body
   differs by content; the frame never does. That sameness-of-frame is what
   makes four different layouts feel like
   one system.
3. **Monochrome is a constraint, not a limitation.** Hard black/white for text;
   weight and size carry hierarchy, not grey. Dithering is reserved for posters.
4. **Numerals are the hero where they exist.** Countdowns and progress read as
   big figures; supporting text stays small and out of the way.

## Spacing

One base unit, `BASE = 8`. Every margin, gap, and inset is a multiple.

- `MARGIN = 24` (3×) — the outer frame, identical on every slot.
- `GUTTER = 24` (3×) — column gap.

This shared rhythm is most of what the eye reads as "consistent."

## Type ladder (Atkinson Hyperlegible)

A finite, named set of roles. Renderers reference the **role**, never a raw
size. Regular and bold font files are bundled under `reterminal/assets/fonts/`
so rendering is identical on macOS and Linux.

| Token | Size / weight | Role |
|-------|---------------|------|
| `KICKER` | 13 bold | slot label (top-left, UPPERCASE); also table column heads |
| `META` | 16 regular | dates, counts, secondary text |
| `SUBHEAD` | 18 bold | in-body section header (`TODAY`, `RECENT`, `UP NEXT`) |
| `BODY` | 22 regular | primary list text — the legibility floor |
| `BODY_BOLD` | 22 bold | emphasized list text (e.g. the week column) |
| `HEADLINE` | 28 bold | hero / item headline |
| `DISPLAY` | 54 bold | big numerals (day-countdowns) |
| `AGENDA_LABEL` | 18 bold | everyday page labels, dates and event times |
| `AGENDA_BODY` | 28 regular | everyday calendar event text |
| `AGENDA_TITLE` | 34 bold | everyday day headings and next-event title |

The everyday calendar edition uses `AGENDA_LEADING = 36` pixels for body
lines. Now and Weekend use equal-width columns with black text on white;
times sit above event titles rather than squeezing their reading measure.
Week uses full-width rows. Overflow is disclosed as a count, not hidden by
shrinking letters. Other provider layouts retain the original type ladder.

**Legibility floor:** body text is never below 22px; labels are bold. Thin
weights and sub-20px body copy turn to mush on the panel. Primary content wraps
within a deliberate measure instead of shrinking or ending in an ellipsis;
content limits create the space required for complete words and balanced lines.

**The one exception:** a genuinely dense composition (the missions 4-up grid,
four cards in one slot) may step a role down one rung *inside a cell*. Dense
exceptions are noted in code with a comment; do not let them spread.

## Slot anatomy

```
┌ MARGIN ────────────────────────────────────────────────┐
│ KICKER                                  [optional meta] │  ← draw_kicker()
│ ─────────────────────────────────────────────────────  │  ← draw_rule() (optional)
│                                                         │
│   body — composed per slot:                             │
│     now      : equal Today and Tomorrow columns         │
│     week     : up to four full-width dated rows         │
│     quest    : one current idea; Tomorrow fallback      │
│     weekend  : Saturday and Sunday columns             │
│                                                         │
│     Source checked / Source updated + timestamp          │
└─────────────────────────────────────────────────────────┘
```

- **Kicker** (`draw_kicker`): UPPERCASE slot label at `(MARGIN, MARGIN)`, with an
  optional right-aligned meta string on the same baseline. Returns the body top.
- **Rule** (`draw_rule`): 1px, inset to the margins. Used to separate header from
  body and to divide list rows — sparingly.
- **Stamp** (`draw_source_stamp`): bottom-right for generated/local feeds whose
  file write time is their real freshness signal. Calendar uses 2h, missions
  3d, and events/coming-up 14d. Canonical wiki features do not render filesystem
  mtime: trip/quest validity is explicit in their header fields, and unrelated
  private-page edits must not change pixels.

## Generated graphics

Feature pages may generate deterministic monochrome artwork from their content.
The trip focus draws a title-seeded mountain line; the action page deliberately
uses the space for large checklist rows instead of decorative art. Rendered
primitives are reproducible, not image-model calls: identical content must
always produce identical pixels and pass the snapshot gate.

## Iconography

The shape vocabulary in `render/viz.py` is the canonical icon set (drawn, never
glyphs — source emoji are stripped at render
time). The tag→shape map lives once, in `kitchen.shape_for`:

`trip △ · school ▢ · event ○ · performance ◇ · camp △(outline) · celebration ★ · default •`

## Adding or changing a slot

1. Open with `draw_kicker` and compose the body from the type ladder.
2. Use `draw_source_stamp` only when file mtime is an authoritative freshness
   signal; otherwise put an explicit reviewed/valid-through field in the scene.
3. Add a snapshot test + golden. Re-pin on intentional visual change.
4. If you reach for a size not in the ladder, that's a signal — either it maps
   to an existing role, or the ladder needs a deliberate new rung (update this
   doc + `kitchen.py` together), not a one-off `font(n)`.

## Calendar meaning and freshness

The everyday calendar reserves the last 34 pixels for an 18px source freshness
line. `Source checked` requires an explicit successful upstream `checked_at`;
legacy markdown uses `Source updated` and file mtime. A new render cannot renew
source freshness. After two hours the line begins `STALE`. The renderer
separately labels missing dates `Calendar unavailable`. An empty Today column
says `Nothing else today`, since elapsed events may have left an older export.

Structured calendar JSON preserves `timezone`, timezone-aware `checked_at`,
inclusive `start_date` / `end_date`, and `events` with `id`, `summary`, ISO
`start` / `end`, `status`, and `location`. All-day event ends are exclusive;
timed events retain their known end, so ongoing events remain visible until
they finish. Cancelled events are removed; tentative status stays visible.
An event title mentioning a time does not override an all-day calendar record.
Markdown remains supported but cannot supply missing end times.

## Seasonal cards and the optional household slot

A quest’s `Valid until` date is inclusive. Trips must declare `Valid until`
(or `Ends`) explicitly; undated and expired trips cannot keep claiming `ON TRIP`.
A manifest quest/trip entry may declare a nested `fallback` provider. Missing,
invalid, or expired cards then yield to that provider in the same physical slot.
Both source paths are watched. The everyday example uses a family quest in
slot 2, falling back to calendar `view: prepare`: tomorrow’s first event,
its recorded location when it fits, and the count of additional events. It
does not infer errands or commitments.

Family quest displays the source title, deck, and first Spark idea at the
everyday 28/34px scale, with an explicit note that more ideas remain in the
source. It does not relabel Spark/Build/Guide as invented weekday assignments.
