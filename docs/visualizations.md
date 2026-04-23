# Visualization rubric

These primitives live in `python/reterminal/render/viz.py` and are the
sanctioned set of data visualizations across the display. Use them
purposefully — each primitive encodes a specific kind of quantity and
swapping one for another changes the meaning a reader infers.

Inspired by Chartli's visual vocabulary. Rendered with PIL directly (no
font dependency; no runtime beyond what's already in the repo).

## Principles

1. **One quantity per primitive.** A progress bar shows a fraction. A
   sparkline shows a trend. A heatmap shows a period. Don't overload.
2. **Match the primitive to the data, not the aesthetic.** Picking a ring
   because it "looks nice" on a streak is miscommunication. Kids reading
   this at a glance should get a correct intuition in <2s.
3. **Consistency across slots.** A progress bar on the missions slot
   should read the same as a progress bar on an events slot if one ever
   appears there. Same metaphor, same visual encoding.

## Primitives

### `progress_bar(draw, x, y, w, h, value, total, segments=None)`

**Use for:** bounded progress with a known total. "Week 2 of 4." "47 of
100 pages." Anything where the end is known and current position is the
point.

**Don't use for:** unbounded counters, trends over time, streaks
(streaks are a heatmap).

**Variants:**
- Continuous (no `segments`): single filled bar. Good for percentages
  and fine-grained measures.
- Segmented (`segments=N`): discrete filled boxes. Good for "N of M
  steps" where the step boundaries are meaningful (weeks, levels).

### `sparkline(draw, x, y, w, h, values)`

**Use for:** trend over time, short series. Pages read per day this
week, temperatures per hour, anything where the shape of the curve
matters more than any single value.

**Don't use for:** single-value metrics, categorical data, streaks.

### `heatmap(draw, x, y, values, cols)`

**Use for:** daily-granularity periods — streaks, attendance, habit
calendars. GitHub-contributions style. Filled cell = did the thing;
empty = missed.

**Don't use for:** continuous quantities (use a bar), trends without a
calendar structure (use a sparkline).

**Tip:** 30 cells at 6×5 gives you a rolling month. 7 cells in one row
gives you a week. Size the grid to the period that matters.

### `dots(draw, x, y, filled, total)`

**Use for:** small bounded counts. "3 of 5 chores done." "2 of 4
siblings here." Best when `total` ≤ ~8 — beyond that, use a progress
bar.

**Don't use for:** large totals, unbounded counters, trends.

### `ring(draw, cx, cy, radius, pct)`

**Use for:** single-metric glance where a fraction matters more than a
count. Battery-level-adjacent. Best as a hero element, not inline with
text.

**Don't use for:** counts (use dots), progress over segments (use
segmented progress bar), time-series (use sparkline).

### `scale(draw, x, y, w, value, low, high, ticks=5)`

**Use for:** position within a known range where the endpoints are
meaningful. "Reading level: age 4 ————◉———— age 10." Rarely needed;
reach for this only when a single scalar has a meaningful low/high
that the reader knows.

**Don't use for:** percentages (use a bar or ring), counts (use dots).

### `shape(draw, cx, cy, kind)`

**Use for:** categorical labels. Trip / school / event / performance /
camp / celebration. Same shape = same category across the display.
Deploy with a legend-free assumption (readers learn the vocabulary).

**Kinds:** `circle`, `square`, `triangle`, `triangle_outline`,
`diamond`, `star`, `dot`.

**Don't use for:** quantitative data. Shape is categorical only.

## Cross-slot conventions

- **Today / Tomorrow (slot 0/1):** use `shape` for event categories;
  no quantitative primitives yet.
- **Missions (slot 1, proposed):** use `progress_bar` for projects,
  `heatmap` for habits, `dots` for small counters.
- **Events (slot 2):** use `shape` for category tag.
- **Activities (slot 3):** no primitives yet; dithered poster hero
  carries the visual weight.

## When to add a new primitive

Only when existing primitives can't truthfully represent the data
you have. Don't add "because it would look cool." Every new primitive
adds visual vocabulary the reader has to learn.

## When to remove one

If a primitive is used in only one place and another primitive would
work equally well, prefer removal. Tight vocabulary > broad library.
