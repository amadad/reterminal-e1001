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
   Fewer items, larger type, more whitespace. When in doubt, cut a row.
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

**Legibility floor:** body text is never below 22px; labels are bold. Thin
weights and sub-20px body copy turn to mush on the panel.

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
│     calendar : TODAY masthead + inverted TOMORROW rail  │
│     camps    : current-week hero + four-week lookahead  │
│     trip     : countdown + route + next gate            │
│     quest    : generated mark + three entry levels      │
│                                                         │
│                        [generated-feed freshness stamp]  │
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
The Family Quest uses a title-seeded 5×5 mirrored mark; the trip feature draws a
title-seeded mountain line. These are reproducible render primitives, not
image-model calls: identical content must always produce identical pixels and
pass the snapshot gate.

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
