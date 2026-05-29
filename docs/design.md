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
| **Guardrail** | `tests/test_renderer_snapshots.py` goldens | any unintended pixel change fails CI; intentional ones move the pin in the same commit |

Rule: **change a token → update this doc in the same edit → re-pin the goldens.**
`CLAUDE.md` remains the source of truth for the rendering *constraints* (rules
6–9: Helvetica, `fontmode="1"`, threshold-vs-dither, full refresh); this doc is
the *design intent* above the code, and `docs/visualizations.md` is the
data-encoding vocabulary it draws on.

## Principles

1. **Glance, not read.** A slot answers one question from across the kitchen.
   Fewer items, larger type, more whitespace. When in doubt, cut a row.
2. **One frame, many bodies.** Every slot opens with the same chrome (kicker →
   optional rule → body → stamp). The body differs by content; the frame never
   does. That sameness-of-frame is what makes four different layouts feel like
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

## Type ladder (Helvetica)

A finite, named set of roles. Renderers reference the **role**, never a raw
size. Helvetica (not Neue) for uniform stroke weight under 1-bit; bold for
anything that must survive at distance.

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
│     calendar : two dated columns (TODAY / TOMORROW)     │
│     missions : 2×2 card grid (the dense exception)      │
│     comingup : big-number countdown rows + UP NEXT      │
│     camps    : week × who table                         │
│                                                         │
│                                      UPDATED / STALE ▸  │  ← draw_source_stamp()
└─────────────────────────────────────────────────────────┘
```

- **Kicker** (`draw_kicker`): UPPERCASE slot label at `(MARGIN, MARGIN)`, with an
  optional right-aligned meta string on the same baseline. Returns the body top.
- **Rule** (`draw_rule`): 1px, inset to the margins. Used to separate header from
  body and to divide list rows — sparingly.
- **Stamp** (`draw_source_stamp`): bottom-right. Neutral `UPDATED <mtime>` until a
  per-provider freshness threshold is exceeded, then a black `STALE` pill.
  Thresholds reflect how live a source is meant to be: calendar 2h, missions 3d,
  events/coming-up 14d, camps 180d (reference content, not a live feed — so a
  long window; a STALE camps grid would be a real signal, not noise).

## Iconography

The shape vocabulary in `render/viz.py` is the canonical icon set (drawn, never
glyphs — Helvetica.ttc has no emoji, and source emoji are stripped at render
time). The tag→shape map lives once, in `kitchen.shape_for`:

`trip △ · school ▢ · event ○ · performance ◇ · camp △(outline) · celebration ★ · default •`

## Adding or changing a slot

1. Open with `draw_kicker`; close with `draw_source_stamp`. Compose the body
   from the type ladder.
2. Pick a freshness threshold that matches how live the source is.
3. Add a snapshot test + golden. Re-pin on intentional visual change.
4. If you reach for a size not in the ladder, that's a signal — either it maps
   to an existing role, or the ladder needs a deliberate new rung (update this
   doc + `kitchen.py` together), not a one-off `font(n)`.
